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
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

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
    """A taxonomy dimension as a reference: the group a term or a regulatory scope group
    belongs to (FP-01)."""

    key: str = Field(
        description=(
            "The dimension's immutable key, such as `service_type` or `standard`, and the only part of this "
            "reference to store, compare or send back. Dimensions are rows of the shared library's "
            "`term_dimension` vocabulary, which an administrator may extend through an approved proposal, "
            "so a key you have not seen before is new data and not an error; `GET /taxonomy/dimensions` "
            "lists the live set."
        ),
        examples=["service_type"],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "How the dimension's terms act on a bank's regulatory scope, one of three fixed values. "
            "`scope`: the dimension says who or what a rule covers, and a scope group with no term chosen "
            "restricts nothing. `classification`: the dimension only describes a record and never narrows "
            "the scope. `opt_in`: the standards a bank follows, where a record carrying one of the "
            "dimension's terms shows only to a bank whose scope names that term, so a group with no term "
            "chosen means none followed rather than no restriction. Every dimension carries a kind, so the "
            "default of null never reaches a reader. It is a kind in code, so the rules branch on it; an "
            "administrator never adds a value."
        ),
        examples=["scope"],
    )
    label: str = Field(
        description=(
            "The dimension's name in the reader's language, for display only. It is a phrase a person wrote "
            "and may be reworded or translated at any time, so nothing may match on it."
        ),
        examples=["Service"],
    )


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
    """`GET /vocab/{list}/suggestions`: one page of the suggestions waiting in one of the
    organisation's own lists, oldest first."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "6d2f9a14-8b3e-4c71-a5d0-3e9b1f7c2a58",
                            "list": "tenant_tag",
                            "key": "pension_transfers",
                            "labels": {"en": "Pension transfers"},
                            "usageNote": "Moving an occupational pension from one provider to another.",
                            "suggestedBy": {"id": "0b7e4c2d-9f61-4a38-b5e2-7c1d8a3f6e90", "name": "Oskar Lund"},
                            "status": "pending",
                            "createdAt": "2026-09-18T10:12:00Z",
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )

    items: list[VocabularySuggestionRow] = Field(
        description=(
            "This page of the list's waiting suggestions, oldest first, at most `limit` of them. Only a "
            "suggestion an admin has not answered yet is here: one whose row was created, or that was "
            "declined, has left the inbox."
        )
    )
    total: int = Field(
        description="How many suggestions wait in this list across every page, counted at the moment of the call."
    )


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
    mirrored: bool = Field(
        default=False,
        description=(
            "True for a term of the dimension that mirrors the markets the platform covers: "
            "the reference data keeps those terms in step with the jurisdiction list, so none "
            "is proposed, renamed or put on a change or an obligation, and a write that names "
            "one answers 422 `jurisdiction_term_mirrored`. A record's market comes from its "
            "instrument or its authority instead. False for every other term."
        ),
        examples=[False],
    )


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
    """One group of the regulatory scope (FP-01): a taxonomy dimension, whether it narrows
    the scope, and the terms this bank has chosen in it. The dimension's kind says how an
    empty group reads: no restriction for a scope dimension, none followed for an opt-in one."""

    dimension: TaxonomyDimensionRef = Field(
        description=(
            "The taxonomy dimension this group covers: its key, its kind and its label in the caller's "
            "language. The kind is `scope` for a dimension that says who or what a rule covers, "
            "`classification` for one that only describes a record and never narrows the scope, and "
            "`opt_in` for the standards a bank follows, where a record carrying one of the dimension's "
            "terms shows only when this group names that term, so an empty group means none followed "
            "rather than no restriction. Dimensions are rows of the shared library's `term_dimension` "
            "vocabulary, which an administrator may extend through an approved proposal; "
            "`GET /taxonomy/dimensions` lists the live set."
        )
    )
    restricts_footprint: bool = Field(
        description=(
            "True when the terms chosen in this group narrow what the bank sees. False for a dimension "
            "that only describes records, which never hides anything. Always true for an `opt_in` "
            "dimension, whatever its own flag says. A library fact, changed only through an approved "
            "proposal."
        )
    )
    terms: list[TermRef] = Field(
        default_factory=list,
        description=(
            "The terms this bank has chosen in the group, each its key and its label in the caller's "
            "language, in picker order; empty when it has chosen none. Terms are rows of the shared "
            "library's taxonomy vocabulary, which an administrator may extend through an approved "
            "proposal; `GET /taxonomy/terms` lists the live set. Changed only through a regulatory "
            "scope change request with its preview, second person and step-up."
        )
    )
    all_selected: bool = Field(
        default=False,
        description=(
            "True when the bank has chosen every active term of the dimension, which the screen reads "
            "as all selected. Defaults to false, also for a dimension that has no active terms."
        ),
    )


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


MarketLevel = Literal["operating", "watching", "not_followed"]


class MarketRow(CamelSchema):
    """One active country's market level (FP-04), computed fresh on every read and never
    stored, so it cannot drift from the two facts it is read from: the tenant's regulatory
    scope, which only a footprint change request changes (FP-02), and the tenant's watch
    list, a direct write that hides nothing."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"jurisdiction": {"key": "no", "kind": "country", "label": "Norway"}, "level": "watching"}]}
    )

    jurisdiction: TermRef = Field(
        description=(
            "The country: its key, kind (always `country`) and label in the caller's language. A row of "
            "the jurisdiction vocabulary; an admin may add more without a deploy, and `GET /reference/jurisdictions` "
            "lists the live set."
        )
    )
    level: MarketLevel = Field(
        description=(
            "How closely the tenant follows this country, computed by the server on every read and never stored. "
            "Operating comes first, then watching:\n"
            "- `operating`: the country's mirrored jurisdiction term is in the tenant's regulatory scope, so its "
            "rules are part of what applies. Changes only through a footprint change request with its preview, "
            "second person and step-up.\n"
            "- `watching`: not operating, and the tenant has a `watched_market` row naming the country, set directly "
            "with `POST /tenant/footprint/watching` with no second person and no step-up, because watching hides "
            "nothing. A country watched before it started operating reads as `watching` again once operating stops.\n"
            "- `not_followed`: neither; approving or reversing a scope change never writes a watch row, so a country "
            "never watched drops back here when operating stops.\n"
            "Operating or watching says nothing about whether the tenant complies with anything there."
        ),
        examples=["operating"],
    )


class MarketWatchBody(WriteBody):
    """`POST /tenant/footprint/watching` and `POST /tenant/footprint/watching/remove`
    (FP-04): the jurisdiction key rides in the body on both routes, never in the path or a
    query string, because the tenant's watch list is sensitive and does not belong on an
    access log line."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"jurisdiction": "no"}]})

    jurisdiction: str = Field(
        min_length=1,
        max_length=80,
        description=(
            "The key of a row of the jurisdiction vocabulary naming a country, at most 80 characters, "
            "such as `no` for Norway (`GET /reference/jurisdictions` lists the live rows; an admin may "
            "add more without a deploy). The union itself, an unknown or inactive key, or a supranational "
            "key answers 422 `unknown_key` or `not_a_country`."
        ),
        examples=["no"],
    )


class FootprintView(CamelSchema):
    dimensions: list[FootprintDimension]
    pending_request: FootprintRequestRow | None = None
    markets: list[MarketRow] = Field(
        default_factory=list,
        description="Every active country's operating and watching level, one row per country, in jurisdiction sort order (FP-04).",
    )


class FootprintRequestPage(CamelSchema):
    """`GET /tenant/footprint/requests`: one page of the organisation's regulatory scope
    change requests, newest first."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "5b0c7e1a-3f2d-4c8e-9a61-2d7f0e4b9c13",
                            "status": "pending",
                            "requestedBy": {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lindqvist"},
                            "requestedAt": "2026-09-18T07:40:00Z",
                            "adds": [
                                {"key": "insurance_distribution", "kind": None, "label": "Insurance distribution", "dimension": "service_type"},
                                {"key": "retail", "kind": None, "label": "Retail", "dimension": "client_category"},
                            ],
                            "removes": [{"key": "advice", "kind": None, "label": "Advice", "dimension": "service_type"}],
                            "preview": {
                                "obligations": {"hidden": 2, "revealed": 2, "available": True},
                                "cases": {"hidden": 0, "revealed": 0, "available": False},
                            },
                            "decidedBy": None,
                            "decidedAt": None,
                            "decisionNote": "",
                            "version": 1,
                        },
                        {
                            "id": "e41f7b2c-6a95-4d08-b3c1-9f2e8d7a6b54",
                            "status": "rejected",
                            "requestedBy": {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lindqvist"},
                            "requestedAt": "2026-09-01T13:20:00Z",
                            "adds": [],
                            "removes": [{"key": "tax", "kind": None, "label": "Tax", "dimension": "regime"}],
                            "preview": {
                                "obligations": {"hidden": 3, "revealed": 0, "available": True},
                                "cases": {"hidden": 0, "revealed": 0, "available": False},
                            },
                            "decidedBy": {"id": "c7d2e9a1-4b6f-4c83-a0e5-6f1b9d2c8e47", "name": "Maria Ek"},
                            "decidedAt": "2026-09-02T07:40:00Z",
                            "decisionNote": "ISK tax reporting is ours.",
                            "version": 2,
                        },
                    ],
                    "total": 2,
                }
            ]
        }
    )

    items: list[FootprintRequestRow] = Field(
        description=(
            "This page of the organisation's regulatory scope change requests, newest first, at most "
            "`limit` of them: the one waiting for a second person, if there is one, and every request "
            "already approved, rejected or withdrawn. A decided request is never deleted."
        )
    )
    total: int = Field(
        description="How many change requests the organisation has sent in all, across every page, counted at the moment of the call."
    )


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
    dry_run: bool = Field(
        default=False,
        description=(
            "True previews the change and stores nothing: the answer is a 200 with what it would hide "
            "and reveal, no request is created, no second person is asked and no audit event is written. "
            "False, the default, sends the request for approval and answers 201."
        ),
    )
