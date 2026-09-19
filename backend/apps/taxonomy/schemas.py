"""Request and response schemas of the taxonomy app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Nothing here declares an enum of vocabulary values (VOC-01, AC-VOC1): `kind` and `key` are
plain strings, so adding a change type or a tag never moves `openapi.json`. The tier-one
kinds stay in apps/shared/kinds.py and never reach the contract as an `enum` either, because
the rules read them off the row, not off the wire.
"""

from __future__ import annotations

import builtins
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from apps.shared.schemas import CamelSchema, VocabularyExtra, WriteBody

__all__ = ["CamelSchema"]


# ---------------------------------------------------------------------------------------
# References: what every picker, pill and filter reads (playbook 15: key and kind, never a
# phrase the client must string-match).
# ---------------------------------------------------------------------------------------
class TermRef(CamelSchema):
    key: str
    kind: str | None = None
    label: str


class PersonRef(CamelSchema):
    """A person on a record: id and name, the only personal data a screen or a log may carry
    about them (playbook 4.7)."""

    id: UUID
    name: str


class TaxonomyDimensionRef(CamelSchema):
    key: str
    kind: str | None = None
    label: str


class JurisdictionRow(CamelSchema):
    """`GET /reference/jurisdictions` (I18N-01). A reference read: a short fixed list that
    never paginates, like `GET /reference/languages` (INPUT_DELTAS §7)."""

    key: str
    kind: str | None = None
    label: str
    parent_key: str | None = None
    default_language: TermRef | None = None


# ---------------------------------------------------------------------------------------
# Vocabularies (VOC-01, VOC-02, VOC-03, VOC-07)
# ---------------------------------------------------------------------------------------
class VocabularyListEntry(CamelSchema):
    """One row of `GET /vocab`: the list of lists the admin screens and the agents read."""

    list: str
    tier: int
    kind: str | None = None  # the tier-one kind's INPUT_DELTAS §1 name, when rows carry one
    kinds: builtins.list[str] = Field(default_factory=builtins.list)  # the values that kind may take
    count: int
    retired_count: int
    proposable: bool


class VocabularyListPage(CamelSchema):
    items: list[VocabularyListEntry]
    total: int


class VocabularyRow(CamelSchema):
    """One vocabulary row as every surface reads it (playbook 15). `extra` carries the
    list's own columns (an urgency's ordinal and SLA days, a dimension's
    `restrictsFootprint`) so one schema serves every list and the contract does not grow a
    shape per list."""

    key: str
    kind: str | None = None
    label: str
    labels: dict[str, str] = Field(default_factory=dict)
    usage_note: str = ""
    sort_order: int = 0
    active: bool = True
    is_system: bool = False
    is_default: bool = False
    usage_count: int = 0
    version: int = 1
    extra: dict[str, Any] = Field(default_factory=dict)  # schema: VocabularyExtra


class VocabularyRowDetail(VocabularyRow):
    """`GET /vocab/{list}/{key}`: the row plus which label is the original and which are
    machine translations (I18N-01, D-12)."""

    original_language: str | None = None
    machine_languages: list[str] = Field(default_factory=list)


class VocabularyRowPage(CamelSchema):
    items: list[VocabularyRow]
    total: int


class VocabularyCreateBody(WriteBody):
    """`key` is optional: it is slugified from the English label when absent, because a
    person types a label and never a key. `force` is how a holder of vocab.manage insists
    past the near-duplicate hint (VOC-03, AC-VOC3)."""

    key: str | None = None
    labels: dict[str, str]
    usage_note: str = ""
    kind: str | None = None
    sort_order: int | None = None
    extra: VocabularyExtra = Field(default_factory=dict)
    force: bool = False


class VocabularyPatchBody(WriteBody):
    labels: dict[str, str] | None = None
    usage_note: str | None = None
    sort_order: int | None = None
    extra: VocabularyExtra | None = None


class VocabularyReorderBody(WriteBody):
    keys: list[str]


class VocabularyRetireBody(WriteBody):
    confirm: bool = False


class VocabularyRetired(CamelSchema):
    key: str
    usage_count: int
    retired: bool


class VocabularyRestored(CamelSchema):
    key: str
    usage_count: int
    restored: bool


class VocabularyMergeBody(WriteBody):
    into: str


class VocabularyMerged(CamelSchema):
    """Both the dry run and the commit answer this shape, so the screen renders one
    preview and one result from the same fields (playbook 15: dry run, preview, commit)."""

    from_: str = Field(alias="from")
    into: str
    usage_count: int
    repointed: int
    dry_run: bool


class VocabularySuggestBody(WriteBody):
    key: str | None = None
    labels: dict[str, str]
    usage_note: str = ""


class VocabularySuggestionRow(CamelSchema):
    id: UUID
    list: str
    key: str
    labels: dict[str, str] = Field(default_factory=dict)
    usage_note: str = ""
    suggested_by: PersonRef | None = None
    status: str
    created_at: datetime


class VocabularySuggestionPage(CamelSchema):
    items: list[VocabularySuggestionRow]
    total: int


# ---------------------------------------------------------------------------------------
# Taxonomy terms (library; every write is a proposal, VOC-07)
# ---------------------------------------------------------------------------------------
class TaxonomyTermRow(CamelSchema):
    id: UUID
    key: str
    kind: str | None = None
    label: str
    labels: dict[str, str] = Field(default_factory=dict)
    dimension: TaxonomyDimensionRef
    parent_key: str | None = None
    usage_note: str = ""
    sort_order: int = 0
    active: bool = True
    is_system: bool = False
    version: int = 1


class TaxonomyTermPage(CamelSchema):
    items: list[TaxonomyTermRow]
    total: int


class TaxonomyTermCreateBody(WriteBody):
    dimension: str
    key: str | None = None
    labels: dict[str, str]
    usage_note: str = ""
    parent: str | None = None


class TaxonomyDimensionPage(CamelSchema):
    items: list[VocabularyRow]
    total: int


# ---------------------------------------------------------------------------------------
# Footprint (FP-01, FP-02, FP-03)
# ---------------------------------------------------------------------------------------
class FootprintPreviewCount(CamelSchema):
    """What a change would hide and reveal for one record kind. `available` is false while
    the table does not exist yet (chunk 2 has no obligations or cases): zeros with
    `available:false` say "not counted", never "none" (playbook 4.4)."""

    hidden: int = 0
    revealed: int = 0
    available: bool = False


class FootprintPreview(CamelSchema):
    """The named schema behind `footprint_change_request.preview` (JSONField)."""

    obligations: FootprintPreviewCount = Field(default_factory=FootprintPreviewCount)
    cases: FootprintPreviewCount = Field(default_factory=FootprintPreviewCount)


class FootprintDimension(CamelSchema):
    dimension: TaxonomyDimensionRef
    restricts_footprint: bool
    terms: list[TermRef] = Field(default_factory=list)
    all_selected: bool = False


class FootprintTermRef(TermRef):
    dimension: str


class FootprintRequestRow(CamelSchema):
    id: UUID
    status: str
    requested_by: PersonRef | None = None
    requested_at: datetime
    adds: list[FootprintTermRef] = Field(default_factory=list)
    removes: list[FootprintTermRef] = Field(default_factory=list)
    preview: FootprintPreview
    decided_by: PersonRef | None = None
    decided_at: datetime | None = None
    decision_note: str = ""
    version: int = 1


class FootprintView(CamelSchema):
    dimensions: list[FootprintDimension]
    pending_request: FootprintRequestRow | None = None


class FootprintRequestPage(CamelSchema):
    items: list[FootprintRequestRow]
    total: int


class FootprintTermSelector(CamelSchema):
    dimension: str
    key: str


class FootprintRequestBody(CamelSchema):
    adds: list[FootprintTermSelector] = Field(default_factory=list)
    removes: list[FootprintTermSelector] = Field(default_factory=list)


class FootprintDecisionBody(CamelSchema):
    note: str = ""


class FootprintDryRun(CamelSchema):
    """`POST /tenant/footprint/requests?dryRun=true` (playbook 15: dry run, preview,
    commit): what the change would hide and reveal, with nothing persisted, no audit event
    and no approval started. The same `adds`, `removes` and `preview` the created request
    would carry, so the screen renders the preview and the request from one shape."""

    adds: list[FootprintTermRef] = Field(default_factory=list)
    removes: list[FootprintTermRef] = Field(default_factory=list)
    preview: FootprintPreview
    dry_run: bool = True


# ---------------------------------------------------------------------------------------
# Query parameters: camelCase on the wire like every other name (`includeRetired`, `dryRun`)
# ---------------------------------------------------------------------------------------
class VocabularyQuery(CamelSchema):
    include_retired: bool = False


class TaxonomyTermQuery(CamelSchema):
    dimension: str | None = None
    include_retired: bool = False


class VocabularyMergeQuery(CamelSchema):
    dry_run: bool = False


class FootprintRequestQuery(CamelSchema):
    dry_run: bool = False
