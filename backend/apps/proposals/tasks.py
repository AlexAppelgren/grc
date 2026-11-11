"""The library baseline's runner and the library's translator, on the beat and on an
approval (D-118, ADR 0065; D-129). Not a `@tenant_task`: they file only shared proposals.

`LIBRARY_BASELINE_FILING_MINUTES` and `LIBRARY_TRANSLATION_MINUTES` set the beat (0
switches translation off); an approval queues the same work `LIBRARY_BASELINE_ON_APPROVAL_S`
later, once per window, so approving thousands never queues thousands of model calls.

A session advisory lock keeps runs from overlapping. The queueing rides the approval's
outbox row and is registered from `ProposalsConfig.ready()`, never at import
(apps/shared/tests_outbox.py)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import connection

from apps.proposals import baseline, translations
from apps.shared import outbox
from apps.shared.models import OutboxEvent

# The approval's own outbox row (apps/proposals/apply.py, `_new_instrument`).
INSTRUMENT_CREATED = "instrument.created"
# The approvals that add a record with texts to translate (apps/proposals/apply.py), and the
# kind of record each one names.
TRANSLATED_ON = {"obligation.created": "obligation", "instrument.summary_added": "instrument"}
_LOCK = "library-baseline"
_QUEUED = "library-baseline:queued"
_TRANSLATION_QUEUED = "library-translation:queued"


@shared_task
def file_library_baseline() -> None:
    """Register the sources the baseline names, then file every entry now due: the
    instruments the library does not hold, and the duties of every instrument it does."""
    with _one_run_at_a_time():
        baseline.register_sources()
        baseline.file()


@contextmanager
def _one_run_at_a_time() -> Iterator[None]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [_LOCK])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [_LOCK])


def register() -> None:
    """Queue a filing when a library instrument is approved. Safe to call twice."""
    outbox.register_handler(INSTRUMENT_CREATED, queue_after_approval)
    for kind in TRANSLATED_ON:
        outbox.register_handler(kind, queue_translation)


def queue_after_approval(event: OutboxEvent) -> None:
    """Queue one run a few seconds out, unless one is already queued for this window. A
    bank's own instrument (recorded in its zone) has no baseline duties and queues nothing."""
    wait = settings.LIBRARY_BASELINE_ON_APPROVAL_S
    if event.tenant_id is not None or not wait:
        return
    if cache.add(_QUEUED, True, timeout=wait):
        file_library_baseline.apply_async(countdown=wait)


@shared_task
def file_library_translations() -> None:
    """Queue one translation task per record that lacks a content language, up to
    `LIBRARY_TRANSLATION_RUN_MAX` (D-129): fanned out, so one slow answer holds up no other."""
    for target, record_id in translations.due(settings.LIBRARY_TRANSLATION_RUN_MAX):
        translate_library_record.delay(target, str(record_id))


@shared_task
def translate_library_record(target: str, record_id: str) -> None:
    """Ask for one record's missing translations and file them as a proposal (D-129)."""
    translations.translate(target, uuid.UUID(record_id))


def queue_translation(event: OutboxEvent) -> None:
    """After an approval that adds a shared obligation or an instrument's summary, queue one
    fan-out a few seconds out (`LIBRARY_BASELINE_ON_APPROVAL_S`), unless one is queued for
    this window or translation is off, so many approvals queue one fan-out of at most
    `LIBRARY_TRANSLATION_RUN_MAX`. A bank's own record is never a model input (D-57)."""
    if event.tenant_id is not None or not settings.LIBRARY_TRANSLATION_MINUTES or event.topic not in TRANSLATED_ON:
        return
    wait = max(settings.LIBRARY_BASELINE_ON_APPROVAL_S, 1)
    if cache.add(_TRANSLATION_QUEUED, True, timeout=wait):
        file_library_translations.apply_async(countdown=wait)


@shared_task
def approve_listed(user_id: str, proposal_ids: list[str], step_up_assertion_id: str) -> None:
    """Approve all, run by the worker (apps/proposals/approve_all.py, D-128). Not a
    `@tenant_task`: the console queue is platform work in the shared zone, as the approve
    route's own is."""
    from apps.identity.models import User
    from apps.proposals import approve_all

    user = User.objects.get(pk=user_id)
    approve_all.approve_listed(user=user, proposal_ids=proposal_ids, step_up_assertion_id=uuid.UUID(step_up_assertion_id))
