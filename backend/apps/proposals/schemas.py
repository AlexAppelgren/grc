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
from pydantic import ConfigDict, Field, RootModel

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
    """One row of the review queue: a change somebody wants made to the shared library,
    and how far it has got. Every field is the proposal's own record of the request, not
    the library: until `status` is `approved` the library still says what it said before,
    and a reader must not quote a proposal as the law. The whole row is platform data; a
    bank sees a proposal of its own only through `GET /tenant/proposals`.

    Read-only and written by the server. Nothing here is a bank's judgement about whether
    a duty applies to it: that is the bank's own zone and never travels with a proposal.
    """

    id: UUID = Field(description="The proposal, as the console addresses it: a UUID the server assigns once and never changes.")
    kind: str = Field(
        description=(
            "What the proposal changes, and therefore which fields of `payload` are read. A fixed kind, "
            "not a vocabulary row: `new_obligation_version` adds a version to an obligation that exists, "
            "`vocabulary_create` adds a row to a library list, `vocabulary_relabel` rewords one, "
            "`vocabulary_retire` and `vocabulary_restore` turn one off and on again, `vocabulary_merge` "
            "points a row's users at another row and retires it, and `term_create` and `term_update` do "
            "the same for a taxonomy term. The other kinds of the data model are not built yet, so a "
            "reader must not treat this list as the full set for ever."
        )
    )
    status: str = Field(
        description=(
            "Where the request stands. A fixed kind: `open` is waiting for a reviewer, `approved` means "
            "the library carries it and `appliedAt` says when, `rejected` means it was refused with a "
            "reason and changed nothing, and `superseded` means a later proposal overtook it. Only "
            "`approved` says anything about what the library holds."
        )
    )
    title: str = Field(
        description=(
            "The one-line request as its author wrote it: an agent's own wording, or a platform "
            "editor's. It is never a bank member's words, because a proposal made inside a bank reaches "
            "the console without its proposer, and it is not the library record's title."
        )
    )
    target_type: str = Field(default="", description="What the proposal changes, when it changes a record that already exists: `obligation` today, empty for a proposal that creates something.")
    target_id: UUID | None = Field(default=None, description="The library record the proposal changes, as a UUID, or null when it creates one. Read the record itself for what it currently says.")
    change_id: UUID | None = Field(default=None, description="The regulatory change that prompted this, as a UUID, when an agent's watch run found one. Null means nobody linked one, not that no change exists.")
    payload: dict[str, Any] = Field(  # schema: ProposalPayload
        default_factory=dict,
        description=(
            "What was proposed, in the shape its `kind` names (`ProposalPayload`). This is the request "
            "as it arrived, kept unchanged for the audit trail even when a reviewer corrected it before "
            "approving: it is not necessarily what the library now holds."
        ),
    )
    field_sources: dict[str, str] = Field(  # schema: ProposalFieldSources
        default_factory=dict,
        description=(
            "Per changed field, where its value came from: an https link or the stable key of a "
            "provision the library holds, at most "
            f"{settings.PROPOSAL_SOURCE_MAX_CHARS} characters. An obligation proposal carries one for "
            "every field it changes or it is refused; the vocabulary kinds, whose wording a person "
            "writes, carry none. A source is the authority's page, not our reading of it."
        ),
    )
    scope_suggestion: list[dict[str, Any]] = Field(  # schema: TermRef (chunk 4 fills it)
        default_factory=list,
        description="Scope terms an agent suggests for a record it is creating. Always empty today, since the kinds that would carry one are not built: an empty list is not a claim that a record has no scope.",
    )
    source_label: str = Field(default="", description="How the proposal names its source in a sentence a reviewer can read, for example \"Finansinspektionen, board decision 15 September 2026\". Written by the proposer, so it is a claim to check against `sourceUrl`, not a verified fact.")
    source_url: str = Field(default="", description="The page the proposal was drawn from, for a reviewer to open. An agent wrote it; that the link resolves says nothing about whether it supports the change.")
    effective_from: date | None = Field(default=None, description="The legal date the proposed change comes into force, as the proposal states it. A plain date, never a timestamp, and null when the proposal names none. Read the library record for the dates actually in force.")
    origin: str = Field(
        description=(
            "Who made it. A fixed kind: `agent` means a watch or research agent drafted it, which is AI "
            "output and stays labelled until a person confirms it by approving; `user` means a person "
            "typed it. Neither tells a reader whether the facts are right."
        )
    )
    agent_run_id: UUID | None = Field(default=None, description="The agent run that produced the proposal, as a UUID the run log addresses. Null for a person's proposal.")
    model: str = Field(default="", description="The model that drafted the text, recorded because AI output is labelled until a person confirms it (AUD-02). Empty means no model was named, not that no model was used.")
    proposed_by: ProposalActorRef | None = Field(
        default=None,
        description=(
            "The platform person who made the proposal. Null for an agent's proposal, and null for one "
            "made inside a bank: a bank member's name and id never reach the console. A reader must not "
            "read null as \"nobody\"."
        ),
    )
    reviewed_by: ProposalActorRef | None = Field(default=None, description="The platform reviewer who decided it. Always a different person from the proposer, which the database enforces. Null while the proposal is open.")
    reviewed_at: datetime | None = Field(default=None, description="When the decision was made: a UTC timestamp, date and time together. Null while the proposal is open.")
    rejection_code: str = Field(
        default="",
        description=(
            "Why it was refused: the key of a row of the `rejection_reason` library list, which an admin "
            "may extend, so a client stores and compares the key and shows the label the list gives. The "
            "keys seeded on day one are `wrong_fact`, `wrong_scope`, `bad_source`, `duplicate`, "
            "`not_relevant`, `poor_wording` and `other`. Empty unless the status is `rejected`."
        ),
    )
    review_note: str = Field(default="", description="The reviewer's own sentence to the proposer, on an approval or a rejection. A platform person's words; it is not part of the library record.")
    applied_at: datetime | None = Field(default=None, description="When the change reached the library: a UTC timestamp, date and time together, which is the moment of approval. Null unless the status is `approved`.")
    created_at: datetime = Field(description="When the proposal was filed: a UTC timestamp, date and time together. Not the legal date of the change, which is `effectiveFrom`.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "8f1d6d9e-58f0-4c2e-9e2f-6a4a6f1b8c21",
                    "kind": "new_obligation_version",
                    "status": "open",
                    "title": "Add version 2 of the research payment obligation, in force 1 October 2026",
                    "targetType": "obligation",
                    "targetId": "3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44",
                    "changeId": "b7e1c0a4-9f3d-4f6a-9c21-5d8e2f0a1b33",
                    "payload": {
                        "summaries": {
                            "sv": "Investeringsanalys från tredje part får tas emot endast om den betalas med institutets egna medel, från ett analyskonto, eller gemensamt med orderutförande enligt de villkor som anges i reglerna.",
                            "en": "Research from third parties may be received only if it is paid from the institution's own resources, from a research payment account, or jointly with execution under the conditions set out in the rules.",
                        },
                        "originalLanguage": "sv",
                        "isMachine": True,
                        "effectiveFrom": "2026-10-01",
                        "effectiveFromPrecision": "day",
                    },
                    "fieldSources": {
                        "summaries.sv": "https://www.fi.se/",
                        "summaries.en": "https://www.fi.se/",
                        "effectiveFrom": "https://www.fi.se/",
                    },
                    "scopeSuggestion": [],
                    "sourceLabel": "Finansinspektionen, board decision 15 September 2026",
                    "sourceUrl": "https://www.fi.se/",
                    "effectiveFrom": "2026-10-01",
                    "origin": "agent",
                    "agentRunId": "5a2b9c7d-1e3f-4a8b-9c0d-2e4f6a8b0c12",
                    "model": "agent pipeline 0.4",
                    "proposedBy": None,
                    "reviewedBy": None,
                    "reviewedAt": None,
                    "rejectionCode": "",
                    "reviewNote": "",
                    "appliedAt": None,
                    "createdAt": "2026-09-16T07:12:00Z",
                }
            ]
        }
    )


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


class ProposalApproveBody(WriteBody):
    """The body of `POST /proposals/{proposalId}/approve`: the reviewer's word that this
    change may enter the shared library, and the corrections they made first.

    Approving is the only door into the library, so this call needs `proposals.review`
    and a passkey step-up no older than the step-up window; without a fresh assertion it
    answers 403 `step_up_required`, and the assertion's id is written on every audit row
    the approval leaves. The reviewer is never the proposer: the database refuses that row
    and the call answers 409 `four_eyes_violation`. Approval carries no
    `Idempotency-Key` and no `If-Match`: a proposal is decided once, and a second call on
    a decided proposal answers 409 `invalid_transition` rather than applying anything
    twice. The audit and outbox rows the approval writes are append-only.

    The whole call is platform work in the shared zone. Neither field ever names the bank
    a proposal came from, because a bank member's identity does not reach the console, and
    nothing a bank wrote about its own compliance is touched by an approval.
    """

    note: str = Field(
        default="",
        description=(
            "The reviewer's own sentence to the proposer, stored on the proposal and sent to them with "
            "the decision. Optional on an approval, unlike a rejection, which needs a reason and a note. "
            "It is the reviewer's comment on the request and never becomes part of the library record's "
            "text, so a reader must not quote it as what the authority said."
        ),
    )
    payload_overrides: dict[str, Any] | None = Field(  # schema: ProposalPayload
        default=None,
        description=(
            "The reviewer's corrections, merged field by field over the proposal's own payload before it "
            "is applied; the fields left out keep what was proposed. Accepted only for the "
            "`new_obligation_version` kind, since the vocabulary kinds carry a label a person wrote "
            "rather than a sourced fact; on any other kind the call answers 422 `validation_error`. The "
            "fields a reviewer may correct are the ones that kind's payload names: `summaries` (the "
            "whole set of texts per language, which replaces the proposed set), `originalLanguage`, "
            "`isMachine`, `effectiveFrom`, `effectiveFromPrecision` (one of `day`, `month`, `quarter` "
            "and `year`, which says how exactly the date is known) and `terms` (the scope facets as "
            f"`dimension:key`, at most {settings.PROPOSAL_SCOPE_MAX_TERMS}, which replace the "
            "obligation's scope). The merged payload must still carry a source for every field it "
            "changes, so a correction that introduces a field the proposal never sourced answers 422 "
            "`source_missing` and applies nothing. What is applied is kept beside what was proposed, as "
            "the reviewer's own correction: a reader must not take the proposal's payload as the text "
            "the library now holds."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "note": "Wording follows the board decision; scope narrowed to the retail categories the decision names.",
                    "payloadOverrides": {
                        "summaries": {
                            "sv": "Investeringsanalys från tredje part får tas emot endast om den betalas med institutets egna medel eller från ett analyskonto.",
                            "en": "Research from third parties may be received only if it is paid from the institution's own resources or from a research payment account.",
                        },
                        "effectiveFrom": "2026-10-01",
                    },
                }
            ]
        }
    )


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
