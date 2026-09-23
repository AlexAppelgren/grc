"""Request and response schemas of the governance app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

The AI output log (AUD-02) is the second shape here. It holds what a model produced and
never the prompt that produced it: `promptTemplate` names the prompt and `promptHash`
identifies it, so a bank's own question can never be read back out of this log, by another
bank or by bleqq (NFR-04, D-07)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from django.conf import settings
from pydantic import ConfigDict, Field

# `AiCitation` lives beside `AgentDecision` in apps/shared/schemas.py, which cites with it
# and which a governance import would turn into a cycle; it is re-exported here for the
# modules that already read it from this app.
from apps.shared.schemas import AiCitation, AuditSnapshot, CamelSchema


class AuditEventQuery(CamelSchema):
    """Filters of the audit log, each optional and combined with AND. A record is `subjectType`
    and `subjectId`; `from` is inclusive and `to` exclusive."""

    subject_type: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Show only the rows about one kind of record, by the kind key a row carries in "
            "`subjectType`, such as `footprint_change_request`, `membership` or `obligation`; "
            "pair it with `subjectId` to read one record's history. Matched exactly, at most "
            "64 characters; a longer value is refused with `validation_error` (422). A kind no "
            "row carries matches nothing and answers 200 with an empty page, because a filter "
            "that finds nothing is an empty answer and not an error."
        ),
        examples=["footprint_change_request"],
    )
    subject_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Show only the rows about one record, by the UUID a row carries in `subjectId`. "
            "For most kinds that is the id the API uses for the record, such as a footprint "
            "change request's id; a `membership` row carries the membership's own id, which "
            "the API does not otherwise show, and not the member's `userId`, so take it from a "
            "row. A value that is not a UUID is refused with `validation_error` (422); an id "
            "no row names answers 200 with an empty page."
        ),
        examples=["4a7c1e9b-3d5f-4b2a-8e6c-0f1d3b5a7c92"],
    )
    actor_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Show only what one person or agent did, by the UUID a row carries in `actor.id`: "
            "a person's user id, or for an agent the agent its key is bound to (the key's own "
            "id for a key bound to no agent). The system has no id, so its rows cannot be "
            "picked out this way. A value that is not a UUID is refused with "
            "`validation_error` (422); an actor who did nothing here answers 200 with an empty "
            "page."
        ),
        examples=["8f3b6a0e-2c71-4d95-b8e4-1a7c9d2f5e30"],
    )
    from_: datetime | None = Field(
        default=None,
        alias="from",
        description=(
            "Show only rows written at or after this moment (inclusive), as an ISO 8601 "
            "timestamp such as `2026-09-16T00:00:00+02:00`. Give the offset: a value without "
            "one, or a date alone, is read as UTC (a date as midnight UTC) and not as the "
            "bank's local time. In the query string write the offset's `+` as `%2B` (or use "
            "`Z`): a bare `+` arrives as a space. A value that is not a timestamp is refused "
            "with `validation_error` (422). A `from` later than `to` matches nothing and "
            "answers 200 with an empty page."
        ),
        examples=["2026-09-16T00:00:00+02:00"],
    )
    to: datetime | None = Field(
        default=None,
        description=(
            "Show only rows written before this moment (exclusive), so `from` one midnight and "
            "`to` the next is exactly one day and back-to-back windows never count a row "
            "twice. An ISO 8601 timestamp such as `2026-09-17T00:00:00+02:00`, read like "
            "`from`: without an offset it is UTC, the `+` is sent as `%2B`, and a value that is "
            "not a timestamp is refused with `validation_error` (422)."
        ),
        examples=["2026-09-17T00:00:00+02:00"],
    )


# The actor kinds of apps.shared.audit.ActorType, closed in the contract so a client sees all three.
AuditActorKind = Literal["user", "agent", "system"]


class AuditActorRef(CamelSchema):
    """Who did it: a user, an agent or the system. `id` is empty for the system."""

    type: AuditActorKind = Field(
        description=(
            "What kind of actor made the change, a fixed kind: `user` (a person, either a "
            "member of this bank or bleqq's platform staff changing the shared library), "
            "`agent` (an agent working through its key; it cannot step up, so its rows "
            "always carry `steppedUp` false, and a proposal it confirmed "
            "is machine-confirmed and never a person's decision) and `system` (the product "
            "itself, such as a seed or a scheduled job). Fixed in code: an admin adds no "
            "fourth kind."
        ),
        examples=["user"],
    )
    id: uuid.UUID | None = Field(
        description=(
            "Who acted, as a UUID: a person's user id, or for an agent the agent its key is "
            "bound to (the key's own id for a key bound to no agent). Null for the system, "
            "which has no identity of its own. Pass it as `actorId` to list everything this "
            "actor did."
        ),
        examples=["8f3b6a0e-2c71-4d95-b8e4-1a7c9d2f5e30"],
    )
    label: str = Field(
        max_length=200,
        description=(
            "The actor's name as it stood when the row was written, at most 200 characters, "
            "for display: a person's name; for an agent, the key of the agent its key is bound "
            "to (such as `library-confirmer`), with the agent's version where the row records "
            "one (`library-confirmer v1`), or `api key <id>` for a key bound to no agent; for "
            "the system, the job's name (`system` when it gave none). A snapshot that is "
            "never updated, so a person renamed later keeps the old name here: match on `id`, "
            "never on the label."
        ),
        examples=["Erik Holm"],
    )


class AuditEventRow(CamelSchema):
    """One change in the bank's audit log (AUD-01): who made it, what happened to which record,
    and the record's fields before and after. Written in the same transaction as the change and
    never edited afterwards; a later change to the same record is a new row."""

    id: uuid.UUID = Field(
        description=(
            "The audit row's identifier, as a UUID. A row is written once and never changed, "
            "so the id names the same facts for good."
        ),
        examples=["5d0e8c2a-91b4-4f6e-a3d7-0c8b2e6f4a19"],
    )
    created_at: datetime = Field(
        description=(
            "When the row was written, as an RFC 3339 timestamp in UTC "
            "(`2026-09-16T08:14:00Z`), taken from the server's clock inside the change's own "
            "transaction. It is the moment of writing and not of committing, so a change that "
            "took longer to commit can show up after rows with a later time. The log is ordered "
            "by it, newest first, and `from` and `to` compare against it: to poll for new rows, "
            "start `from` a little before the newest time already seen and drop the rows whose "
            "`id` you already have."
        ),
        examples=["2026-09-16T08:14:00Z"],
    )
    actor: AuditActorRef = Field(
        description=(
            "Who made the change: a person, an agent or the system, with the id to filter on "
            "and the name as it stood at the time."
        )
    )
    action: str = Field(
        max_length=100,
        description=(
            "What happened, as a machine key of the form `<record>.<event>` of at most 100 "
            "characters, such as `member.updated`, `footprint.change_approved`, "
            "`library.problem_reported` or `obligation.version_applied`. Written by the code that made "
            "the change, and the set grows as the product records new kinds of change, so show "
            "a key you do not know rather than fail on it. It is a key to compare and filter "
            "on, not a sentence: `summary` is the sentence."
        ),
        examples=["member.updated"],
    )
    subject_type: str = Field(
        max_length=64,
        description=(
            "What kind of record changed, as a snake_case kind key of at most 64 characters, "
            "such as `membership`, `tenant_role` or `footprint_change_request` for the bank's "
            "own records. The shared library's kinds are `authority`, `instrument`, "
            "`provision`, `obligation`, `vocabulary` and `taxonomy_term`: a row about one of "
            "those is either the bank's own act on that record, such as a problem it reported, "
            "or a change to the library itself made by an agent, the system or bleqq's "
            "platform staff, which every bank sees; `action` says which. `vocabulary` also "
            "covers this bank's own lists, which its administrators edit: its `subjectTitle` "
            "starts with the list's name (`<list>:<key>`), and the list says whether it is the "
            "library's or the bank's. Written by the code, and the set grows as features ship. "
            "Filter on it with `subjectType`."
        ),
        examples=["membership"],
    )
    subject_id: uuid.UUID | None = Field(
        description=(
            "The record that changed, as a UUID, which `subjectId` filters on. For most kinds "
            "it is the id the API uses for that record, so a screen can link to it; a few kinds "
            "name a row the API does not otherwise show, such as `membership`, whose id is the "
            "membership's own and not the member's `userId`. Null for a change about no single "
            "record."
        ),
        examples=["b2c4e6f8-0a1c-4e3a-9b5d-7f9e1d3c5a70"],
    )
    subject_title: str = Field(
        max_length=500,
        description=(
            "The record's name as it read when the change was made, at most 500 characters, "
            "such as a member's name, an obligation's stable key or `<list>:<key>` for a list "
            "value. A snapshot: a record renamed later keeps its old title here, which is what "
            "an audit trail is for. Empty when the record has no name."
        ),
        examples=["Johan Berg"],
    )
    summary: str = Field(
        max_length=1000,
        description=(
            "One sentence saying what happened, at most 1000 characters, written in English by "
            "the code that made the change and not translated. Read it as the row's caption; "
            "`before` and `after` hold the detail."
        ),
        examples=["Member roles or title changed."],
    )
    before: AuditSnapshot = Field(
        description=(
            "The record's fields before the change, keyed by field name, as the code that made "
            "the change chose to record them: usually only what changed, sometimes with context "
            "such as a version number. Values are JSON as stored. An empty object (`{}`) when "
            "there was nothing before, such as a creation. The keys differ by `subjectType` "
            "and are not a fixed schema, so show them rather than branch on them."
        ),
        examples=[{"roles": ["contributor"], "title": "Obligation owner, digital investing"}],
    )
    after: AuditSnapshot = Field(
        description=(
            "The record's fields after the change, in the same shape as `before`: compare the "
            "two field by field, and a field present on one side only was added or removed. "
            "An empty object (`{}`) when the change left nothing to show."
        ),
        examples=[{"roles": ["contributor", "owner"], "title": "Obligation owner, digital investing"}],
    )
    stepped_up: bool = Field(
        description=(
            "True when the person who made the change confirmed it with a fresh passkey "
            "step-up, which the product demands for approvals, sign-off, footprint changes, "
            "exports, key creation, role and security changes and re-enrolment. Always false "
            "for an agent or the system, neither of which can step up: a decision an agent "
            "confirmed is machine-confirmed and never reads as a person's passkey-backed one."
        ),
        examples=[True],
    )


class AuditEventPage(CamelSchema):
    """One page of the bank's audit log, newest change first."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "5d0e8c2a-91b4-4f6e-a3d7-0c8b2e6f4a19",
                            "createdAt": "2026-09-16T08:14:00Z",
                            "actor": {"type": "user", "id": "8f3b6a0e-2c71-4d95-b8e4-1a7c9d2f5e30", "label": "Erik Holm"},
                            "action": "member.updated",
                            "subjectType": "membership",
                            "subjectId": "b2c4e6f8-0a1c-4e3a-9b5d-7f9e1d3c5a70",
                            "subjectTitle": "Johan Berg",
                            "summary": "Member roles or title changed.",
                            "before": {"roles": ["contributor"], "title": "Obligation owner, digital investing"},
                            "after": {"roles": ["contributor", "owner"], "title": "Obligation owner, digital investing"},
                            "steppedUp": True,
                        },
                        {
                            "id": "e7a1c3f5-4b2d-4e8f-8a6c-1d3f5b7e9c02",
                            "createdAt": "2026-09-16T07:40:00Z",
                            "actor": {"type": "agent", "id": "3c5e7a9b-1d2f-4a6c-8e0b-2f4a6c8e0d13", "label": "library-confirmer v1"},
                            "action": "obligation.version_applied",
                            "subjectType": "obligation",
                            "subjectId": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
                            "subjectTitle": "obl-research-payments",
                            "summary": "Filed version 2 of obl-research-payments (proposal 9d4f2b6a-0c8e-4a1f-b3d5-6e8a0c2f4b17).",
                            "before": {"versionNumber": 1, "terms": None},
                            "after": {
                                "versionNumber": 2,
                                "versionId": "0a2c4e6f-8b1d-4f3a-9c5e-7b9d1f3a5c68",
                                "effectiveFrom": "2027-01-01",
                                "effectiveFromPrecision": "day",
                                "languages": ["en", "sv"],
                                "terms": None,
                                "proposal": "9d4f2b6a-0c8e-4a1f-b3d5-6e8a0c2f4b17",
                            },
                            "steppedUp": False,
                        },
                    ],
                    "total": 2,
                }
            ]
        }
    )

    items: list[AuditEventRow] = Field(
        description=(
            "The rows of this page, newest first, with rows written in the same instant ordered "
            "by `id`, descending. Empty when nothing matches, which is a 200 and never an error."
        )
    )
    total: int = Field(
        description=(
            "How many rows match the filters in total, counted at the moment of the call and "
            "not only on this page, so a screen can say “n of m” and know when to stop paging."
        ),
        examples=[2],
    )


# ---------------------------------------------------------------------------------------
# AUD-02: the AI output log
# ---------------------------------------------------------------------------------------
_PURPOSES = (
    "`so_what` (the drafted “So what?” filed with a regulatory change), "
    "`change_summary` (a plain-language summary of a change), `scope_suggestion` (a "
    "suggested scope term or flag), `link_suggestion` (a suggested obligation link), "
    "`translation` (a machine translation of library text), `answer` (an Ask answer for "
    "one bank) and `agent_review` (a confirming agent's decision on another agent's work: "
    "approving, correcting or rejecting a proposal, or confirming a watch item's curation, "
    "with the model behind it reported by that agent; only the platform reads these, so a "
    "bank's log never lists one)"
)
_STATUSES = (
    "`draft` (nobody has stood behind it yet, which is how every row starts and how a "
    "screen knows to label the words as AI output), `confirmed` (a person accepted them as "
    "they stand), `edited` (a person rewrote them) and `rejected` (a person threw them "
    "away). Fixed in code: an admin adds no fifth state, because each is something the "
    "product does differently"
)


class AiGenerationQuery(CamelSchema):
    """Filters of the AI output log, each optional and combined with AND. Leaving all three
    out lists everything the reader may see."""

    purpose: str | None = Field(
        default=None,
        max_length=32,
        description=(
            f"Show only calls made for one purpose, a fixed kind: {_PURPOSES}. At most 32 "
            "characters. A value that is not one of them matches nothing and answers 200 "
            "with an empty page, because a filter that finds nothing is an empty answer and "
            "not an error."
        ),
        examples=["so_what"],
    )
    status: str | None = Field(
        default=None,
        max_length=16,
        description=(
            f"Show only rows in one review state, a fixed kind: {_STATUSES}. At most 16 "
            "characters. It reads the state as this bank sees it (see `status` on a row), so "
            "`confirmed` lists a shared “So what?” this bank stood behind and not "
            "one only another bank did. A value that is not one of them matches nothing and "
            "answers 200 with an empty page."
        ),
        examples=["draft"],
    )
    subject_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Show only the calls about one record, by the UUID a row carries in `subjectId`: "
            "for a “So what?” the regulatory change's id, so a change's screen can "
            "list every draft of what it means. A value that is not a UUID is refused with "
            "`validation_error` (422); an id no row names answers 200 with an empty page."
        ),
        examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"],
    )


class AiGenerationReviewer(CamelSchema):
    """The person who stood behind a model's output: id and name, the only personal data
    the log carries about them (playbook 4.7)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"id": "8f3b6a0e-2c71-4d95-b8e4-1a7c9d2f5e30", "name": "Anna Lindqvist"}]}
    )

    id: uuid.UUID = Field(
        description="The person's user id, as a UUID.",
        examples=["8f3b6a0e-2c71-4d95-b8e4-1a7c9d2f5e30"],
    )
    name: str = Field(
        description="The person's name as it stands now, at most 200 characters, for display.",
        examples=["Anna Lindqvist"],
    )


class AiGenerationRow(CamelSchema):
    """One model call and what it produced (AUD-02)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "1f6c3b70-2a48-4e91-9d05-7b2c8f4a1e63",
                    "purpose": "so_what",
                    "model": "claude-opus-5",
                    "modelVersion": "2026-05-01",
                    "modelMetadataReportedByAgent": True,
                    "promptTemplate": "watch-sweeper/so-what/v1",
                    "promptHash": "9f2a1c7d4b8e05f3",
                    "subjectType": "regulatory_change",
                    "subjectId": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
                    "output": "Teams that pay for external research should confirm that documented criteria exist.",
                    "citations": [
                        {
                            "label": "Finansinspektionen, decision memorandum FI Dnr 25-12345",
                            "url": "https://www.fi.se/en/published/news/2026/reporting/",
                        }
                    ],
                    "status": "draft",
                    "reviewedBy": None,
                    "reviewedAt": None,
                    "feedback": "",
                    "feedbackNote": "",
                    "inputTokens": 1840,
                    "outputTokens": 96,
                    "stopReason": "",
                    "tenantScoped": False,
                    "createdAt": "2026-09-16T06:02:00Z",
                }
            ]
        }
    )

    id: uuid.UUID = Field(
        description="The log row's identifier, as a UUID. Stable: a row is never rewritten in place.",
        examples=["1f6c3b70-2a48-4e91-9d05-7b2c8f4a1e63"],
    )
    purpose: str = Field(
        description=f"What the call was for, a fixed kind: {_PURPOSES}.",
        examples=["so_what"],
    )
    model: str = Field(
        description=(
            "Which model wrote it, as the provider names it, at most 200 characters. Read it "
            "beside `modelMetadataReportedByAgent`: for an agent's filing it is that agent's "
            "own word rather than a measurement bleqq took."
        ),
        examples=["claude-opus-5"],
    )
    model_version: str = Field(
        description=(
            "Which version of that model, at most 120 characters, so two answers months "
            "apart can be told apart. Empty only for a row written before a version was "
            "recorded."
        ),
        examples=["2026-05-01"],
    )
    model_metadata_reported_by_agent: bool = Field(
        description=(
            "Whether `model` and `modelVersion` were reported by the agent that made the "
            "call rather than observed by bleqq's own wrapper around the model (D-66). True "
            "for anything an agent filed together with the record it had just read; false "
            "for a call bleqq made itself, such as an Ask answer. In R1 every agent is "
            "bleqq's own, so this is a reporting boundary; it becomes a trust boundary the "
            "day a bank runs its own agent against the write routes, and this field is how a "
            "reader tells the two apart. Computed by the server, never sent by a caller."
        ),
        examples=[True],
    )
    prompt_template: str = Field(
        description=(
            "Which prompt was used, by name and version, at most 200 characters, so an "
            "output can be traced to the instructions behind it. Empty when the caller named "
            "none. The prompt's text is never stored and never returned."
        ),
        examples=["watch-sweeper/so-what/v1"],
    )
    prompt_hash: str = Field(
        description=(
            "A hash of the prompt actually sent, at most 128 characters, so two calls can be "
            "compared without the prompt being kept. This is the whole record of the input: "
            "no prompt text is stored anywhere, which is what keeps a bank's own words out "
            "of a log every bank can read (NFR-04)."
        ),
        examples=["9f2a1c7d4b8e05f3"],
    )
    subject_type: str = Field(
        description=(
            "What kind of record the call was about, such as `regulatory_change`, at most 32 "
            "characters. Empty for a call about no particular record. The record is named, "
            "never its text."
        ),
        examples=["regulatory_change"],
    )
    subject_id: uuid.UUID | None = Field(
        description="The record the call was about, as a UUID, or null when it was about no record.",
        examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"],
    )
    output: str = Field(
        description=(
            f"What the model wrote, at most {settings.AI_GENERATION_OUTPUT_MAX_CHARS} "
            "characters; a longer output is stored up to that length, because the log keeps "
            "the record and not the whole transcript. Do not quote it as anybody's position "
            "while `status` is `draft`: AI output stays labelled until a person confirms it."
        ),
        examples=["Teams that pay for external research should confirm that documented criteria exist."],
    )
    citations: list[AiCitation] = Field(
        description=(
            "The public pages the output rests on, so a reader can check it. An empty list "
            "means the call cited nothing, not that its sources were withheld."
        )
    )
    status: str = Field(
        description=(
            f"How far a person has got with it, a fixed kind: {_STATUSES}. Computed for the "
            "reading bank. On a bank's own row it is that row's state. A shared “So "
            "what?” (`tenantScoped` false) is one row every bank reads and no bank may "
            "move, so its state here is this bank's own, taken from this bank's case for the "
            "change and never written to the shared row: `confirmed` when someone here "
            "confirmed the draft as it stands, `edited` when they rewrote it, and `draft` "
            "otherwise. A case settles the newest draft of the change logged by the time it "
            "was confirmed, so an earlier draft, or one logged after the confirmation, reads "
            "`draft` because nobody here stood behind those words. Another bank's decision "
            "never shows."
        ),
        examples=["draft"],
    )
    reviewed_by: AiGenerationReviewer | None = Field(
        description=(
            "Who moved the row out of `draft`, computed for the reading bank as `status` is: "
            "on a shared “So what?” the person at this bank who confirmed or rewrote "
            "it on the case. Null while `status` is `draft`."
        ),
        examples=[None],
    )
    reviewed_at: datetime | None = Field(
        description=(
            "When a person moved the row out of `draft`, as an RFC 3339 timestamp in UTC "
            "(`2026-09-17T09:12:00Z`), computed for the reading bank as `status` is. Null "
            "while nobody has."
        ),
        examples=[None],
    )
    feedback: str = Field(
        description=(
            "A reader's verdict on an Ask answer, at most 16 characters: `helpful` or "
            "`wrong`, as `POST /answers/{answerId}/feedback` stored it, and the latest verdict "
            "when it was given more than once. Empty when nobody gave one, and always empty "
            "on a row that is not an Ask answer. Source: a person in this bank."
        ),
        examples=[""],
    )
    feedback_note: str = Field(
        description=(
            "What the reader wrote with the verdict, as they wrote it, at most "
            f"{settings.SEARCH_FEEDBACK_NOTE_MAX_CHARS} characters, the limit "
            "`POST /answers/{answerId}/feedback` accepts. Empty when they wrote nothing or "
            "gave no verdict. It is this bank's own text and appears only on this bank's own "
            "row."
        ),
        examples=[""],
    )
    input_tokens: int = Field(
        description="How many tokens went into the call, as the provider counted them. 0 when unknown.",
        examples=[1840],
    )
    output_tokens: int = Field(
        description="How many tokens came back, as the provider counted them. 0 when unknown.",
        examples=[96],
    )
    stop_reason: str = Field(
        description=(
            "How a call bleqq made ended, at most 64 characters: `end_turn` (the model "
            "finished), `max_tokens` or `model_context_window_exceeded` (the model stopped at "
            "a limit, so `output` is cut short), `aborted` (the caller stopped reading before "
            "the model finished, such as a reader closing an Ask answer; `output` holds what "
            "was written by then), `failed` (the model failed once asked; `output` holds what "
            "arrived first, possibly nothing), or another stop reason the provider names in "
            "its own snake_case word. Token counts are 0 on an `aborted` or `failed` row, "
            "because the provider reports usage only with its last word. Empty on a row an "
            "agent filed (`modelMetadataReportedByAgent`), whose call bleqq did not watch "
            "end, and on a row written before this was recorded. Source: the server."
        ),
        examples=["end_turn"],
    )
    tenant_scoped: bool = Field(
        description=(
            "Whether the row is the reading bank's own (true) or the shared library's "
            "(false). A library row — the drafted “So what?” of a change — is the "
            "same row every bank sees, and no bank may confirm, rewrite or delete it: a "
            "bank's own confirmation of a “So what?” lives on its case. Computed by "
            "the server."
        ),
        examples=[False],
    )
    created_at: datetime = Field(
        description="When the call was made, as an RFC 3339 timestamp in UTC (`2026-09-16T06:02:00Z`).",
        examples=["2026-09-16T06:02:00Z"],
    )


class AiGenerationPage(CamelSchema):
    """One page of the AI output log, newest call first."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [], "total": 0}]})

    items: list[AiGenerationRow] = Field(
        description=(
            "The rows of this page, newest call first. Empty when nothing matches, which is "
            "a 200 and never an error."
        )
    )
    total: int = Field(
        description=(
            "How many rows match the filters in total, counted at the moment of the call and "
            "not only on this page, so a screen can say “n of m”."
        ),
        examples=[0],
    )
