"""`record()`: the only way to write `audit_event` and `outbox_event` (AUD-01, AC-AUD1,
playbook 4.3). Both rows land in the same transaction as the change, with a user, agent
or system actor and before and after values. The outbox row is what the worker delivers
(webhooks, re-index, notifications) so a side effect can never exist without its audit
row, and vice versa.

`AppendOnlyModel` refuses update and delete in Python; the migration's trigger makes the
docstring true in the database, with a `SET LOCAL cw.maintenance = 'on'` escape hatch
so a conscious fix states its intent.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from typing import Any

from django.db import connection, models, transaction

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

    `tenant_id` is None for a library change (visible to everyone under the mixed
    policy) and the tenant's id for tenant work. `topic` defaults to `action`; the
    worker routes outbox rows by it. `payload` is what the worker needs to act; it
    never carries tenant content the audit `after` does not already hold.
    """
    from apps.shared.models import AuditEvent, OutboxEvent

    if not connection.in_atomic_block:
        raise NotInTransaction(
            "record() must run inside the transaction of the write it records; "
            "requests run under ATOMIC_REQUESTS, tasks use @tenant_task or transaction.atomic()."
        )
    with transaction.atomic():
        event = AuditEvent.objects.create(
            tenant_id=tenant_id,
            actor_type=actor.kind.value,
            actor_id=actor.id,
            actor_label=actor.label,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_title=subject_title,
            summary=summary,
            before=before or {},
            after=after or {},
            step_up_assertion_id=step_up_assertion_id,
            request_id=current_request_id() or "",
        )
        OutboxEvent.objects.create(
            tenant_id=tenant_id,
            audit_event=event,
            topic=topic or action,
            payload=payload or {"auditEventId": str(event.id), "subjectId": str(subject_id) if subject_id else None},
        )
    return event
