"""The one ordered cursor over `outbox_event` (chunk 5 ruling 9; AUD-01, CAS-01, NFR-01,
NFR-04).

`record()` writes an outbox row in the transaction of the write it records, and this
module is the only thing that delivers one. It writes no event of its own: it marks the
delivery columns the `cw_outbox_guard` trigger allows (`published_at`, `attempts`,
`last_error`) and moves one cursor row. Every consumer — chunk 5's case creation, chunk
7's indexing, chunk 10's collaboration, chunk 13's integrations — registers a handler
here, and there is no second relay.

**Reading every zone.** The app role cannot bypass row-level security and `outbox_event`
is a mixed table, so with no tenant activated one read would see the library's rows only
and every tenant's rows would sit undelivered forever (fail closed, but forever). A batch
therefore reads once per zone — the library, then each tenant — and merges the results by
`(created, id)`. That is one query per zone, never one per row, and the handlers are
dispatched from the merged list (fan out, never chain).

**Order, and exactly once.** Pending is `published_at IS NULL` with attempts left, not
"after the cursor's position": two writers commit in an order of their own, so a row whose
transaction commits after a row with a later `created` would be stepped over by a
positional scan and never delivered. The cursor row carries the position of the last
delivered event, the retry clock, and — through `SELECT ... FOR UPDATE SKIP LOCKED` — the
lock that keeps a second worker from delivering a row twice.

**Failure.** A handler that raises leaves its row unpublished, counts the attempt and
stops the batch there, so nothing behind it overtakes it; the row is tried again after
`OUTBOX_RETRY_BACKOFF_S`, doubled per attempt. After `OUTBOX_MAX_ATTEMPTS` the row is left
failed — unpublished, with its attempt count and the exception's type name — and the
cursor moves on. The type name and never the message: an exception message carries the
values of the row that failed (playbook 4.7), and the audit event this row points at
already holds what happened.

**The library-row path** is what chunk 7's indexing depends on. Alex's answer on the search
fence (item 4) has library rows indexed from events dispatched with no tenant active,
which is exactly what a row with no `tenant_id` gets here.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.shared import tenancy
from apps.shared.models import OutboxCursor, OutboxEvent, Tenant

logger = logging.getLogger(__name__)

CURSOR_NAME = "outbox"

Handler = Callable[[OutboxEvent], None]

# Kind (the row's `topic`) -> the handlers that act on it. Empty here and empty when the
# chunk ships: a consumer registers its own where it is defined, never in this module.
_HANDLERS: dict[str, list[Handler]] = {}


@dataclass(frozen=True)
class BatchResult:
    delivered: int = 0  # rows whose handlers all ran, now published
    failed: int = 0  # rows whose handler raised in this pass, whether or not retries are left


def register_handler(kind: str, fn: Handler) -> None:
    """Call `fn` with every row of this kind, in order, inside the row's own zone."""
    _HANDLERS.setdefault(kind, []).append(fn)


def deliver_batch() -> BatchResult:
    """Deliver one batch of pending rows, in `(created, id)` order, exactly once.

    Everything happens in one transaction: the handlers, the `published_at` marks and the
    cursor. A second worker whose cursor is locked returns an empty result at once.
    """
    delivered = failed = 0
    with transaction.atomic():
        cursor = _locked_cursor()
        if cursor is None:
            return BatchResult()
        moment = timezone.now()
        if cursor.retry_not_before is not None and moment < cursor.retry_not_before:
            return BatchResult()  # the row at the front is waiting out its backoff
        for event in _pending(settings.OUTBOX_BATCH_SIZE):
            try:
                _deliver(event)
            except Exception as error:  # compliance: allow-broad-except a handler is a consumer's code and its failure belongs on its own row, not on the batch
                failed += 1
                if _record_failure(event, error):
                    cursor.retry_not_before = None  # attempts spent: left failed, the cursor moves on
                    continue
                cursor.retry_not_before = moment + _backoff(event.attempts)
                break  # the cursor does not advance past it, so order holds
            _mark_published(event, moment)
            cursor.last_created, cursor.last_id, cursor.retry_not_before = event.created, event.id, None
            delivered += 1
        cursor.save(update_fields=["last_created", "last_id", "retry_not_before", "updated"])
    return BatchResult(delivered=delivered, failed=failed)


def _locked_cursor() -> OutboxCursor | None:
    """The cursor row, locked for this batch, or None while another worker holds it."""
    OutboxCursor.objects.get_or_create(name=CURSOR_NAME)
    return (
        OutboxCursor.objects.select_for_update(skip_locked=True)
        .filter(name=CURSOR_NAME)
        .first()  # ordering: the cursor is one row, looked up by its name
    )


def _pending(limit: int) -> list[OutboxEvent]:
    """The next rows to deliver, in `(created, id)` order: one read per zone, merged.

    A row whose attempts are spent is behind the cursor and is never read again.
    """
    zones: list[uuid.UUID | None] = [None, *Tenant.objects.order_by("slug").values_list("id", flat=True)]
    rows: list[OutboxEvent] = []
    for tenant_id in zones:
        _enter_zone(tenant_id)
        zone = (
            OutboxEvent.objects.filter(tenant__isnull=True)
            if tenant_id is None
            else OutboxEvent.objects.filter(tenant_id=tenant_id)
        )
        rows.extend(
            zone.filter(published_at__isnull=True, attempts__lt=settings.OUTBOX_MAX_ATTEMPTS).order_by(
                "created", "id"
            )[:limit]
        )
    rows.sort(key=lambda row: (row.created, row.id))
    return rows[:limit]


def _deliver(event: OutboxEvent) -> None:
    """Run every handler registered for this row's kind, inside the row's own zone."""
    if event.tenant_id is None:
        _enter_zone(None)  # a library row's handlers run with no tenant activated
        _run_handlers(event)
    else:
        _run_handlers_in_tenant(event.tenant_id, event)


@tenancy.tenant_task
def _run_handlers_in_tenant(tenant_id: uuid.UUID, event: OutboxEvent) -> None:
    """A tenant row's handlers, with its tenant activated, inside the batch's transaction.
    Fanning one row out to other tenants is a handler's job, never the cursor's."""
    _run_handlers(event)


def _run_handlers(event: OutboxEvent) -> None:
    for handler in _HANDLERS.get(event.topic, []):
        handler(event)


def _mark_published(event: OutboxEvent, moment: datetime) -> None:
    _enter_zone(event.tenant_id)
    event.published_at = moment
    event.save(update_fields=["published_at"])


def _record_failure(event: OutboxEvent, error: BaseException) -> bool:
    """Count the attempt on the row and answer whether its attempts are now spent.

    The exception's type name only: its message would carry the values of the row that
    failed. The log line names the row, its kind and the attempt, and nothing else.
    """
    _enter_zone(event.tenant_id)
    event.attempts += 1
    event.last_error = type(error).__name__[:500]
    event.save(update_fields=["attempts", "last_error"])
    spent = event.attempts >= settings.OUTBOX_MAX_ATTEMPTS
    logger.warning(
        "outbox delivery failed",
        extra={"outboxEventId": str(event.id), "kind": event.topic, "attempts": event.attempts, "spent": spent},
    )
    return spent


def _backoff(attempts: int) -> timedelta:
    """`OUTBOX_RETRY_BACKOFF_S`, doubled for each attempt already spent."""
    return timedelta(seconds=settings.OUTBOX_RETRY_BACKOFF_S * 2 ** (attempts - 1))


def _enter_zone(tenant_id: uuid.UUID | None) -> None:
    """Put the batch's transaction in one zone: a tenant's, or the library's (no tenant).

    The database setting only, not `tenancy.activate()`: the Python-side mirror of the
    active tenant belongs to the `@tenant_task` around the handlers, which sets it and
    puts it back. `SET LOCAL` outside a transaction is a silent no-op, so this refuses to
    run outside one for the same reason `tenancy.activate()` does.
    """
    if not connection.in_atomic_block:
        raise tenancy.NotInTransaction(
            "the outbox cursor sets its zone inside the batch's transaction; deliver_batch() opens it"
        )
    with connection.cursor() as db_cursor:
        db_cursor.execute("SELECT set_config(%s, %s, true)", [tenancy.TENANT_SETTING, str(tenant_id or "")])
