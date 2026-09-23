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

from apps.library.schemas import AgentRef, DiffSegment, LibraryRef, LocalizedText, OutsideReason, PartialDate
from apps.shared.schemas import CamelSchema, WriteBody

__all__ = ["CamelSchema"]


# Scope terms as `dimension:key`. Spelled here because `ProposalPayload` has a field named
# `list`, which shadows the builtin inside that class body.
TermRefs = list[str]
# A plain date, under a second name, because `LibraryUpdateDay` has a field called `date`,
# which shadows the type inside that class body exactly as `list` does above.
DayDate = date


class ProposalActorRef(CamelSchema):
    """A platform person named on a proposal: who filed it, who corrected it or who decided
    it. Always bleqq's own staff and never a bank member, whose name and id do not reach the
    console (PRO-03)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"id": "0b6f2c4e-8d1a-4f3b-9e27-5c8a1d3f6b90", "name": "Kari Nygaard"}]})

    id: UUID = Field(description="The person's platform account, as a UUID that never changes. Compare this, never the name, to tell whether two proposals were handled by the same person.")
    name: str = Field(description="The person's name as their platform account spells it today, for showing on screen. It may change; the audit trail keeps the name it had at the time.")


class ProposalAgentRef(CamelSchema):
    """One of the platform's agents named on a proposal: the agent that filed it, or the
    independent agent that decided it (D-62). An agent's decision is machine-confirmed and
    never reads as a person's; the record it applied says so on its own provenance."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"key": "library-confirmer", "version": 1}]})

    key: str = Field(
        description=(
            "The agent definition's own key, stable and never changed, for example `watch-sweeper`: the folder its "
            "versioned definition lives in. Store and compare this, and show it to name the agent. Two proposals "
            "naming the same key were handled by the same agent, whichever of its keys it called with."
        ),
        examples=["library-confirmer"],
    )
    version: int = Field(
        description=(
            "The version of the definition the platform runs for this agent now, counting from 1. It is not "
            "necessarily the version that filed or decided this proposal: a later release may have moved on, and "
            "only the audit row of the decision keeps the version the agent ran when it decided."
        ),
        examples=[1],
    )


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
            "output and stays labelled: a person's approval confirms it, and an independent agent's "
            "approval leaves the record machine-confirmed, naming both agents, never confirmed by a "
            "person. `user` means a person typed it. Neither tells a reader whether the facts are right."
        )
    )
    agent_run_id: UUID | None = Field(default=None, description="The agent run that produced the proposal, as a UUID the run log addresses. Null for a person's proposal.")
    model: str = Field(default="", description="The model that drafted the text, recorded because AI output is labelled until a person confirms it (AUD-02). Empty means no model was named, not that no model was used.")
    proposed_by: ProposalActorRef | None = Field(
        default=None,
        description=(
            "The platform person who made the proposal. Null for an agent's proposal, which "
            "`proposedByAgent` names instead, and null for one made inside a bank: a bank member's name "
            "and id never reach the console. A reader must not read null as \"nobody\"."
        ),
    )
    proposed_by_agent: ProposalAgentRef | None = Field(
        default=None,
        description=(
            "The platform agent that filed the proposal, by definition key, when the key it called with is "
            "bound to one. Null for a person's proposal, for one made inside a bank, whichever of its people "
            "or keys filed it, and for a key bound to no agent. Four eyes compares this with the reviewing "
            "agent: no key of the same definition may decide it."
        ),
    )
    from_organisation: bool = Field(
        default=False,
        description=(
            "True when the proposal was made inside a bank, by one of its people or by an agent "
            "of theirs, in which case `proposedBy` is null however the reader is signed in: a bank "
            "member's name and id never reach the platform console, and which bank it was is not "
            "told either. False means it was made by platform staff or by a platform agent, and "
            "`proposedBy` is then the person, or null for an agent."
        ),
        examples=[False],
    )
    reviewed_by: ProposalActorRef | None = Field(
        default=None,
        description=(
            "The platform person who decided it, never the person who proposed it, which the database "
            "enforces. Null while the proposal is open, and null when an independent agent decided it, "
            "which `reviewedByAgent` then names: a decided proposal names exactly one of the two."
        ),
    )
    reviewed_by_agent: ProposalAgentRef | None = Field(
        default=None,
        description=(
            "The independent agent that decided it, by definition key: never the proposing key and never "
            "another key of the proposing agent's definition, which the database enforces. Null while the "
            "proposal is open and when a person decided it. An agent's approval is machine-confirmed: the "
            "record it applied reads as confirmed by that agent and never as verified by a person."
        ),
    )
    corrected_by: ProposalActorRef | None = Field(
        default=None,
        description=(
            "The person who corrected the payload on the way to approving it, which is always the person "
            "who approved it. Null when nobody corrected it, and null when the approving agent did, which "
            "`correctedByAgent` then names."
        ),
    )
    corrected_by_agent: ProposalAgentRef | None = Field(
        default=None,
        description=(
            "The independent agent that corrected the payload on the way to approving it, which is always "
            "the agent that approved it. Null when nobody corrected it and when a person did. What was "
            "proposed stays in `payload` beside the correction, so the audit trail keeps both."
        ),
    )
    reviewed_at: datetime | None = Field(default=None, description="When the decision was made, by a person or by an agent: a UTC timestamp, date and time together. Null while the proposal is open.")
    rejection_code: str = Field(
        default="",
        description=(
            "Why it was refused: the key of a row of the `rejection_reason` library list, which an admin "
            "may extend, so a client stores and compares the key and shows the label the list gives. The "
            "keys seeded on day one are `wrong_fact`, `wrong_scope`, `bad_source`, `duplicate`, "
            "`not_relevant`, `outside_sector_scope`, `poor_wording` and `other`. Empty unless the status is "
            "`rejected`."
        ),
    )
    review_note: str = Field(default="", description="The reviewer's own sentence to the proposer, on an approval or a rejection: a platform person's words, or the deciding agent's output when an agent decided, which is AI output like any other. It is not part of the library record.")
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
                    "proposedByAgent": {"key": "watch-sweeper", "version": 1},
                    "fromOrganisation": False,
                    "reviewedBy": None,
                    "reviewedByAgent": None,
                    "correctedBy": None,
                    "correctedByAgent": None,
                    "reviewedAt": None,
                    "rejectionCode": "",
                    "reviewNote": "",
                    "appliedAt": None,
                    "createdAt": "2026-09-16T07:12:00Z",
                }
            ]
        }
    )


class ProposalTarget(CamelSchema):
    """The library record a proposal changes, as the queue names it in a row: the record's
    own title and reference, never the proposal's wording. Null on a proposal that changes a
    vocabulary list rather than a record; `payload.list` and `payload.key` name that row."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44",
                    "title": "Pay for third-party research only under the permitted models",
                    "referenceLabel": "Third-party payments",
                    "instrumentShortName": "FFFS 2017:2",
                }
            ]
        }
    )

    id: UUID = Field(description="The library record this proposal changes, as a UUID, which is the id `GET /obligations/{obligationId}` takes.")
    title: str = Field(
        description=(
            "The record's own title, in the best language this reader has (the original where "
            "there is no translation). It is the library's wording and not the proposal's, so a "
            "reader sees which duty is being changed rather than how the proposer described it."
        )
    )
    reference_label: str = Field(
        description=(
            "How the record is cited inside its instrument, for example \"Third-party payments\": "
            "the short reference a person uses to find the duty in the text. Empty when the record "
            "carries none."
        )
    )
    instrument_short_name: str = Field(
        description="The short name of the law, regulation or guideline the duty was broken out of, for example \"FFFS 2017:2\", so a row says which text is changing."
    )


class ProposalSource(CamelSchema):
    """Where one changed field's value came from (PRO-01): a source a reviewer opens before
    they approve. It is the proposer's claim about provenance, checked by a person, and never
    a guarantee that the source says what the proposal says."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "field": "summaries.sv",
                    "label": "Finansinspektionen, board decision 15 September 2026",
                    "url": "https://www.fi.se/",
                }
            ]
        }
    )

    field: str = Field(
        description=(
            "The field of the payload this source belongs to, spelled as the payload spells it: "
            "`summaries.<language>` for the text in one content language, `effectiveFrom` for the "
            "date the change binds from, and `terms` for the scope facets."
        )
    )
    label: str = Field(
        description=(
            "The source in a sentence a reviewer can read, which is the proposal's own "
            "`sourceLabel` for a link, or the stable key of the provision when the source is one "
            "the library already holds. Written by the proposer, so it is a claim to check."
        )
    )
    url: str = Field(
        description=(
            "The page to open, when the source is a link. Empty when the source is a provision of "
            "the library instead, which `label` then names by its stable key."
        ),
        examples=["https://www.fi.se/"],
    )


class ProposalAppliedVersion(CamelSchema):
    """The library version an approved proposal wrote (PRO-02, INV-04). Null until the
    proposal is approved; a rejected proposal never has one."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"id": "1f0b3e7c-4a1b-4f9e-8a21-6d4b2c0a9e17", "versionNumber": 2, "effectiveFrom": "2026-10-01"}]}
    )

    id: UUID = Field(description="The version row this approval created, as a UUID the obligation's own read returns beside its number.")
    version_number: int = Field(
        description="Which version of the record it is, counting from 1 upwards in the order the versions were filed, so version 2 is the first change after the record entered the library.",
        examples=[2],
    )
    effective_from: date | None = Field(
        default=None,
        description="The legal date this version starts binding the bank, as a plain date and never a timestamp. Null when it has been in force since the record entered the library.",
        examples=["2026-10-01"],
    )


class ProposalQueueRow(ProposalRow):
    """One row of the console queue: the proposal, plus what a reviewer needs to tell the
    rows apart without opening each one. Platform data throughout; a bank reads its own
    proposals through `GET /tenant/proposals`, which answers a narrower row."""

    target: ProposalTarget | None = Field(
        default=None,
        description=(
            "The library record being changed, by its own title and reference. Null when the "
            "proposal changes a vocabulary list rather than a record, and null when the record "
            "was withdrawn from the library after the proposal was filed."
        ),
    )
    is_mine: bool = Field(
        default=False,
        description=(
            "True when the reader filed this proposal themselves, worked out by the server from who "
            "called and never sent by the client: for a person, the person who filed it; for an "
            "agent's key, the same key or any key of the same agent definition. Four eyes means the "
            "reader may not decide it, and their approval answers 409 `four_eyes_violation`, so a "
            "screen hides the control rather than offering a refusal. Always false for a proposal "
            "made inside a bank, which no platform reader filed, and exactly the rows `notMine` drops."
        ),
        examples=[False],
    )


class ProposalDetail(ProposalQueueRow):
    """One proposal opened for a decision (PRO-02): everything the row carries, plus what the
    library says against what the proposal would make it say, and where each changed value
    came from. Read it before approving; approving is the only door into the shared library.

    What it is compared with depends on where it stands. Only an approved proposal is pinned:
    it is read against the version numbered just before the one it wrote, and its scope
    against the scope the approval found, so that comparison stays the same whatever the
    calendar or a later version says. A proposal that was not approved, open or rejected, is
    read against the version in force today and the scope the record carries now, so its
    comparison moves when a version comes into force or another is approved; while an
    approved version still waits for its date, an open proposal's diff shows that version's
    changes as well as its own."""

    language: str = Field(
        default="",
        description=(
            "The content language the texts and the diff below are written in: the language the "
            "proposal was drafted in, which is the one a reviewer judges the wording in. A "
            "two-letter code from the content languages (`GET /reference/languages`). Empty on a "
            "proposal that changes no text, such as a vocabulary change."
        ),
        examples=["sv"],
    )
    current_summary: LocalizedText | None = Field(
        default=None,
        description=(
            "The wording the proposal is compared with, in the language above. For a proposal "
            "that was not approved, open or rejected, it is the summary of the version in force "
            "today, or of the latest version when every version starts later, so it moves when a "
            "version comes into force or another is approved. For an approved one it is the summary "
            "of the version before the one the approval wrote, so it does not move when that version "
            "comes into force or a later one arrives. Null when that version has no text in this "
            "language, when there is no earlier version, and on a proposal that changes no record text."
        ),
    )
    proposed_text: str = Field(
        default="",
        description=(
            "The wording that would replace it, which is the reviewer's own correction where one "
            "has been made and the proposal's text otherwise. Empty on a proposal that changes no "
            "record text. It is a request, not the library: until the proposal is approved the "
            "library still says what `currentSummary` says, and once it is, `appliedVersion` is "
            "where the library carries it."
        ),
    )
    diff: list[DiffSegment] = Field(
        default_factory=list,
        description=(
            "The two texts sentence by sentence, the same comparison \"Show what changed\" makes "
            "between two versions of a record: what stands, what would go and what would arrive. "
            "Empty when there is nothing to compare, which is the case for a vocabulary change and "
            "for a record with no text in this language."
        ),
    )
    sources: list[ProposalSource] = Field(
        default_factory=list,
        description=(
            "One source per field the proposal changes, so a reviewer can follow every value to "
            "where it came from. Empty on the vocabulary kinds, whose wording a person writes "
            "rather than drawing it from an authority."
        ),
    )
    scope_before: list[str] = Field(
        default_factory=list,
        description=(
            "The record's scope facets before this proposal, each written `dimension:key`, for "
            "example `client_category:retail`. For a proposal that was not approved, open or "
            "rejected, it is the scope the library holds now. For an approved one that replaced "
            "the scope it is the scope the approval found, as the audit row of the approval "
            "recorded it; one that left the scope alone shows the scope the record carries now. "
            "Both parts are keys of rows an admin manages rather than fixed values, so read the "
            "term lists for the labels. Empty when the record carries no facets, and empty on a "
            "proposal that changes no record."
        ),
        examples=[["service_type:advice", "client_category:retail"]],
    )
    scope_after: list[str] | None = Field(
        default=None,
        description=(
            "The scope the proposal would leave, in the same spelling, which replaces the list "
            "above whole rather than adding to it. Null means the proposal leaves the scope alone, "
            "which is not the same as an empty list: an empty list would clear it."
        ),
    )
    rejection_reason: LibraryRef | None = Field(
        default=None,
        description=(
            "Why it was refused, as the key and the label of the row chosen from the "
            "`rejection_reason` vocabulary, a library list. Its rows are data an admin may extend, relabel, "
            "reorder or retire without a deploy, never a closed set, and "
            "`GET /vocab/rejection_reason` returns the live one, so a key you have not seen "
            "before is new data and not an error; the kinds are those of that list, which today "
            "gives its rows none. Null unless the status is `rejected`, and null when the code "
            "stored on the proposal names a row the list no longer holds."
        ),
    )
    applied_version: ProposalAppliedVersion | None = Field(
        default=None,
        description="The library version this approval wrote, by id, number and effective date. Null unless the status is `approved`.",
    )


class TenantProposalRow(CamelSchema):
    """One proposal this bank made to a shared library list (PRO-03, VOC-07), as the bank's
    own vocabulary screen lists it. A bank sees the proposals its own people and agents
    filed and never another bank's, and never a platform reviewer's name."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "8f1d6d9e-58f0-4c2e-9e2f-6a4a6f1b8c21",
                    "kind": "vocabulary_create",
                    "status": "open",
                    "title": "Add the flag \"Client money\"",
                    "createdAt": "2026-09-16T07:12:00Z",
                }
            ]
        }
    )

    id: UUID = Field(description="The proposal, as a UUID the server assigned when it was filed and never changes.")
    kind: str = Field(
        description=(
            "What this bank asked to change. A fixed kind, not a vocabulary row: `vocabulary_create` "
            "adds a row to a shared list, `vocabulary_relabel` rewords one, `vocabulary_retire` and "
            "`vocabulary_restore` turn one off and on again, `vocabulary_merge` points a row's users "
            "at another row and retires it, and `term_create` and `term_update` do the same for a "
            "taxonomy term. `new_obligation_version` adds a version to a duty."
        )
    )
    status: str = Field(
        description=(
            "Where the request stands. A fixed kind: `open` is waiting for a platform reviewer, "
            "`approved` means every bank's library now carries it, `rejected` means it was refused "
            "with a reason and changed nothing, and `superseded` means a later proposal overtook it."
        )
    )
    title: str = Field(description="The one-line request as the person here who filed it wrote it, which is what the screen lists it under.")
    created_at: datetime = Field(description="When this bank filed it: a UTC timestamp, date and time together, so a screen can order and date the list.")


class TenantProposalPage(CamelSchema):
    """A page of what this bank has proposed to the shared library lists."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "8f1d6d9e-58f0-4c2e-9e2f-6a4a6f1b8c21",
                            "kind": "vocabulary_create",
                            "status": "open",
                            "title": "Add the flag \"Client money\"",
                            "createdAt": "2026-09-16T07:12:00Z",
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )

    items: list[TenantProposalRow] = Field(description="This page of proposals, oldest first, so a list reads in the order the bank filed them.")
    total: int = Field(description="How many proposals match the filters in all, across every page, so a screen can show a count without reading them.", examples=[3])


class TenantProposalQuery(CamelSchema):
    """Filters of a bank's own proposals, each optional and each narrowing the list."""

    status: str | None = Field(
        default=None,
        description=(
            "Keep only these statuses: one value, or several separated by commas. The values are "
            "`open`, `approved`, `rejected` and `superseded`. Left out, every status is returned."
        ),
        examples=["open"],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "Keep only these kinds: one value, or several separated by commas, from the kinds "
            "`kind` names above. Left out, every kind is returned."
        ),
        examples=["vocabulary_create,vocabulary_relabel"],
    )
    target_list: str | None = Field(
        default=None,
        description=(
            "Keep only the proposals that change this vocabulary list, or this taxonomy dimension, "
            "by its key, for example `flag`. The keys are rows an admin manages; "
            "`GET /vocabularies` returns the live set. Left out, every list is returned."
        ),
        examples=["flag"],
    )



class ProposalPage(CamelSchema):
    """A page of the console review queue, oldest first, with the count of every proposal
    matching the filters."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "8f1d6d9e-58f0-4c2e-9e2f-6a4a6f1b8c21",
                            "kind": "new_obligation_version",
                            "status": "approved",
                            "title": "Add version 2 of the research payment obligation, in force 1 October 2026",
                            "targetType": "obligation",
                            "targetId": "3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44",
                            "changeId": "b7e1c0a4-9f3d-4f6a-9c21-5d8e2f0a1b33",
                            "payload": {
                                "summaries": {
                                    "sv": "Investeringsanalys från tredje part får tas emot endast om den betalas med institutets egna medel eller från ett analyskonto.",
                                },
                                "originalLanguage": "sv",
                                "isMachine": False,
                                "effectiveFrom": "2026-10-01",
                                "effectiveFromPrecision": "day",
                            },
                            "fieldSources": {"summaries.sv": "https://www.fi.se/", "effectiveFrom": "https://www.fi.se/"},
                            "scopeSuggestion": [],
                            "sourceLabel": "Finansinspektionen, board decision 15 September 2026",
                            "sourceUrl": "https://www.fi.se/",
                            "effectiveFrom": "2026-10-01",
                            "origin": "agent",
                            "agentRunId": "5a2b9c7d-1e3f-4a8b-9c0d-2e4f6a8b0c12",
                            "model": "agent pipeline 0.4",
                            "proposedBy": None,
                            "proposedByAgent": {"key": "watch-sweeper", "version": 1},
                            "fromOrganisation": False,
                            "reviewedBy": None,
                            "reviewedByAgent": {"key": "library-confirmer", "version": 1},
                            "correctedBy": None,
                            "correctedByAgent": None,
                            "reviewedAt": "2026-09-16T09:40:00Z",
                            "rejectionCode": "",
                            "reviewNote": "The summary matches the board decision and the date it names.",
                            "appliedAt": "2026-09-16T09:40:00Z",
                            "createdAt": "2026-09-16T07:12:00Z",
                            "target": {
                                "id": "3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44",
                                "title": "Pay for third-party research only under the permitted models",
                                "referenceLabel": "Third-party payments",
                                "instrumentShortName": "FFFS 2017:2",
                            },
                            "isMine": False,
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )

    items: list[ProposalQueueRow] = Field(
        description=(
            f"This page of proposals, oldest first, so the queue reads in the order they arrived and "
            f"paging is repeatable: {settings.API_PAGE_SIZE_DEFAULT} rows by default and "
            f"{settings.API_PAGE_SIZE_MAX} at most. Nothing matching the filters is an empty list, never a 404."
        )
    )
    total: int = Field(
        description="How many proposals match the filters in all, across every page, which is what a tab's count shows. 0 when nothing matches.",
        examples=[4],
    )


# ---------------------------------------------------------------------------------------
# What changed in the shared library since a reader last looked (PRO-03, INV-04, FP-03)
# ---------------------------------------------------------------------------------------
class LibraryUpdateTarget(CamelSchema):
    """The library record an update touched, named by the record itself. A proposal's own
    wording never appears here: one bank's request must not reach another bank as a title."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44",
                    "title": "Pay for third-party research only under the permitted models",
                    "referenceLabel": "Third-party payments",
                    "instrumentShortName": "FFFS 2017:2",
                }
            ]
        }
    )

    id: UUID = Field(description="The duty that changed, as a UUID: the id its own card is read at, so a row can link straight to it.")
    title: str = Field(description="The duty's own title, in the best language this reader has, as the library holds it after the change.")
    reference_label: str = Field(description="How the duty is cited inside its instrument, for example \"Third-party payments\". Empty when the record carries no reference of its own.")
    instrument_short_name: str = Field(description="The short name of the law, regulation or guideline the duty sits in, for example \"FFFS 2017:2\".")


# The watch agent proposed the change and an independent agent confirmed it (D-62).
_SAMPLE_CONFIRMED_BY_AGENTS: dict[str, Any] = {
    "verifiedOrigin": "agent",
    "confirmedByAgent": {"id": "2f7a9c14-3b8e-4d61-9a05-c8e1f4b27d93", "key": "library-confirmer"},
    "proposedByAgent": {"id": "6d1e4f8a-9c3b-4a7e-8f21-1b6d4c8a2e05", "key": "watch-sweeper"},
}


class LibraryUpdateRow(CamelSchema):
    """One change that reached the shared library while this reader was away (PRO-03,
    INV-04): what changed, when it was applied, when it starts binding, whether it reaches
    this bank, and who confirmed it. It is a fact about the library and never a task:
    whether the duty applies here, and whether this bank complies with it, are the bank's
    own judgements recorded elsewhere. No person is named: who asked for a change is not a
    bank's business, and a change another bank asked for reads exactly like any other. The
    platform agents that proposed or confirmed it are named by definition key (INV-05,
    D-62), so a change an independent agent confirmed never reads as a person's approval."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "8f1d6d9e-58f0-4c2e-9e2f-6a4a6f1b8c21",
                    "kind": "new_obligation_version",
                    "appliedAt": "2026-09-18T09:20:00Z",
                    "effectiveFrom": {"date": "2026-10-01", "precision": "day"},
                    "versionNumber": 2,
                    "target": {
                        "id": "3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44",
                        "title": "Pay for third-party research only under the permitted models",
                        "referenceLabel": "Third-party payments",
                        "instrumentShortName": "FFFS 2017:2",
                    },
                    "vocabularyList": None,
                    "vocabulary": None,
                    "inFootprint": True,
                    "outsideReason": [],
                    **_SAMPLE_CONFIRMED_BY_AGENTS,
                }
            ]
        }
    )

    id: UUID = Field(description="A stable id for this row, as a UUID: it is the id of the approved change behind it. Use it as a list key; there is no call that takes it.")
    kind: str = Field(
        description=(
            "What kind of change it was, and therefore which of the fields below are filled. A "
            "fixed kind: `new_obligation_version` is a new wording of a duty, and "
            "`vocabulary_create`, `vocabulary_relabel`, `vocabulary_retire`, `vocabulary_restore`, "
            "`vocabulary_merge`, `term_create` and `term_update` are changes to a shared list or "
            "to the taxonomy every bank reads."
        )
    )
    applied_at: datetime = Field(
        description="When the change reached the library: a UTC timestamp, date and time together. The day a screen files it under is this moment in the bank's own time zone.",
        examples=["2026-09-18T09:20:00Z"],
    )
    effective_from: PartialDate | None = Field(
        default=None,
        description=(
            "The legal date the new wording starts binding the bank, with how exactly that date "
            "is known. Null on a change to a shared list, which has no legal date, and null when "
            "the new version has been in force since the duty entered the library."
        ),
    )
    version_number: int | None = Field(
        default=None,
        description="Which version of the duty this change created, counting from 1 upwards, so a reader can ask for what changed between it and the one before. Null on a change to a shared list.",
        examples=[2],
    )
    target: LibraryUpdateTarget | None = Field(
        default=None,
        description="The duty that changed, named by the library's own wording. Null on a change to a shared list, which names no single record; `vocabularyList` then says which list it was.",
    )
    vocabulary_list: str | None = Field(
        default=None,
        description=(
            "Which shared list or taxonomy dimension changed, by its key, for example `flag`. The "
            "lists are themselves rows an admin may extend or retire, and `GET /vocabularies` "
            "returns the live set. Null on a change to a duty."
        ),
        examples=["flag"],
    )
    vocabulary: LibraryRef | None = Field(
        default=None,
        description=(
            "The row of that list which changed, by key and label, as the list labels it today. "
            "The rows are vocabulary data an admin may extend, relabel, reorder or retire without "
            "a deploy, so store the key and show the label; `GET /vocabularies` returns the live "
            "set. The label is the library's own and never the wording of the request that "
            "changed it. Null on a change to a duty, and null when the row has since been deleted."
        ),
    )
    in_footprint: bool = Field(
        default=True,
        description=(
            "True when the duty that changed is inside this bank's footprint, which is the only "
            "kind of change the list carries unless `outsideFootprint` asked for the rest. A change "
            "to a shared list is always true: a list is shared by every bank and belongs to no "
            "footprint. It says the duty reaches this bank's business, never that the bank complies."
        ),
        examples=[True],
    )
    outside_reason: list[OutsideReason] = Field(
        default_factory=list,
        description=(
            "Why the footprint would have hidden it, one entry per facet in which the duty's terms "
            "and this bank's footprint have nothing in common. Empty when the change is inside the "
            "footprint, which is the usual case, and empty on a change to a shared list."
        ),
    )
    verified_origin: str = Field(
        description=(
            "Who confirmed the approval that applied this change: `agent` when the reviewer was "
            "a second, independent agent, which a screen labels machine-confirmed and never as a "
            "person's verification; `user` when a person approved it, who is never named here. "
            "A fixed kind, not a vocabulary."
        ),
        examples=["agent"],
    )
    confirmed_by_agent: AgentRef | None = Field(
        description=(
            "The independent agent that confirmed the change, by its definition key, when "
            "`verifiedOrigin` is `agent`. Null whenever a person approved it. It names a platform "
            "agent definition, never a person or a bank."
        )
    )
    proposed_by_agent: AgentRef | None = Field(
        description=(
            "The agent that proposed the change, by its definition key. Null whenever the proposer "
            "was not a key bound to an agent, which is every change a person asked for, whoever "
            "confirmed it; that person is never named. It is independent of `verifiedOrigin`: a "
            "person may have approved an agent's proposal, and an agent may have confirmed a "
            "person's."
        )
    )


class LibraryUpdateDay(CamelSchema):
    """One day's changes, as the list groups them."""

    date: DayDate = Field(description="The day these changes were applied, in the bank's own time zone, as a plain date: a change applied late in the evening is filed under the bank's day, not London's.", examples=["2026-09-18"])
    items: list[LibraryUpdateRow] = Field(description="What changed that day, the most recent first.")


class LibraryUpdatesPage(CamelSchema):
    """What changed in the shared library since this reader last marked it as seen."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "since": "2026-09-16T07:12:00Z",
                    "days": [
                        {
                            "date": "2026-09-18",
                            "items": [
                                {
                                    "id": "8f1d6d9e-58f0-4c2e-9e2f-6a4a6f1b8c21",
                                    "kind": "new_obligation_version",
                                    "appliedAt": "2026-09-18T09:20:00Z",
                                    "effectiveFrom": {"date": "2026-10-01", "precision": "day"},
                                    "versionNumber": 2,
                                    "target": {
                                        "id": "3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44",
                                        "title": "Pay for third-party research only under the permitted models",
                                        "referenceLabel": "Third-party payments",
                                        "instrumentShortName": "FFFS 2017:2",
                                    },
                                    "vocabularyList": None,
                                    "vocabulary": None,
                                    "inFootprint": True,
                                    "outsideReason": [],
                                    **_SAMPLE_CONFIRMED_BY_AGENTS,
                                }
                            ],
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )

    since: datetime = Field(
        description=(
            "The moment this list starts from: when this reader last marked the library as seen "
            "(`POST /me/visit`), as a UTC timestamp. For a reader who never has, it is the start "
            "of the default window instead, so a first visit is not empty."
        ),
        examples=["2026-09-16T07:12:00Z"],
    )
    days: list[LibraryUpdateDay] = Field(description="The changes on this page, grouped by the day they were applied in the bank's time zone, the most recent day first.")
    total: int = Field(description="How many changes there are in all since that moment, across every page, so a screen can say how much arrived while the reader was away.", examples=[1])


class LibraryUpdatesQuery(CamelSchema):
    """Filters of "what changed in the library", each optional."""

    kind: str | None = Field(
        default=None,
        description=(
            "Keep only these kinds of change: one value, or several separated by commas, from the "
            "kinds `LibraryUpdateRow.kind` names. Left out, every kind is returned."
        ),
        examples=["new_obligation_version"],
    )
    outside_footprint: bool = Field(
        default=False,
        description=(
            "True also lists the changes to duties the bank's footprint hides, each saying in "
            "`outsideReason` why it would have been hidden. False, the default, lists only what "
            "reaches this bank. Changes to a shared list are listed either way."
        ),
        examples=[True],
    )



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
    agent_run_id: UUID | None = Field(
        default=None,
        description=(
            "The run this proposal was found in, as the UUID `POST /agent-runs` returned. "
            "Required from a key bound to an agent, and it must be a run that same key has "
            "open: naming none, or a closed one, answers 422 `run_not_open`, and a run of "
            "another key answers 404 `not_found`. A person and a bank's own key name none."
        ),
        examples=["5b8e1a44-9c2d-4f17-b0a3-1e7c6d5f4a21"],
    )
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
    """Filters of the console review queue, each optional and each narrowing the queue."""

    status: str | None = Field(
        default=None,
        description=(
            "Keep only these statuses: one value, or several separated by commas. The values are "
            "`open` (waiting for a reviewer), `approved`, `rejected` and `superseded`. Left out, "
            "every status is returned, which is why each tab of the queue sends its own."
        ),
        examples=["open"],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "Keep only these kinds: one value, or several separated by commas, from the kinds "
            "`ProposalRow.kind` names. Left out, every kind is returned."
        ),
        examples=["vocabulary_create,term_create"],
    )
    target_list: str | None = Field(
        default=None,
        description=(
            "Keep only the proposals that change this vocabulary list, or this taxonomy dimension, "
            "by its key, for example `flag`: the lists are rows an admin manages and "
            "`GET /vocabularies` returns the live set. Left out, every list is returned."
        ),
        examples=["flag"],
    )
    origin: str | None = Field(
        default=None,
        description=(
            "Keep only the proposals filed by one sort of proposer: `agent` for a watch or research "
            "agent's, `user` for a person's. Those are the only two values; anything else is refused "
            "with 422 `unknown_key` rather than answered with an empty queue. Left out, both are "
            "returned."
        ),
        examples=["agent"],
    )
    not_mine: bool = Field(
        default=False,
        description=(
            "True drops the proposals the reader filed themselves, which are exactly the ones four "
            "eyes will not let them decide and the ones `isMine` marks, so the queue shows only work "
            "they can actually do: for a person, their own; for an agent's key, the key's own and "
            "those of every other key of the same agent definition. `total` then counts what is left. "
            "False, the default, returns theirs alongside the rest."
        ),
        examples=[True],
    )
