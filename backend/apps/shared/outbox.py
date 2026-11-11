"""The one ordered cursor over `outbox_event` (AUD-01, CAS-01, NFR-01, NFR-04).

`record()` writes an outbox row with the write it records; this module is the only thing
that delivers one. It writes only the delivery columns `cw_outbox_guard` allows and moves one
cursor row. Every consumer registers a handler here; there is no second relay.

**Every zone.** The app role cannot bypass row-level security, so a batch reads once per zone
(the library, then each tenant) and merges by `(created, id)`: one query per zone, never per
row.

**Order, exactly once.** Pending is `published_at IS NULL` with attempts left, not "after the
cursor", since a late commit would be stepped over (`outbox_event_zone_pending`). The cursor's
`SELECT ... FOR UPDATE SKIP LOCKED` keeps a second worker from delivering a row twice.

**Failure.** Each row's handlers run in a savepoint of their own, so a database failure leaves
the batch a usable transaction and takes the half-done writes with it. A raising handler
leaves its row unpublished, counts the attempt and stops the batch, retried after
`OUTBOX_RETRY_BACKOFF_S` doubled per attempt; after `OUTBOX_MAX_ATTEMPTS` the row is left
failed with the exception's type name, never its message (playbook 4.7).

**One retry clock**, on the cursor: a library row's backoff holds back the tenants' rows too.
Library rows are dispatched with no tenant active, which search indexing relies on.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
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

# Kind (the row's `topic`) -> the handlers that act on it. Empty here: a consumer registers
# its own from its app's `ready()`, never in this module.
_HANDLERS: dict[str, list[Handler]] = {}


@dataclass(frozen=True)
class BatchResult:
    delivered: int = 0  # rows whose handlers all ran, now published
    failed: int = 0  # rows whose handler raised in this pass, whether or not retries are left


def register_handler(kind: str, fn: Handler) -> None:
    """Call `fn` with every row of this kind, in order, inside the row's own zone. The same
    function twice is one registration, so a handler never runs twice for a row.
    """
    registered = _HANDLERS.setdefault(kind, [])
    if fn not in registered:
        registered.append(fn)


def deliver_batch() -> BatchResult:
    """Deliver one batch of pending rows, in `(created, id)` order, exactly once.

    Everything happens in one transaction: the handlers, the `published_at` marks and the
    cursor. A second worker whose cursor is locked returns an empty result at once.
    """
    delivered: list[OutboxEvent] = []
    failed = 0
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
            cursor.last_created, cursor.last_id, cursor.retry_not_before = event.created, event.id, None
            delivered.append(event)
        _mark_published(delivered, moment)
        cursor.save(update_fields=["last_created", "last_id", "retry_not_before", "updated"])
    return BatchResult(delivered=len(delivered), failed=failed)


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
    """Run every handler registered for this row's kind, inside the row's zone and a
    savepoint of its own (`@tenant_task`'s for a tenant row, one opened here for a library
    row), so a database failure leaves the batch a usable transaction to count the attempt,
    mark what was delivered and move the cursor, and undoes the handler's half-done writes."""
    if event.tenant_id is None:
        with transaction.atomic():
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


def _mark_published(events: list[OutboxEvent], moment: datetime) -> None:
    """Mark everything this batch delivered, one statement per zone (the session writes only
    its own zone), inside the batch's transaction, so a row is published exactly when its
    handlers ran."""
    by_zone: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
    for event in events:
        by_zone[event.tenant_id].append(event.id)
    for tenant_id, ids in by_zone.items():
        _enter_zone(tenant_id)
        OutboxEvent.objects.filter(id__in=ids).update(published_at=moment)


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

    The database setting only: the Python mirror belongs to the `@tenant_task` around the
    handlers. Refuses to run outside a transaction, where `SET LOCAL` is a silent no-op.
    """
    if not connection.in_atomic_block:
        raise tenancy.NotInTransaction(
            "the outbox cursor sets its zone inside the batch's transaction; deliver_batch() opens it"
        )
    with connection.cursor() as db_cursor:
        db_cursor.execute("SELECT set_config(%s, %s, true)", [tenancy.TENANT_SETTING, str(tenant_id or "")])
