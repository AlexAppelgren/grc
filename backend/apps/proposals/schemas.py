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
from apps.shared.schemas import AgentDecision, CamelSchema, WriteBody

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


# A new record's stable key: lowercase words joined by hyphens, as the seeded library writes
# them (`fffs-2017-2`, `obl-research-payments`). It is the record's name for ever.
STABLE_KEY_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class ProposalInstrumentPayload(WriteBody):
    """`new_instrument` (PRO-01, INV-01, INV-08): a law, regulation, guideline or standard
    edition the library does not hold yet.

    `key` is the stable key the instrument keeps for ever. `titles` is its official name
    per content language, `originalLanguage` the one it was issued in, and `isMachine`
    says the others are machine translations until a person confirms them (INV-05).
    `level`, `jurisdiction` and `authority` are keys of their library lists; `binding`
    left out takes the level's default. `regime` is a term of the regime dimension written
    `regime:<key>` (D-39): any other term is refused with 422 `not_a_regime`. In-force
    dates are plain legal dates, each with a precision (INV-S10).

    Every fact here needs its source, an https link, in `fieldSources` (`sourced_fields()`
    in apps/proposals/logic.py names them); the key and the language flags do not.
    """

    key: str = Field(max_length=120, pattern=STABLE_KEY_PATTERN)
    titles: dict[str, str]
    original_language: str
    is_machine: bool = False
    short_name: str = Field(min_length=1, max_length=120)
    official_ref: str = Field(min_length=1, max_length=200)
    eli_uri: str = Field(default="", max_length=2000)
    level: str
    binding: bool | None = None
    jurisdiction: str
    authority: str | None = None
    regime: str
    in_force_from: date | None = None
    in_force_from_precision: str = "day"
    in_force_to: date | None = None
    in_force_to_precision: str = "day"
    implements_note: str = ""


class ProposalObligationPayload(WriteBody):
    """`new_obligation` (PRO-01, INV-03, INV-04): a duty the library does not hold yet,
    under an instrument it does, with its first version.

    `key` is the stable key the obligation keeps for ever and `instrument` the stable key
    of the shared instrument it is broken out of. `titles` and `summaries` are per content
    language, with `originalLanguage` the one both were written in and `isMachine` saying
    the others are machine-made (INV-05). `dutyType` is a key of the duty type list.
    `effectiveFrom` is when the first version is in force, a plain legal date with a
    precision; left out, since the duty began. `terms` are the scope facets as
    `dimension:key`, never a mirrored jurisdiction term (FP-S12).

    Every fact here needs its source, an https link, in `fieldSources`.
    """

    key: str = Field(max_length=120, pattern=STABLE_KEY_PATTERN)
    instrument: str
    titles: dict[str, str]
    summaries: dict[str, str]
    original_language: str
    is_machine: bool = False
    ref_label: str = Field(min_length=1, max_length=200)
    duty_type: str
    effective_from: date | None = None
    effective_from_precision: str = "day"
    terms: TermRefs | None = Field(default=None, max_length=settings.PROPOSAL_SCOPE_MAX_TERMS)


class ProposalProvisionPayload(WriteBody):
    """`new_provision` (PRO-01, INV-02): a node of a law's structure the library does not
    hold yet, with its first verbatim text.

    `key` is the stable key the provision keeps for ever, `instrument` the stable key of the
    shared instrument it belongs to and `parent` the stable key of the provision of that
    instrument it sits under, left out at the top of the tree. `provisionKind` is a key of
    the provision kind list; `refLabel` and `heading` are how the text cites and names it.
    `texts` is the verbatim text per content language, `originalLanguage` the one the
    authority published and `isMachine` saying the others are machine-made (INV-05). The
    date is a plain legal date with a precision.

    Never under a standard, whose text is licensed: 422 `licensed_text` (INV-08, D-35).
    Every fact here needs its source, an https link, in `fieldSources`.
    """

    key: str = Field(max_length=200, pattern=STABLE_KEY_PATTERN)
    instrument: str
    parent: str | None = None
    provision_kind: str
    ref_label: str = Field(min_length=1, max_length=200)
    heading: str = ""
    sort_order: int = 0
    texts: dict[str, str]
    original_language: str
    is_machine: bool = False
    effective_from: date | None = None
    effective_from_precision: str = "day"


class ProposalProvisionVersionPayload(WriteBody):
    """`new_provision_version` (PRO-01, INV-02): the verbatim text of a provision that
    exists, in force from a date. Nothing is overwritten; the earlier text stays.

    `texts`, `originalLanguage`, `isMachine` and the date read as on `new_provision`. Never
    on a standard's provision: 422 `licensed_text` (INV-08, D-35). Every field needs its
    source in `fieldSources`.
    """

    texts: dict[str, str]
    original_language: str
    is_machine: bool = False
    effective_from: date | None = None
    effective_from_precision: str = "day"


class ProposalRecurringDutyPayload(WriteBody):
    """`new_recurring_duty` (REG-07, PRO-01): a duty an obligation of the library carries on
    a schedule, a quarterly report or a yearly attestation. The obligation is the
    proposal's target (`targetType` `obligation` and `targetId`), shared and in force.

    `title` names the duty. `recurrenceRule` is one RFC 5545 RRULE line at a day or coarser,
    such as `FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=31`, without DTSTART: it must fall due at least
    once and at most `RECURRENCE_MAX_OCCURRENCES` times in the next ten years, or the
    proposal answers 422 `invalid_recurrence` (apps/library/recurrence.py). `dueRuleNote`
    says how the authority sets the due date, `recipientAuthority` is the key of the
    authority the duty goes to, when one does, and `leadDays` how many days before a due
    date the duty starts showing, at most a year.

    Every field it sets needs its source in `fieldSources`: an https link or the stable key
    of a provision the library holds.
    """

    title: str = Field(min_length=1, max_length=300)
    recurrence_rule: str = Field(min_length=1, max_length=500)
    due_rule_note: str = Field(default="", max_length=settings.PROPOSAL_TEXT_MAX_CHARS)
    recipient_authority: str | None = None
    lead_days: int = Field(default=0, ge=0, le=366)


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
            "`new_instrument` adds an instrument the library does not hold yet, `new_obligation` adds a "
            "duty under an instrument it holds, with its first version, `new_provision` adds a node of a "
            "law's text with its first verbatim text, `new_provision_version` adds a text to a provision "
            "that exists, `new_recurring_duty` adds a duty an obligation carries on a schedule, "
            "`vocabulary_create` adds a row to a library list, `vocabulary_relabel` rewords one, "
            "`vocabulary_retire` and `vocabulary_restore` turn one off and on again, `vocabulary_merge` "
            "points a row's users at another row and retires it, and `term_create` and `term_update` do "
            "the same for a taxonomy term, and `obligation_scope` re-tags many obligations' scope terms as "
            "one batch (`isBatch`). The other kinds of the data model are not built yet, so a "
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
    target_type: str = Field(default="", description="What the proposal changes, when it changes one record that already exists: `obligation` today, empty for a proposal that creates something and for a batch, whose rows name their records.")
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
    risk_flags: list[str] = Field(
        default_factory=list,
        description=(
            "What the injection screen found in the texts the proposal arrived with: its title, "
            "every text of its payload, its field sources, its source and its model. Empty when it found "
            "nothing; otherwise `embedded_instructions`, text that reads as an instruction to "
            "an AI rather than a fact from the authority. The texts are stored exactly as they "
            "arrived and are never followed. While the list is not empty no agent may approve "
            "the proposal, which answers 409 `risk_flagged`: a person reads the flag and "
            "decides, and may still approve."
        ),
        examples=[[], ["embedded_instructions"]],
    )
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
    is_batch: bool = Field(
        default=False,
        description=(
            "True when the proposal is a batch: one request that changes many library records, with a row "
            "per record read through `GET /proposal-batches/{batchId}`. The queue lists a batch once, as this "
            "row. False for a proposal that changes one record or creates one."
        ),
        examples=[False],
    )
    row_count: int = Field(
        default=0,
        ge=0,
        description="How many records a batch would change, one row each, at most `PROPOSAL_BATCH_MAX_ROWS`. Always 0 when `isBatch` is false.",
        examples=[0],
    )
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
                    "isBatch": False,
                    "rowCount": 0,
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
            "taxonomy term. `new_obligation_version` adds a version to a duty, and `new_instrument`, "
            "`new_obligation`, `new_provision` and `new_provision_version` bring a record or a text "
            "the library does not hold yet, and `new_recurring_duty` a schedule a duty falls due on."
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
            f"This page of proposals, oldest first unless `order` asks for the newest first, by when "
            f"each was filed with the id breaking a tie, so paging is repeatable: {settings.API_PAGE_SIZE_DEFAULT} rows by default and "
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
            "fixed kind: `new_obligation_version` is a new wording of a duty, `new_obligation` is a "
            "duty new to the library with its first wording, `new_instrument` is an instrument new to "
            "the library, which names no duty and no list, `new_provision` and `new_provision_version` "
            "are a law's verbatim text, new or amended, which name no duty and no list either, "
            "`new_recurring_duty` is a schedule a duty falls due on, which names that duty, and "
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
        description="The duty that changed, or the duty that arrived, named by the library's own wording. Null on a change to a shared list, which names no single record, when `vocabularyList` says which list it was, and null on a new instrument.",
    )
    vocabulary_list: str | None = Field(
        default=None,
        description=(
            "Which shared list or taxonomy dimension changed, by its key, for example `flag`. The "
            "lists are themselves rows an admin may extend or retire, and `GET /vocabularies` "
            "returns the live set. Null on a change to a duty and on a new instrument."
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
    """The 202 a write to a shared library list or taxonomy term answers (VOC-07): nothing in the library
    changed, and a proposal now waits for a second person or agent to decide it."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "proposal": {
                        "id": "2c7a5e91-4d3b-4f08-a6e2-9b1c0d8f7e35",
                        "kind": "vocabulary_create",
                        "status": "open",
                        "title": "Add Supervisory statement to change_type",
                        "targetType": "change_type",
                        "targetId": None,
                        "changeId": None,
                        "payload": {
                            "list": "change_type",
                            "key": "supervisory_statement",
                            "labels": {"en": "Supervisory statement", "sv": "Tillsynsuttalande"},
                            "usageNote": "An authority's published view on how a rule is applied.",
                            "kind": "supervisory",
                            "extra": {},
                        },
                        "fieldSources": {},
                        "scopeSuggestion": [],
                        "sourceLabel": "",
                        "sourceUrl": "",
                        "effectiveFrom": None,
                        "origin": "user",
                        "agentRunId": None,
                        "model": "",
                        "proposedBy": None,
                        "proposedByAgent": None,
                        "fromOrganisation": True,
                        "reviewedBy": None,
                        "reviewedByAgent": None,
                        "correctedBy": None,
                        "correctedByAgent": None,
                        "reviewedAt": None,
                        "rejectionCode": "",
                        "reviewNote": "",
                        "appliedAt": None,
                        "createdAt": "2026-09-18T09:40:00Z",
                    }
                }
            ]
        }
    )

    proposal: ProposalRow = Field(
        description=(
            "The proposal the write became, waiting in the platform's review queue with `status` `open`. "
            "Nothing has changed yet: the shared list or taxonomy still says what it said, and it changes only when a "
            "second, independent person or agent approves the proposal in the console, never the one who "
            "made it. A proposal made inside a bank names no proposer (`fromOrganisation` is true); the bank "
            "follows it in `GET /tenant/proposals`."
        )
    )


class ProposalCreateBody(WriteBody):
    """The body of `POST /proposals`: one change somebody wants made to the shared library,
    with the source behind every value it would write. Nothing in the library changes when
    this is accepted; the proposal waits for a second, independent reviewer.

    Fields the schema does not name are refused with 422 `validation_error` rather than
    dropped, so nothing rides along unseen. The whole body is library data that every bank
    will read once approved: it must never carry a bank's own judgement, its people's names
    or its internal documents.
    """

    kind: str = Field(
        description=(
            "What is asked for, which decides the shape of `payload`. A fixed kind, not a vocabulary: "
            "`new_obligation_version` is a new summary of one duty in force from a date, with its scope "
            "terms; `new_instrument` is a law, regulation, guideline or standard edition the library "
            "does not hold yet; `new_obligation` is a duty the library does not hold yet, under an "
            "instrument it does, with its first summary; `new_provision` is a node of a law's text with "
            "its first verbatim text, and `new_provision_version` a provision's text in force from a "
            "date, neither ever under a standard (422 `licensed_text`); `new_recurring_duty` is a schedule "
            "an obligation in force falls due on, as an RFC 5545 rule; `vocabulary_create`, `vocabulary_relabel`, "
            "`vocabulary_retire`, `vocabulary_restore` and `vocabulary_merge` add, reword, turn off, "
            "turn on again or fold together a row of a shared list; `term_create` and `term_update` add "
            "or reword a taxonomy term. Any other value answers 422 `unknown_key` naming the valid ones."
        ),
        examples=["new_obligation_version"],
    )
    title: str = Field(
        max_length=500,
        description=(
            "The request in one line, as the reviewer reads it in the queue, at most 500 characters and "
            "never blank. It describes the request and is never the library record's own title, which "
            "comes from the payload."
        ),
        examples=["Version 2 of the research assessment duty, in force 1 October 2026"],
    )
    payload: dict[str, Any] = Field(  # schema: ProposalPayload
        default_factory=dict,
        description=(
            "What the library should hold, in the shape `kind` names, with camelCase field names. A "
            "field the kind does not name, or a value it does not accept, answers 422 "
            "`validation_error` naming the fields to fix. `new_obligation_version`: `summaries` (text "
            "per content language), `originalLanguage`, `isMachine`, `effectiveFrom`, "
            "`effectiveFromPrecision` (`day`, `month`, `quarter` or `year`) and `terms` (scope as "
            f"`dimension:key`, at most {settings.PROPOSAL_SCOPE_MAX_TERMS}). `new_instrument`: `key` "
            "(a stable key of lowercase words joined by hyphens, at most 120 characters, kept for ever), "
            "`titles` per language, `originalLanguage`, `isMachine`, `shortName`, `officialRef`, "
            "`eliUri`, `level`, `binding` (left out, the level's default), `jurisdiction`, `authority`, "
            "`regime` (a term of the regime dimension as `regime:<key>`, else 422 `not_a_regime`), "
            "`inForceFrom`, `inForceTo` and their precisions, and `implementsNote`. `new_obligation`: "
            "`key`, `instrument` (the stable key of a shared instrument in force), `titles` and "
            "`summaries` per language, `originalLanguage`, `isMachine`, `refLabel`, `dutyType`, "
            "`effectiveFrom`, `effectiveFromPrecision` and `terms`; under a standard it is the one "
            "conformance obligation, carrying exactly one standard term (else 422 "
            "`one_conformance_obligation` or `standard_term_required`), and a law's obligation carries "
            "none (422 `standard_term_only_on_standards`). `new_provision`: `key`, `instrument`, "
            "`parent` (the stable key of a provision of the same instrument, left out at the top), "
            "`provisionKind`, `refLabel`, `heading`, `sortOrder`, `texts` per language, "
            "`originalLanguage`, `isMachine`, `effectiveFrom` and `effectiveFromPrecision`. "
            "`new_provision_version`: `texts`, `originalLanguage`, `isMachine`, `effectiveFrom` and "
            "`effectiveFromPrecision`. Each summary and each text is at most "
            f"{settings.PROPOSAL_TEXT_MAX_CHARS} characters per language, else 422 `validation_error`. "
            "The vocabulary and term kinds name a "
            "`list` or `dimension`, a `key` and `labels`. Level, jurisdiction, authority, duty type and "
            "term keys are library rows that change only through proposals; `GET /vocabularies` and "
            "`GET /taxonomy/terms` return the live sets."
        ),
    )
    target_type: str = Field(
        default="",
        max_length=64,
        description=(
            "What the proposal changes, when it changes a record that exists: `obligation` for "
            "`new_obligation_version` and `new_recurring_duty` and `provision` for `new_provision_version`, at most 64 "
            "characters. Empty for every other kind; a new instrument, obligation or provision that "
            "names a target answers 422 `validation_error`, since the "
            "record does not exist until the proposal is approved."
        ),
        examples=["obligation"],
    )
    target_id: UUID | None = Field(
        default=None,
        description=(
            "The record changed, as a UUID, with `targetType`. For `new_obligation_version` and `new_recurring_duty` it must be "
            "an obligation, and for `new_provision_version` a provision, the library holds and has not "
            "retired, else 422 `unknown_key`. Null for every other kind."
        ),
        examples=["7b1f2c4e-8d3a-4c61-9f0b-2e5a7c9d1a44"],
    )
    change_id: UUID | None = Field(
        default=None,
        description=(
            "The regulatory change that prompted this, as a UUID, when a watch run found one. Optional; "
            "leaving it out says nobody linked one, not that no change exists."
        ),
        examples=["b7e1c0a4-9f3d-4f6a-9c21-5d8e2f0a1b33"],
    )
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
    model: str = Field(
        default="",
        max_length=200,
        description=(
            "The model or pipeline that drafted the proposal, as the agent names it, at most 200 "
            "characters (AUD-02). Empty for a proposal a person wrote. What it drafted stays labelled "
            "machine-made until a person confirms it."
        ),
        examples=["agent pipeline 0.4"],
    )
    field_sources: dict[str, str] = Field(  # schema: ProposalFieldSources
        default_factory=dict,
        description=(
            "Per field the payload sets, where its value came from, keyed as the queue names the field "
            "(`summaries.sv`, `texts.sv`, `effectiveFrom`, `terms`, `regime`). Each source is at most "
            f"{settings.PROPOSAL_SOURCE_MAX_CHARS} characters and is an https link, or for an obligation "
            "or provision version also the stable key of a provision the library holds. A new "
            "instrument, obligation or provision takes https links only, since it has no provision of "
            "its own yet, and so does every obligation of a standard: anything else there answers 422 "
            "`licensed_text`. A field "
            "without a source answers 422 `source_missing`; a source that is neither, or one given for a "
            "field the proposal does not set, answers 422 `validation_error`. The vocabulary kinds need "
            "none, since a person writes their wording."
        ),
        examples=[{"summaries.sv": "https://www.fi.se/en/published/news/2026/research-payments/"}],
    )
    source_label: str = Field(
        default="",
        max_length=500,
        description=(
            "The source in words, as a reviewer and a reader see it beside a link, at most 500 "
            "characters, for example the authority and the decision. A new obligation keeps it as its "
            "own source label; left empty, it reads the instrument's reference and the duty's. Under a "
            "standard it is the standard's official reference or empty, never a clause or quoted text, "
            "else 422 `licensed_text`."
        ),
        examples=["Finansinspektionen, board decision 15 September 2026"],
    )
    source_url: str = Field(
        default="",
        max_length=2000,
        description=(
            "The authority's page the proposal was read from, at most 2000 characters. Required for a "
            "new instrument, obligation or provision, as an https link (a new instrument or obligation "
            "keeps it as its own source): "
            "without one it answers 422 `source_missing`. Optional on the other kinds, but when given it "
            "is an https link on every kind, since the queue shows it as the proposal's source: any "
            "other scheme answers 422 `validation_error`."
        ),
        examples=["https://www.fi.se/en/published/news/2026/research-payments/"],
    )
    effective_from: date | None = Field(
        default=None,
        description=(
            "The legal date the change starts binding, as a plain date without a time. For an obligation "
            "version or a new obligation it must equal the payload's `effectiveFrom`, else 422 "
            "`validation_error`; left out, it takes the payload's. Optional, and null means the "
            "proposal names no date."
        ),
        examples=["2026-10-01"],
    )


# What a confirming agent's approve and reject bodies carry beside its verdict (D-80,
# AUD-02, AGT-01), said once for both.
_DECISION_DESCRIPTION = (
    "The model call behind an agent's decision, as the agent reports it: the model and its version, the "
    "prompt's name and hash, what it concluded and at least one public page the conclusion rests on. "
    "Required from a key, whose decision without it answers 422 `validation_error`: every model call is "
    "logged, and one nobody reported cannot be. It becomes one entry of the AI output log under the purpose "
    "`agent_review`, in the same transaction as the decision, marked as the agent's own report rather than "
    "bleqq's measurement and labelled as AI output, so a reader must not take it for a person's review. No "
    "bank reads that entry. A person's decision is not a model call, so a person's body never carries it "
    "and one that does answers 422 `validation_error`."
)
_RUN_DESCRIPTION = (
    "The run this decision was made in, as the UUID `POST /agent-runs` returned: a run the calling key "
    "opened and has not closed, so every decision a confirming agent makes is counted in the run that made "
    "it, as a sweep's registrations are, and the decision's audit row names it. Required from a key: "
    "naming none, or a run that is closed, answers 422 `run_not_open`, and a run another key opened, "
    "another agent's included, answers 404 `not_found` exactly as a run that never existed does. A person's "
    "body never names one, and one that does answers 422 `validation_error`."
)
_DECISION_EXAMPLE: dict[str, Any] = {
    "model": "claude-opus-5",
    "modelVersion": "2026-05-01",
    "promptTemplate": "library-confirmer/decide/v1",
    "promptHash": "9f2a1c7d4b8e05f3",
    "output": (
        "Approve. The proposed wording matches the board decision as Finansinspektionen publishes it, and "
        "the date it applies from is the one the decision states."
    ),
    "citations": [
        {
            "label": "Finansinspektionen, board decision 15 September 2026",
            "url": "https://www.fi.se/en/published/news/2026/research-payments/",
        }
    ],
}
_RUN_EXAMPLE = "3c2a9f1e-6b7d-4e58-a1c4-0f9d8e7b6a52"


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

    A confirming agent approves with the platform-only scope `proposals:review` instead of
    a step-up, and sends two more fields a person never sends: `decision`, the model call
    behind its approval, and `agentRunId`, the open run of its own key it was made in
    (D-80). The first example is a person's approval, the second an agent's.

    The whole call is platform work in the shared zone. No field ever names the bank a
    proposal came from, because a bank member's identity does not reach the console, and
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
            "`new_obligation_version`, `new_instrument` and `new_obligation` kinds, since the vocabulary "
            "kinds carry a label a person wrote rather than a sourced fact; on any other kind the call "
            "answers 422 `validation_error`. A new record's corrections are checked exactly as the "
            "proposal was, so a regime that is not a term of the regime dimension answers 422 "
            "`not_a_regime`. For an obligation version the "
            "fields a reviewer may correct are the ones that kind's payload names: `summaries` (the "
            "whole set of texts per language, which replaces the proposed set), `originalLanguage`, "
            "`isMachine`, `effectiveFrom`, `effectiveFromPrecision` (one of `day`, `month`, `quarter` "
            "and `year`, which says how exactly the date is known) and `terms` (the scope facets as "
            f"`dimension:key`, at most {settings.PROPOSAL_SCOPE_MAX_TERMS}, which replace the "
            "obligation's scope). The merged payload must still carry a source for every field it "
            "changes, so a correction that introduces a field the proposal never sourced answers 422 "
            "`source_missing` and applies nothing, and a value changed from what was proposed needs its "
            "fresh source in `fieldSources`. Each summary is at most "
            f"{settings.PROPOSAL_TEXT_MAX_CHARS} characters per language. What is applied is kept beside what was proposed, as "
            "the reviewer's own correction: a reader must not take the proposal's payload as the text "
            "the library now holds."
        ),
    )
    field_sources: dict[str, str] | None = Field(  # schema: ProposalFieldSources
        default=None,
        description=(
            "The fresh source of every value `payloadOverrides` changes from what was proposed, keyed as "
            "the queue names the field (`summaries.sv`, `effectiveFrom`, `terms`), because the "
            "proposer's source vouches only for the value it was given for. Each is checked as a "
            f"proposal's own are: at most {settings.PROPOSAL_SOURCE_MAX_CHARS} characters, an https link "
            "or the stable key of a provision the library holds, and an https link only on a new record "
            "or a standard's obligation. A changed value without one answers 422 `source_missing`; a "
            "source for a field the correction leaves as proposed answers 422 `validation_error`. The "
            "proposal keeps these sources for the corrected fields from then on. Optional, and left out "
            "when nothing is corrected."
        ),
        examples=[{"summaries.sv": "https://www.fi.se/sv/publicerat/nyheter/2026/analysbetalningar/"}],
    )
    decision: AgentDecision | None = Field(default=None, description=_DECISION_DESCRIPTION)
    agent_run_id: UUID | None = Field(default=None, description=_RUN_DESCRIPTION, examples=[_RUN_EXAMPLE])

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
                    "fieldSources": {
                        "summaries.sv": "https://www.fi.se/sv/publicerat/nyheter/2026/analysbetalningar/",
                        "summaries.en": "https://www.fi.se/en/published/news/2026/research-payments/",
                    },
                },
                {"note": "Confirmed against the board decision.", "decision": _DECISION_EXAMPLE, "agentRunId": _RUN_EXAMPLE},
            ]
        }
    )


class ProposalRejectBody(WriteBody):
    """The body of `POST /proposals/{proposalId}/reject`: why a reviewer turned a proposal
    down, as a reason the proposer's screen can branch on and a sentence the proposer reads.

    Nothing in the library changes. The proposal is closed as `rejected` for good, with the
    reason and the note stored on it, and the proposer is told through the notification the
    rejection's audit row triggers. A field the body does not name answers 422
    `validation_error` rather than being dropped.

    A confirming agent rejects with the platform-only scope `proposals:review` and sends two
    more fields a person never sends: `decision`, the model call behind its rejection, and
    `agentRunId`, the open run of its own key it was made in (D-80). The first example is a
    person's rejection, the second an agent's.
    """

    rejection_code: str = Field(
        default="",
        description=(
            "Why the proposal is refused, as the key of a live row of the `rejection_reason` vocabulary, a "
            "library list: for example `duplicate`, `wrong_scope`, `poor_wording` or `outside_sector_scope`. "
            "Its rows are data an admin may extend, relabel or retire without a deploy, never a closed set, "
            "and `GET /vocab/rejection_reason` returns the live ones; compare the key, never the label. "
            "Required: left empty, or naming a key the list does not hold or has retired, the call answers "
            "422 `reason_required` and nothing is decided."
        ),
        examples=["duplicate"],
    )
    note: str = Field(
        default="",
        description=(
            "The reviewer's own sentence to the proposer, saying what is wrong in words they can act on, "
            "stored on the proposal and sent to them with the decision. Required, unlike on an approval: "
            "left empty or blank, the call answers 422 `reason_required`. It is the reviewer's comment on "
            "the request and never part of any library record's text."
        ),
        examples=["Version 2 already says this; the board decision changes nothing further."],
    )
    decision: AgentDecision | None = Field(default=None, description=_DECISION_DESCRIPTION)
    agent_run_id: UUID | None = Field(default=None, description=_RUN_DESCRIPTION, examples=[_RUN_EXAMPLE])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"rejectionCode": "duplicate", "note": "Version 2 already says this; the board decision changes nothing further."},
                {
                    "rejectionCode": "wrong_scope",
                    "note": "The board decision applies to retail clients only; the proposed scope names professional clients too.",
                    "decision": {
                        **_DECISION_EXAMPLE,
                        "output": (
                            "Reject. The board decision limits the rule to retail clients, and the proposal widens "
                            "its scope to professional clients, which the cited decision does not support."
                        ),
                    },
                    "agentRunId": _RUN_EXAMPLE,
                },
            ]
        }
    )


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
    order: str | None = Field(
        default=None,
        description=(
            "Which end of the queue comes first, by when each proposal was filed, with the id "
            "breaking a tie so paging is repeatable. The values are `oldest` (the default: the "
            "order proposals arrived in, which is how the Waiting tab is worked) and `newest` (the "
            "latest filed first, which is how the Approved and Rejected tabs read). Those are the "
            "only two values; anything else is refused with 422 `unknown_key`. Left out, the "
            "queue reads oldest first."
        ),
        examples=["newest"],
    )


# ---------------------------------------------------------------------------------------
# Batch proposals (PRO-04, AGT-05; c11-proposal-batches-create). A batch is one proposal
# with one row per library record it would change; the rows carry the preview a reviewer
# decides on, computed when the batch is filed (apps/proposals/batch.py).
# ---------------------------------------------------------------------------------------
_BATCH_EXAMPLE_ID = "6d0c4b1a-2f7e-4c3d-9a8b-1e5f7a9c3b20"
_BATCH_ROW_EXAMPLE_ID = "e4a7c2d9-5b1f-4e6a-8c3d-7f9b2a4c6e81"
_OBLIGATION_EXAMPLE_ID = "3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44"
_BATCH_SOURCE_EXAMPLE = "https://www.fi.se/en/published/news/2026/client-money/"


class ObligationScopeChange(WriteBody):
    """One obligation's part of a re-tag: the scope terms to add to it and the ones to take
    off it, with the source that says why. The rest of its scope stays as it is."""

    obligation_id: UUID = Field(
        description=(
            "The shared library obligation to re-tag, as the UUID `GET /obligations` returns. It must be "
            "in force and one of the library's own, else 422 `unknown_key`; a bank's private obligation "
            "never enters a batch. Each obligation appears once in a batch, else 422 `validation_error`."
        ),
        examples=[_OBLIGATION_EXAMPLE_ID],
    )
    add: TermRefs = Field(
        default_factory=list,
        max_length=settings.PROPOSAL_SCOPE_MAX_TERMS,
        description=(
            "Scope terms to put on the obligation, each written `dimension:key` as `GET /taxonomy/terms` "
            f"lists them, at most {settings.PROPOSAL_SCOPE_MAX_TERMS}. Every one must be a live term, else "
            "422 `unknown_key`; a term of a dimension that mirrors the jurisdiction list answers 422 "
            "`jurisdiction_term_mirrored`, because an obligation's market comes from its instrument. A term "
            "the obligation already carries changes nothing."
        ),
        examples=[["service_type:custody"]],
    )
    remove: TermRefs = Field(
        default_factory=list,
        max_length=settings.PROPOSAL_SCOPE_MAX_TERMS,
        description=(
            "Scope terms to take off the obligation, written and checked as `add` is, at most "
            f"{settings.PROPOSAL_SCOPE_MAX_TERMS}. A term the obligation does not carry changes nothing; "
            "one named in both `add` and `remove` answers 422 `validation_error`."
        ),
        examples=[["service_type:execution_only"]],
    )
    source: str = Field(
        max_length=settings.PROPOSAL_SOURCE_MAX_CHARS,
        description=(
            "Where the new scope comes from: an https link to the authority's page or the stable key of a "
            f"provision the library holds, at most {settings.PROPOSAL_SOURCE_MAX_CHARS} characters. Missing "
            "or blank answers 422 `source_missing`; anything else that is neither answers 422 "
            "`validation_error`. On a standard's obligation it is an https link only, else 422 "
            "`licensed_text`."
        ),
        examples=[_BATCH_SOURCE_EXAMPLE],
    )


class ObligationScopePayload(WriteBody):
    """The payload of the `obligation_scope` kind (PRO-04, AGT-05): a re-tag of many
    obligations, each changing only its scope terms, filed as one batch. Every obligation
    gets one row in the batch, previewed as its scope before and after. Checked in full when
    the batch is filed, as every other kind's payload is: live obligations, live terms, no
    mirrored jurisdiction term, and the standards rule (a standard's term only on a
    standard's obligation, which keeps exactly one)."""

    changes: list[ObligationScopeChange] = Field(
        min_length=1,
        description=(
            "One entry per obligation to re-tag, at least one and at most "
            f"{settings.PROPOSAL_BATCH_MAX_ROWS} (`PROPOSAL_BATCH_MAX_ROWS`); more answers 422 "
            "`batch_too_large`, so a larger re-tag is filed as more than one batch. An entry that would "
            "leave its obligation's scope exactly as it is answers 422 `validation_error`."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "changes": [
                        {
                            "obligationId": _OBLIGATION_EXAMPLE_ID,
                            "add": ["service_type:custody"],
                            "remove": [],
                            "source": _BATCH_SOURCE_EXAMPLE,
                        }
                    ]
                }
            ]
        }
    )


class ProposalBatchRowPayload(CamelSchema):
    """One side of a batch row's preview: the fields of the record that would change, and
    nothing else. For a re-tag that is the obligation's scope."""

    terms: TermRefs = Field(
        default_factory=list,
        description=(
            "The obligation's scope terms, each `dimension:key`, sorted. On `before` it is the scope the "
            "obligation carried when the batch was filed, read from the library then; on `after` the scope "
            "approving the row would leave it with. It is a preview: until the row is approved the library "
            "keeps the scope it has."
        ),
        examples=[["client_category:retail", "service_type:custody"]],
    )


class ProposalBatchRow(CamelSchema):
    """One record a batch would change, with the preview the reviewer decides on and the
    decision made on it. Library data from the platform queue: no bank's judgement and no
    tenant content is ever on a row."""

    id: UUID = Field(description="The row, as a UUID the server assigns once. A decision on the batch names rows by this id.", examples=[_BATCH_ROW_EXAMPLE_ID])
    subject_type: str = Field(
        description="What kind of library record the row changes. A fixed kind: `obligation`, a duty's scope, is the only one a batch changes today.",
        examples=["obligation"],
    )
    subject_id: UUID = Field(description="The library record the row changes, as a UUID, which is the id `GET /obligations/{obligationId}` takes.", examples=[_OBLIGATION_EXAMPLE_ID])
    target: ProposalTarget | None = Field(
        default=None,
        description="The record by its own title and reference, as the queue names a proposal's target. Null only if the record can no longer be read.",
    )
    before: ProposalBatchRowPayload = Field(description="The record's fields that would change, as the library held them when the batch was filed.")
    after: ProposalBatchRowPayload = Field(description="The same fields as approving this row would leave them. Nothing is written until then.")
    source: str = Field(
        default="",
        description="Where the change comes from, as the proposer gave it: an https link or a provision's stable key. It is a claim for the reviewer to open and check, not a verified fact.",
        examples=[_BATCH_SOURCE_EXAMPLE],
    )
    stale: bool = Field(
        default=False,
        description=(
            "True when the record has changed since the batch was filed, so `before` no longer says what "
            "the library holds: the row was previewed against another scope, and it cannot be approved; "
            "the batch is filed again instead. Computed when read, and only for a row still pending. False "
            "for a decided row, whatever the library says now."
        ),
        examples=[False],
    )
    decision: str = Field(
        description=(
            "Where the row stands. A fixed kind: `pending` waits for a reviewer, `approved` means the "
            "library carries its `after`, and `rejected` means it was refused with a reason and changed "
            "nothing. A row is decided once and never again."
        ),
        examples=["pending"],
    )
    rejection_code: str = Field(
        default="",
        description=(
            "Why the row was refused: the key of a row of the `rejection_reason` library list, which an "
            "admin may extend, so compare the key and show the label `GET /vocab/rejection_reason` gives. "
            "Empty unless `decision` is `rejected`."
        ),
        examples=[""],
    )
    decided_by: ProposalActorRef | None = Field(default=None, description="The platform person who decided the row, never the batch's proposer, which the database enforces. Null while pending.")
    decided_at: datetime | None = Field(default=None, description="When the row was decided: a UTC timestamp, date and time together. Null while pending.")


class ProposalBatch(ProposalRow):
    """A batch proposal as a reviewer reads it: the one proposal the queue lists, and every
    row beneath it with its preview. `isBatch` is true and `rowCount` counts `rows`. Every
    row is returned in one answer, since a batch holds at most `PROPOSAL_BATCH_MAX_ROWS`.
    Reading it changes nothing: until a row is approved the library says what it said."""

    rows: list[ProposalBatchRow] = Field(
        default_factory=list,
        description=f"Every row of the batch, at most {settings.PROPOSAL_BATCH_MAX_ROWS}, ordered by the record it changes so the order is the same on every read.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": _BATCH_EXAMPLE_ID,
                    "kind": "obligation_scope",
                    "status": "open",
                    "title": "Re-tag the client asset duties with custody",
                    "payload": {
                        "changes": [
                            {"obligationId": _OBLIGATION_EXAMPLE_ID, "add": ["service_type:custody"], "remove": [], "source": _BATCH_SOURCE_EXAMPLE}
                        ]
                    },
                    "sourceLabel": "Finansinspektionen, client money guidance 2026",
                    "sourceUrl": _BATCH_SOURCE_EXAMPLE,
                    "origin": "user",
                    "proposedBy": {"id": "0b6f2c4e-8d1a-4f3b-9e27-5c8a1d3f6b90", "name": "Kari Nygaard"},
                    "fromOrganisation": False,
                    "isBatch": True,
                    "rowCount": 1,
                    "createdAt": "2026-09-25T08:30:00Z",
                    "rows": [
                        {
                            "id": _BATCH_ROW_EXAMPLE_ID,
                            "subjectType": "obligation",
                            "subjectId": _OBLIGATION_EXAMPLE_ID,
                            "target": {
                                "id": _OBLIGATION_EXAMPLE_ID,
                                "title": "Keep client money apart from the firm's own",
                                "referenceLabel": "8 kap. 1 §",
                                "instrumentShortName": "FFFS 2017:2",
                            },
                            "before": {"terms": ["client_category:retail"]},
                            "after": {"terms": ["client_category:retail", "service_type:custody"]},
                            "source": _BATCH_SOURCE_EXAMPLE,
                            "stale": False,
                            "decision": "pending",
                            "rejectionCode": "",
                            "decidedBy": None,
                            "decidedAt": None,
                        }
                    ],
                }
            ]
        }
    )


class ProposalBatchInput(WriteBody):
    """The body of `POST /proposal-batches`: one request that changes many library records
    the same way, filed as one proposal with a row per record. Nothing in the library changes
    when it is accepted; each row waits for a second, independent reviewer. A field the body
    does not name answers 422 `validation_error` rather than being dropped."""

    kind: str = Field(
        description=(
            "What the batch changes. A fixed kind: `obligation_scope`, a re-tag of obligations' scope "
            "terms, is the only batch kind today; any other value answers 422 `unknown_key`."
        ),
        examples=["obligation_scope"],
    )
    title: str = Field(
        max_length=500,
        description="The request in one line, as the reviewer reads it in the queue, at most 500 characters and never blank (422 `validation_error`).",
        examples=["Re-tag the client asset duties with custody"],
    )
    payload: ObligationScopePayload = Field(description="The change per record, in the shape `kind` names.")
    agent_run_id: UUID | None = Field(
        default=None,
        description=(
            "The open run of the calling key the batch is filed under, as the UUID `POST /agent-runs` "
            "returned. Required from a key (none, or a closed run, answers 422 `run_not_open`; another "
            "key's run answers 404 `not_found`), and left out by a person."
        ),
        examples=[_RUN_EXAMPLE],
    )
    model: str = Field(default="", max_length=200, description="The model that drafted the request, at most 200 characters, when an agent did. Left empty by a person.", examples=[""])
    source_label: str = Field(
        default="",
        max_length=500,
        description="The batch's source in words, as a reviewer reads it beside the link, at most 500 characters. Under a standard it is the standard's official reference or empty, else 422 `licensed_text`.",
        examples=["Finansinspektionen, client money guidance 2026"],
    )
    source_url: str = Field(
        default="",
        max_length=2000,
        description="The authority's page the request was read from, at most 2000 characters, as an https link or left out; any other scheme answers 422 `validation_error`.",
        examples=[_BATCH_SOURCE_EXAMPLE],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "kind": "obligation_scope",
                    "title": "Re-tag the client asset duties with custody",
                    "payload": {
                        "changes": [
                            {"obligationId": _OBLIGATION_EXAMPLE_ID, "add": ["service_type:custody"], "remove": [], "source": _BATCH_SOURCE_EXAMPLE}
                        ]
                    },
                    "sourceLabel": "Finansinspektionen, client money guidance 2026",
                    "sourceUrl": _BATCH_SOURCE_EXAMPLE,
                }
            ]
        }
    )


class ProposalBatchRowDecision(WriteBody):
    """A reviewer's decision on one row of a batch."""

    row_id: UUID = Field(description="The row decided, as the UUID `ProposalBatchRow.id` names it.", examples=[_BATCH_ROW_EXAMPLE_ID])
    decision: str = Field(
        description="The decision. A fixed kind: `approved` lets the row's `after` into the library, `rejected` refuses it with `rejectionCode`.",
        examples=["rejected"],
    )
    rejection_code: str = Field(
        default="",
        description=(
            "Why the row is refused, as the key of a live row of the `rejection_reason` library list, for "
            "example `wrong_scope`; its rows are data an admin may extend, and `GET /vocab/rejection_reason` "
            "returns the live ones. Required for a rejection and left empty for an approval."
        ),
        examples=["wrong_scope"],
    )


class ProposalBatchDecision(WriteBody):
    """The body of `POST /proposal-batches/{batchId}/decide`: decisions on named rows, and
    one decision for every row left pending, so a reviewer rejects a few and approves the
    rest in one call."""

    rows: list[ProposalBatchRowDecision] = Field(
        default_factory=list,
        max_length=settings.PROPOSAL_BATCH_MAX_ROWS,
        description=f"The rows decided one by one, at most {settings.PROPOSAL_BATCH_MAX_ROWS}, each named once.",
    )
    rest: str | None = Field(
        default=None,
        description=(
            "One decision for every row this call does not name and that is still pending: `approved` or "
            "`rejected`, the same fixed kind a row's decision takes. Null leaves those rows pending."
        ),
        examples=["approved"],
    )
    rest_rejection_code: str = Field(
        default="",
        description="Why the rest are refused when `rest` is `rejected`: the key of a live row of the `rejection_reason` library list. Left empty otherwise.",
        examples=[""],
    )
    note: str = Field(default="", max_length=2000, description="The reviewer's own sentence to the proposer about the batch, at most 2000 characters. It is never part of any library record.", examples=["This duty concerns the firm's own assets, not client money."])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "rows": [{"rowId": _BATCH_ROW_EXAMPLE_ID, "decision": "rejected", "rejectionCode": "wrong_scope"}],
                    "rest": "approved",
                    "restRejectionCode": "",
                    "note": "This duty concerns the firm's own assets, not client money.",
                }
            ]
        }
    )


# ---------------------------------------------------------------------------------------
# The bank's own queue (INV-07, OWN-03; D-57, ADR 0050, ADR 0059; d89-proposal-owner)
# ---------------------------------------------------------------------------------------
_PRIVATE_EXAMPLE_ID = "5e2a7c1d-3b9f-4d6e-8a10-2c4f6b8d0e13"
_PRIVATE_ROW_EXAMPLE: dict[str, Any] = {
    "id": _PRIVATE_EXAMPLE_ID,
    "kind": "new_obligation",
    "status": "open",
    "title": "New obligation: report outsourced functions to the board every year",
    "origin": "agent",
    "isMine": False,
    "payload": {
        "key": "obl-nordbank-outsourcing-board-report",
        "instrument": "fffs-2026-9",
        "titles": {"en": "Report outsourced functions to the board every year"},
        "originalLanguage": "en",
        "isMachine": True,
        "refLabel": "4 kap. 5 §",
        "dutyType": "governance",
        "effectiveFrom": "2027-01-01",
        "terms": ["legal_entity:bank"],
    },
    "fieldSources": {"titles.en": "https://www.fi.se/sv/vara-register/forfattningssamling/fffs-2026-9/"},
    "sourceUrl": "https://www.fi.se/sv/vara-register/forfattningssamling/fffs-2026-9/",
    "createdAt": "2026-09-24T06:40:00Z",
}


class PrivateProposalRow(CamelSchema):
    """One proposal in this bank's own queue: a record of the bank's own, an instrument or an
    obligation the shared library does not hold, waiting for a person here to decide it
    (OWN-03). It belongs to this bank alone. The console never lists it, no other bank reads
    it, and no platform reviewer decides it.

    It is a request, not a record: until `status` is `approved` nothing of the bank's own
    inventory changes, and even then the record reads "Private to us" and is never a fact of
    the shared library. Whether it applies to the bank, and whether the bank complies, are
    decided in the register afterwards, never here.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [_PRIVATE_ROW_EXAMPLE]})

    id: UUID = Field(description="The proposal, as a UUID the server assigned when it was filed and never changes.")
    kind: str = Field(
        description=(
            "What the proposal adds or changes. A fixed kind, not a vocabulary row: `new_instrument` adds an "
            "instrument of the bank's own, `new_obligation` adds a duty of its own with its first version, "
            "and `new_obligation_version` adds a version to a duty the bank already holds as its own."
        )
    )
    status: str = Field(
        description=(
            "Where the request stands. A fixed kind: `open` is waiting for a person here to decide it, "
            "`approved` means the bank's own inventory now carries it, `rejected` means it was refused with a "
            "reason and changed nothing, and `superseded` means a later proposal overtook it."
        )
    )
    title: str = Field(description="The one-line request as its proposer wrote it, which is what the queue lists it under.")
    origin: str = Field(
        description=(
            "Who filed it. A fixed kind: `agent` means the bank's own research agent found it and a person has "
            "not confirmed it yet, so it reads as proposed by our agent; `user` means a person here filed it."
        )
    )
    is_mine: bool = Field(
        description=(
            "True when the reader filed it. Four eyes never lets them decide it, so a screen offers them no "
            "approve or reject button; the server refuses them either way."
        )
    )
    payload: dict[str, Any] = Field(  # schema: ProposalPayload
        default_factory=dict,
        description=(
            "What was proposed, in the shape its `kind` names (`ProposalPayload`), kept exactly as it arrived. "
            "It is the bank's own content and never leaves the bank."
        ),
    )
    field_sources: dict[str, str] = Field(  # schema: ProposalFieldSources
        default_factory=dict,
        description=(
            "Per field the proposal sets, where its value came from: an https link to the authority's public "
            "page. A source is the authority's page, not the bank's reading of it."
        ),
    )
    source_url: str = Field(default="", description="The https link to the authority's public page the new record is read from, which the record keeps as its own source.")
    created_at: datetime = Field(description="When it was filed: a UTC timestamp, date and time together, so the queue can order and date it.")


class PrivateProposalPage(CamelSchema):
    """A page of this bank's own queue, oldest first, with the count of every proposal in it."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_PRIVATE_ROW_EXAMPLE], "total": 1}]})

    items: list[PrivateProposalRow] = Field(description="This page of the bank's own proposals, oldest first, so the queue is worked in the order it was filed.")
    total: int = Field(description="How many of the bank's own proposals there are in all, across every page, so a screen can show a count without reading them.", examples=[1])


class PrivateProposalApproveBody(WriteBody):
    """The body of `POST /private-proposals/{proposalId}/approve`: a person's word that this
    record of the bank's own may enter the bank's own inventory. It needs
    `private_records.approve` and a fresh passkey step-up, and the approver is never the
    proposer. A field the body does not name answers 422 `validation_error`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"note": "Checked against FFFS 2026:9, 4 kap. 5 §."}]})

    note: str = Field(
        default="",
        max_length=2000,
        description=(
            "The approver's own sentence to the proposer, at most 2000 characters, stored on the proposal. "
            "Optional. It is a comment on the request and never part of the record's text."
        ),
        examples=["Checked against FFFS 2026:9, 4 kap. 5 §."],
    )


class PrivateProposalRejectBody(WriteBody):
    """The body of `POST /private-proposals/{proposalId}/reject`: why a person here turned a
    proposal of the bank's own down. Nothing changes in the bank's inventory, and the
    proposal is closed for good. A field the body does not name answers 422
    `validation_error`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"rejectionCode": "duplicate", "note": "We already hold this duty as our own."}]})

    rejection_code: str = Field(
        default="",
        description=(
            "Why the proposal is refused, as the key of a live row of the `rejection_reason` vocabulary: for "
            "example `duplicate`, `wrong_scope`, `poor_wording` or `outside_sector_scope`. Its rows are data an "
            "admin may extend, relabel or retire without a deploy, never a closed set, and "
            "`GET /vocab/rejection_reason` returns the live ones; compare the key, never the label. Required."
        ),
        examples=["duplicate"],
    )
    note: str = Field(
        default="",
        max_length=2000,
        description=(
            "The person's own sentence to the proposer saying what is wrong, at most 2000 characters, stored on "
            "the proposal. Required. It is a comment on the request and never part of any record's text."
        ),
        examples=["We already hold this duty as our own."],
    )
