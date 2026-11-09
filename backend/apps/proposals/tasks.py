"""The library baseline's runner and the library's translator, on the beat and on an
approval (D-118, ADR 0065; D-129).

Not a `@tenant_task`: it activates no tenant and files only shared proposals, as the
command does from the API's shell. `LIBRARY_BASELINE_FILING_MINUTES` sets how often the beat
runs it; `LIBRARY_BASELINE_ON_APPROVAL_S` queues it that many seconds after a reviewer
approves a library instrument, so the duties follow at once (config/settings.py).
`LIBRARY_TRANSLATION_MINUTES` sets how often the beat queues the records the translator
asks about, one task each up to `LIBRARY_TRANSLATION_RUN_MAX`, and an approval that adds an
obligation or an instrument's summary queues that same fan-out a few seconds later, once for
every approval in the window, so approving thousands at once never queues thousands of model
calls; 0 switches both off (apps/proposals/translations.py).

Runs never overlap: a session advisory lock makes a second run wait for the first and then
read what the first filed, so the beat and an approval can never file one entry twice. The
queueing rides the outbox row of the approval, the one relay there is, and is registered
from `ProposalsConfig.ready()`, never at import (apps/shared/tests_outbox.py)."""

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
    fan-out of the beat's own a few seconds out (`LIBRARY_BASELINE_ON_APPROVAL_S`, the same
    wait the baseline's filing takes), unless one is already queued for this window or
    translation is switched off: approving 2,000 duties queues one fan-out of at most
    `LIBRARY_TRANSLATION_RUN_MAX`, never 2,000 model calls at once. A bank's own record
    (recorded in its zone) is never translated: it is never a model input (D-57)."""
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
