"""Shared Pydantic schemas. snake_case in the database, camelCase in the API through the
alias generator on `CamelSchema` (playbook 4.1). Every app's schemas.py subclasses it.
Schema class names are global across apps (Ninja flattens components), so app-specific
shapes carry the app prefix."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from ninja import Schema
from pydantic import ConfigDict, Field, RootModel
from pydantic.alias_generators import to_camel


class CamelSchema(Schema):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class ProductInfo(CamelSchema):
    product_name: str


class PageQuery(Schema):
    """Pagination on every list (playbook 10): `limit` default 20, max 100, `offset`.
    The numbers come from settings; a value above the maximum is a 422, not a clamp."""

    limit: int = Field(default=settings.API_PAGE_SIZE_DEFAULT, ge=1, le=settings.API_PAGE_SIZE_MAX)
    offset: int = Field(default=0, ge=0)


class MailOutboxMessage(CamelSchema):
    """One message the mock mailer sent, for E2E journeys (playbook 8.3)."""

    to: str
    subject: str
    body: str


class VocabularyEntry(CamelSchema):
    """What every vocabulary read returns (playbook 15): key and kind, never a phrase the
    client must string-match, plus the label in the caller's language."""

    key: str
    kind: str | None
    label: str
    usage_note: str
    sort_order: int
    active: bool
    is_system: bool
    is_default: bool


class AuditSnapshot(RootModel[dict[str, Any]]):
    """The `before` and `after` columns of audit_event: the audited record's fields at
    the time, keyed by field name. Free-form by nature (the audit log stores every
    model); named here so the JSONField's comment points somewhere real."""


class OutboxPayload(RootModel[dict[str, Any]]):
    """The `payload` column of outbox_event: what the worker needs to act on the topic,
    always including `auditEventId`. Never tenant content the audit row lacks."""
