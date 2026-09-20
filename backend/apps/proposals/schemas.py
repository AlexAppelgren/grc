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

from django.conf import settings
from pydantic import Field, RootModel

from apps.shared.schemas import CamelSchema, WriteBody

__all__ = ["CamelSchema"]


# Scope terms as `dimension:key`. Spelled here because `ProposalPayload` has a field named
# `list`, which shadows the builtin inside that class body.
TermRefs = list[str]


class ProposalActorRef(CamelSchema):
    id: UUID
    name: str


# ---------------------------------------------------------------------------------------
# Payloads, one named schema per kind (PRO-01). `list` is a vocabulary list name from
# apps/taxonomy/registry.py; `key` is the immutable key the row will carry forever.
# ---------------------------------------------------------------------------------------
class ProposalVocabularyCreatePayload(WriteBody):
    list: str
    key: str
    labels: dict[str, str]
    usage_note: str = ""
    kind: str | None = None
    sort_order: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)  # schema: VocabularyExtra


class ProposalVocabularyRelabelPayload(WriteBody):
    list: str
    key: str
    labels: dict[str, str] = Field(default_factory=dict)
    usage_note: str | None = None
    sort_order: int | None = None
    extra: dict[str, Any] | None = None  # schema: VocabularyExtra


class ProposalVocabularyRetirePayload(WriteBody):
    list: str
    key: str


class ProposalVocabularyMergePayload(WriteBody):
    list: str
    key: str
    into: str


class ProposalTermCreatePayload(WriteBody):
    dimension: str
    key: str
    labels: dict[str, str]
    usage_note: str = ""
    parent: str | None = None


class ProposalTermUpdatePayload(WriteBody):
    dimension: str
    key: str
    labels: dict[str, str] = Field(default_factory=dict)
    usage_note: str | None = None
    sort_order: int | None = None


class ProposalObligationVersionPayload(WriteBody):
    """`new_obligation_version` (PRO-01, INV-04): the summary that comes into force on a
    date, and the scope terms that come with it.

    `summaries` is the text per content language, never a `summaryEn` column (I18N-01);
    `originalLanguage` is the one that was written rather than translated and must be one
    of them, and `isMachine` says the translations are machine-made until a person
    confirms them (AUD-02). The date is a plain legal date with a precision (INV-S10).
    `terms` are the obligation's scope facets as `dimension:key`; leaving it out leaves
    the scope alone.

    Every field here is a field the library will carry, so each one needs its source in
    `fieldSources` (`sourced_fields()` in apps/proposals/logic.py names them).
    """

    summaries: dict[str, str]
    original_language: str
    is_machine: bool = False
    effective_from: date | None = None
    effective_from_precision: str = "day"
    terms: TermRefs | None = Field(default=None, max_length=settings.PROPOSAL_SCOPE_MAX_TERMS)


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
    summaries: dict[str, str] = Field(default_factory=dict)
    original_language: str | None = None
    is_machine: bool | None = None
    effective_from: date | None = None
    effective_from_precision: str | None = None
    terms: TermRefs = []


class ProposalFieldSources(RootModel[dict[str, str]]):
    """`field_sources`: per changed field, the source its value came from (PRO-01). The
    vocabulary kinds carry none; an obligation proposal carries one per field it changes
    (`summaries.<language>`, `effectiveFrom`, `terms`) and none for a field it does not,
    or it is refused. A source is an https link or the stable key of a provision the
    library holds, at most `PROPOSAL_SOURCE_MAX_CHARS` long."""


class ProposalRow(CamelSchema):
    id: UUID
    kind: str
    status: str
    title: str
    target_type: str = ""
    target_id: UUID | None = None
    change_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)  # schema: ProposalPayload
    field_sources: dict[str, str] = Field(default_factory=dict)  # schema: ProposalFieldSources
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


class ProposalCreateBody(WriteBody):
    kind: str
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)  # schema: ProposalPayload
    target_type: str = ""
    target_id: UUID | None = None
    change_id: UUID | None = None
    agent_run_id: UUID | None = None  # the run that produced it (agents, chunk 5)
    model: str = ""  # the model that drafted it (AUD-02; labelled until a person confirms)
    field_sources: dict[str, str] = Field(default_factory=dict)  # schema: ProposalFieldSources
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
