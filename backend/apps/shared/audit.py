"""`record()`: the only way to write `audit_event` and `outbox_event` (AUD-01, AC-AUD1,
playbook 4.3). Both rows land in the same transaction as the change, with a user, agent
or system actor and before and after values. The outbox row is what the worker delivers
(webhooks, re-index, notifications) so a side effect can never exist without its audit
row, and vice versa.

`AppendOnlyModel` refuses update and delete in Python; the migration's trigger makes the
docstring true in the database, with the escape hatch in apps/shared/migration_helpers.py
so a conscious fix states its intent.

`batched()` is the same door for a write of many subjects at once, such as a pasted
Statement of Applicability: every `record()` inside the block is held and, when the block
ends, its rows go in together, in the same transaction, under the same triggers, built by
the same code as one call's rows.

The audit rows and their outbox rows go in as one statement, and a savepoint is taken only
around a write that crosses the zones (ADR 0063).
"""

from __future__ import annotations

import enum
import itertools
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from django.db import connection, models, transaction
from django.db.models.sql import InsertQuery

from apps.shared import tenancy
from apps.shared.authentication import Principal
from apps.shared.middleware import current_request_id


class ActorType(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): who did it."""

    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


ACTOR_TYPE_CHOICES = [(kind.value, kind.value) for kind in ActorType]


@dataclass(frozen=True)
class Actor:
    kind: ActorType
    id: uuid.UUID | None = None
    label: str = ""  # a person's name or an agent's name: permitted in logs and audit

    @classmethod
    def system(cls, label: str = "system") -> Actor:
        return cls(kind=ActorType.SYSTEM, id=None, label=label)


def key_actor(principal: Principal) -> Actor:
    """Who a key's request acts as in the audit log. A personal access token names its
    person and a key of an agent access entry names the entry (ACC-03); a key bound to one
    of our agents names the agent (ID-10); any other key is named by its own id."""
    if principal.acting_user_id is not None:
        return Actor(kind=ActorType.USER, id=principal.acting_user_id, label=principal.acting_user_label)
    if principal.agent_access_id is not None:
        return Actor(kind=ActorType.AGENT, id=principal.agent_access_id, label=principal.agent_access_label)
    if principal.agent_id is not None:
        return Actor(kind=ActorType.AGENT, id=principal.agent_id, label=principal.agent_label)
    return Actor(kind=ActorType.AGENT, id=principal.subject_id, label=f"api key {principal.subject_id}")


class AppendOnlyRefused(RuntimeError):
    """An append-only row was updated or deleted from Python (AC-AUD1)."""


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs: Any) -> int:  # compliance: allow-kwargs Django QuerySet signature
        raise AppendOnlyRefused(f"{self.model.__name__} is append-only; rows are never updated")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AppendOnlyRefused(f"{self.model.__name__} is append-only; rows are never deleted")


class AppendOnlyModel(models.Model):
    """A ledger row: inserted once, then read. The database trigger of the same name
    enforces it for every client, this class for the ORM."""

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:  # compliance: allow-kwargs Django Model.save signature
        if not self._state.adding:
            raise AppendOnlyRefused(f"{type(self).__name__} is append-only; rows are never updated")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        raise AppendOnlyRefused(f"{type(self).__name__} is append-only; rows are never deleted")


class NotInTransaction(RuntimeError):
    """record() was called outside a transaction, so the audit row could commit alone."""


@dataclass(frozen=True)
class _Pending:
    """One `record()` call's values."""

    fields: dict[str, Any]
    topic: str
    payload: dict[str, Any] | None


# The block `batched()` holds open, or None when each record() writes at once.
_batch: ContextVar[list[_Pending] | None] = ContextVar("audit_batch", default=None)


@contextmanager
def batched() -> Iterator[None]:
    """Hold every `record()` of the block and write them all when it ends: one statement for
    the lot (two when some cross the zones), in the caller's transaction, in the order
    recorded. The zone is read when the block ends, so a block that moves between zones
    writes each tenant's rows in that tenant's zone only if it ends there: keep a block
    inside one bank, as the row-level security refuses anything else.
    A block that raises writes nothing, and its transaction rolls back with the change. A
    `record()` inside the block returns None, since its row does not exist yet. A block
    inside another joins it."""
    if _batch.get() is not None:
        yield
        return
    pending: list[_Pending] = []
    token = _batch.set(pending)
    try:
        yield
    finally:
        _batch.reset(token)
    _write(pending)


def record(
    *,
    action: str,
    actor: Actor,
    subject_type: str,
    subject_id: uuid.UUID | None,
    subject_title: str,
    summary: str,
    tenant_id: uuid.UUID | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    step_up_assertion_id: uuid.UUID | None = None,
    topic: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    """Write the audit event and its outbox event in the caller's transaction.

    `tenant_id` is None for a library change (read by everyone under the mixed policy) and
    the tenant's id for tenant work. Both rows are written in the zone `tenant_id` names,
    because a mixed table accepts only the zone the session is in (H15): the two rows of a
    library change made from a bank's own session go in with the tenant cleared, and this is
    the one door that may cross the zones. Which calls may pass `tenant_id=None`, and under
    which subject, is the guard's question, not the policy's (hardening H3).

    `topic` defaults to `action`; the worker routes outbox rows by it. `payload` is what the
    worker needs to act; it never carries tenant content the audit `after` does not already
    hold.
    """
    if not connection.in_atomic_block:
        raise NotInTransaction(
            "record() must run inside the transaction of the write it records; "
            "requests run under ATOMIC_REQUESTS, tasks use @tenant_task or transaction.atomic()."
        )
    pending = _Pending(
        fields={
            "tenant_id": tenant_id,
            "actor_type": actor.kind.value,
            "actor_id": actor.id,
            "actor_label": actor.label,
            "action": action,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "subject_title": subject_title,
            "summary": summary,
            "before": before or {},
            "after": after or {},
            "step_up_assertion_id": step_up_assertion_id,
            "request_id": current_request_id() or "",
        },
        topic=topic or action,
        payload=payload,
    )
    batch = _batch.get()
    if batch is not None:
        batch.append(pending)
        return None
    return _write([pending])[0]


def _write(pending: list[_Pending]) -> list[Any]:
    """The audit and outbox rows of `pending`, one statement per run of rows in one zone.

    A run in the session's own zone is one statement and nothing else: if it fails, the
    database aborts the caller's transaction and the change it records goes with it, so no
    savepoint is wanted, and none is taken so that a caller who swallowed the error could
    not commit the change without its rows (ADR 0063). A run that crosses the zones, a row
    of no tenant written from a bank's session, goes in inside `platform_zone()` and a
    savepoint: the zone block comes before the atomic one, so a failed insert rolls back to
    its savepoint before the tenant goes back on and the caller sees the error the insert
    raised. The zone is the GUC, not the context variable, since that is what a policy
    sees, and it is read only when a row of no tenant is written.

    The ids are sorted so that rows stamped in the same microsecond still read back in the
    order recorded, as the tables order by (created, id)."""
    from apps.shared.models import AuditEvent, OutboxEvent

    if pending and not connection.in_atomic_block:
        raise NotInTransaction("record() must write in the transaction of the change it records.")
    in_bank = any(row.fields["tenant_id"] is None for row in pending) and tenancy.database_tenant_id() is not None
    events: list[Any] = []
    for crosses_zones, group in itertools.groupby(pending, key=lambda row: in_bank and row.fields["tenant_id"] is None):
        rows = list(group)
        ids = sorted(uuid.uuid4() for _ in rows)
        written = [AuditEvent(id=event_id, **row.fields) for event_id, row in zip(ids, rows, strict=True)]
        outbox = [
            OutboxEvent(
                id=outbox_id,
                tenant_id=row.fields["tenant_id"],
                audit_event=event,
                topic=row.topic,
                payload=row.payload
                or {"auditEventId": str(event.id), "subjectId": str(row.fields["subject_id"]) if row.fields["subject_id"] else None},
            )
            for outbox_id, event, row in zip(sorted(uuid.uuid4() for _ in rows), written, rows, strict=True)
        ]
        with tenancy.platform_zone() if crosses_zones else nullcontext(), transaction.atomic() if crosses_zones else nullcontext():
            _insert_both(written, outbox)
        events.extend(written)
    return events


def _insert_both(events: Sequence[models.Model], outbox: Sequence[models.Model]) -> None:
    """The audit rows and their outbox rows as one statement: the audit INSERT as a
    data-modifying WITH, the outbox INSERT as its main statement. Each INSERT is the one
    `bulk_create` would send, built by Django's own compiler from the same objects, so every
    column, default and timestamp is what it was; the foreign key from outbox to audit is
    checked when the statement ends, when both sets of rows exist."""
    statements = []
    for model_rows in (events, outbox):
        query = InsertQuery(type(model_rows[0]))
        query.insert_values(type(model_rows[0])._meta.concrete_fields, list(model_rows))
        [statement] = query.get_compiler(connection=connection).as_sql()
        statements.append(statement)
    (audit_sql, audit_params), (outbox_sql, outbox_params) = statements
    with connection.cursor() as cursor:
        cursor.execute(f"WITH audit_rows AS ({audit_sql}) {outbox_sql}", (*audit_params, *outbox_params))
    for row in (*events, *outbox):
        row._state.adding = False
        row._state.db = connection.alias
