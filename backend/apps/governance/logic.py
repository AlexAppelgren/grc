"""Business logic of the governance app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3).

The tenant audit log (AUD-01): row-level security has already cut `audit_event` to the
tenant's own rows and the rows without a tenant. Of the latter a tenant sees only a library
record's change made by an agent, the system or platform staff. Every other row without a
tenant stays hidden: proposal rows (a tenant-made proposal's title, the editor's rejection
note, a tenant member as proposer) and platform identity events (sign-ins, code requests,
which may name a member of another tenant).
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.governance.schemas import AuditActorRef, AuditEventQuery, AuditEventRow
from apps.identity.models import PlatformRoleAssignment
from apps.shared.audit import ActorType
from apps.shared.models import AuditEvent
from apps.shared.schemas import AuditSnapshot

LIBRARY_SUBJECT_TYPES = ("authority", "instrument", "provision", "obligation", "vocabulary", "taxonomy_term")


def audit_events(
    tenant_id: uuid.UUID | None, filters: AuditEventQuery, *, limit: int, offset: int
) -> tuple[list[AuditEvent], int]:
    """The tenant's audit log, newest first, with the total. A platform session has no
    tenant and no audit view in chunk 4: 404, like every tenant route."""
    if tenant_id is None:
        raise ValidationError("Not found.", code="not_found")
    library_change = Q(tenant__isnull=True, subject_type__in=LIBRARY_SUBJECT_TYPES) & (
        Q(actor_type__in=(ActorType.AGENT.value, ActorType.SYSTEM.value))
        | Q(actor_type=ActorType.USER.value, actor_id__in=PlatformRoleAssignment.objects.values("user_id"))
    )
    events = AuditEvent.objects.filter(Q(tenant_id=tenant_id) | library_change)
    if filters.subject_type:
        events = events.filter(subject_type=filters.subject_type)
    if filters.subject_id:
        events = events.filter(subject_id=filters.subject_id)
    if filters.actor_id:
        events = events.filter(actor_id=filters.actor_id)
    if filters.from_:
        events = events.filter(created__gte=filters.from_)
    if filters.to:
        events = events.filter(created__lt=filters.to)
    events = events.order_by("-created", "-id")
    return list(events[offset : offset + limit]), events.count()


def audit_row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        id=event.id,
        created_at=event.created,
        actor=AuditActorRef(type=event.actor_type, id=event.actor_id, label=event.actor_label),
        action=event.action,
        subject_type=event.subject_type,
        subject_id=event.subject_id,
        subject_title=event.subject_title,
        summary=event.summary,
        before=AuditSnapshot(event.before),
        after=AuditSnapshot(event.after),
        stepped_up=event.step_up_assertion_id is not None,
    )
