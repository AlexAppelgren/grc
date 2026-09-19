"""Shared Pydantic schemas. snake_case in the database, camelCase in the API through the
alias generator on `CamelSchema` (playbook 4.1). Every app's schemas.py subclasses it.
Schema class names are global across apps (Ninja flattens components), so app-specific
shapes carry the app prefix."""

from __future__ import annotations

import uuid
from typing import Any

from ninja import Schema
from pydantic import ConfigDict, RootModel
from pydantic.alias_generators import to_camel


class CamelSchema(Schema):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class ProductInfo(CamelSchema):
    product_name: str


class MeResponse(CamelSchema):
    """Phase 0 shape of GET /me: the principal only. Chunk 1 adds the user, tenant, roles
    and queue counts of the designed `Me` (contract_drift_pending.txt)."""

    kind: str
    subject_id: uuid.UUID
    tenant_id: uuid.UUID | None
    permissions: list[str]
    scopes: list[str]


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
