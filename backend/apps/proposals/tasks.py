"""The library baseline's runner, on the beat and on an approval (D-118, ADR 0065).

Not a `@tenant_task`: it activates no tenant and files only shared proposals, as the
command does from the API's shell. `LIBRARY_BASELINE_FILING_MINUTES` sets how often the beat
runs it; `LIBRARY_BASELINE_ON_APPROVAL_S` queues it that many seconds after a reviewer
approves a library instrument, so the duties follow at once (config/settings.py).

Runs never overlap: a session advisory lock makes a second run wait for the first and then
read what the first filed, so the beat and an approval can never file one entry twice. The
queueing rides the outbox row of the approval, the one relay there is, and is registered
from `ProposalsConfig.ready()`, never at import (apps/shared/tests_outbox.py)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import connection

from apps.proposals import baseline
from apps.shared import outbox
from apps.shared.models import OutboxEvent

# The approval's own outbox row (apps/proposals/apply.py, `_new_instrument`).
INSTRUMENT_CREATED = "instrument.created"
_LOCK = "library-baseline"
_QUEUED = "library-baseline:queued"


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


def queue_after_approval(event: OutboxEvent) -> None:
    """Queue one run a few seconds out, unless one is already queued for this window. A
    bank's own instrument (recorded in its zone) has no baseline duties and queues nothing."""
    wait = settings.LIBRARY_BASELINE_ON_APPROVAL_S
    if event.tenant_id is not None or not wait:
        return
    if cache.add(_QUEUED, True, timeout=wait):
        file_library_baseline.apply_async(countdown=wait)
