"""Request and response schemas of the governance app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from apps.shared.schemas import AuditSnapshot, CamelSchema


class AuditEventQuery(CamelSchema):
    """Filters of the audit log, each optional. A record is `subjectType` and `subjectId`;
    `from` is inclusive and `to` exclusive."""

    subject_type: str | None = Field(default=None, max_length=64)
    subject_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None


class AuditActorRef(CamelSchema):
    """Who did it: a user, an agent or the system. `id` is empty for the system."""

    type: str
    id: uuid.UUID | None
    label: str


class AuditEventRow(CamelSchema):
    id: uuid.UUID
    created_at: datetime
    actor: AuditActorRef
    action: str
    subject_type: str
    subject_id: uuid.UUID | None
    subject_title: str
    summary: str
    before: AuditSnapshot
    after: AuditSnapshot
    stepped_up: bool


class AuditEventPage(CamelSchema):
    items: list[AuditEventRow]
    total: int
