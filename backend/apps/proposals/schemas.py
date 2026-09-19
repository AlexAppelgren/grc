"""Request and response schemas of the proposals app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

The payload is named per kind (PRO-01): `apply()` never reads a free-form dictionary, and
a malformed payload is refused when the proposal is created, not when it is approved, so
the queue never holds a proposal nobody can apply.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from apps.shared.schemas import CamelSchema

__all__ = ["CamelSchema"]


class ProposalActorRef(CamelSchema):
    id: UUID
    name: str


# ---------------------------------------------------------------------------------------
# Payloads, one named schema per kind (PRO-01). `list` is a vocabulary list name from
# apps/taxonomy/registry.py; `key` is the immutable key the row will carry forever.
# ---------------------------------------------------------------------------------------
class ProposalVocabularyCreatePayload(CamelSchema):
    list: str
    key: str
    labels: dict[str, str]
    usage_note: str = ""
    kind: str | None = None
    sort_order: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)  # schema: VocabularyExtra


class ProposalVocabularyRelabelPayload(CamelSchema):
    list: str
    key: str
    labels: dict[str, str] = Field(default_factory=dict)
    usage_note: str | None = None
    sort_order: int | None = None
    extra: dict[str, Any] | None = None  # schema: VocabularyExtra


class ProposalVocabularyRetirePayload(CamelSchema):
    list: str
    key: str


class ProposalVocabularyMergePayload(CamelSchema):
    list: str
    key: str
    into: str


class ProposalTermCreatePayload(CamelSchema):
    dimension: str
    key: str
    labels: dict[str, str]
    usage_note: str = ""
    parent: str | None = None


class ProposalTermUpdatePayload(CamelSchema):
    dimension: str
    key: str
    labels: dict[str, str] = Field(default_factory=dict)
    usage_note: str | None = None
    sort_order: int | None = None


class ProposalPayload(CamelSchema):
    """The union as the contract states it: every field of every kind's payload, optional,
    with the kind saying which ones are read. Ninja flattens components, so one named
    object keeps the generated TypeScript honest without a discriminated union the client
    would have to narrow by hand."""

    list: str | None = None
    dimension: str | None = None
    key: str | None = None
    into: str | None = None
    parent: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    usage_note: str | None = None
    sort_order: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)  # schema: VocabularyExtra


class ProposalFieldSources(CamelSchema):
    """`field_sources`: per changed field, where the value came from (PRO-01). Chunk 2
    proposals carry none; the watch agent fills it from chunk 5 on."""

    fields: dict[str, str] = Field(default_factory=dict)


class ProposalRow(CamelSchema):
    id: UUID
    kind: str
    status: str
    title: str
    target_type: str = ""
    target_id: UUID | None = None
    change_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)  # schema: ProposalPayload
    field_sources: dict[str, Any] = Field(default_factory=dict)  # schema: ProposalFieldSources
    scope_suggestion: list[dict[str, Any]] = Field(default_factory=list)  # schema: TermRef (chunk 4 fills it)
    source_label: str = ""
    source_url: str = ""
    effective_from: date | None = None
    origin: str
    agent_run_id: UUID | None = None
    model: str = ""
    proposed_by: ProposalActorRef | None = None
    reviewed_by: ProposalActorRef | None = None
    reviewed_at: datetime | None = None
    rejection_code: str = ""
    review_note: str = ""
    applied_at: datetime | None = None
    created_at: datetime


class ProposalPage(CamelSchema):
    items: list[ProposalRow]
    total: int


class ProposalAccepted(CamelSchema):
    """202 from a library-list write (VOC-07): nothing changed, a proposal is waiting."""

    proposal: ProposalRow


class ProposalCreateBody(CamelSchema):
    kind: str
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)  # schema: ProposalPayload
    target_type: str = ""
    target_id: UUID | None = None
    change_id: UUID | None = None
    agent_run_id: UUID | None = None  # the run that produced it (agents, chunk 5)
    model: str = ""  # the model that drafted it (AUD-02; labelled until a person confirms)
    field_sources: dict[str, Any] = Field(default_factory=dict)  # schema: ProposalFieldSources
    source_label: str = ""
    source_url: str = ""
    effective_from: date | None = None


class ProposalApproveBody(CamelSchema):
    note: str = ""


class ProposalRejectBody(CamelSchema):
    rejection_code: str = ""
    note: str = ""


class ProposalQuery(CamelSchema):
    """Filters of the review queue, each optional: `status` and `kind` take one value or a
    comma-separated list; `targetList` is a vocabulary list name or a taxonomy dimension
    key and matches the proposals that change it (`payload.list` or `payload.dimension`)."""

    status: str | None = None
    kind: str | None = None
    target_list: str | None = None
