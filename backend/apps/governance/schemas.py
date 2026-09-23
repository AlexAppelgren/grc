"""Request and response schemas of the governance app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

The AI output log (AUD-02) is the second shape here. It holds what a model produced and
never the prompt that produced it: `promptTemplate` names the prompt and `promptHash`
identifies it, so a bank's own question can never be read back out of this log, by another
bank or by bleqq (NFR-04, D-07)."""

from __future__ import annotations

import uuid
from datetime import datetime

from django.conf import settings
from pydantic import ConfigDict, Field

# `AiCitation` lives beside `AgentDecision` in apps/shared/schemas.py, which cites with it
# and which a governance import would turn into a cycle; it is re-exported here for the
# modules that already read it from this app.
from apps.shared.schemas import AiCitation, AuditSnapshot, CamelSchema


class AuditEventQuery(CamelSchema):
    """Filters of the audit log, each optional. A record is `subjectType` and `subjectId`;
    `from` is inclusive and `to` exclusive."""

    subject_type: str | None = Field(default=None, max_length=64)
    subject_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None


class AuditActorRef(CamelSchema):
    """Who did it: a user, an agent or the system. `id` is empty for the system."""

    type: str
    id: uuid.UUID | None
    label: str


class AuditEventRow(CamelSchema):
    id: uuid.UUID
    created_at: datetime
    actor: AuditActorRef
    action: str
    subject_type: str
    subject_id: uuid.UUID | None
    subject_title: str
    summary: str
    before: AuditSnapshot
    after: AuditSnapshot
    stepped_up: bool


class AuditEventPage(CamelSchema):
    items: list[AuditEventRow]
    total: int


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
    "with the model behind it reported by that agent)"
)
_STATUSES = (
    "`draft` (nobody has stood behind it yet, which is how every row starts and how a "
    "screen knows to label the words as AI output), `confirmed` (a person accepted them as "
    "they stand), `edited` (a person rewrote them) and `rejected` (a person threw them "
    "away). Fixed in code: an admin adds no fifth state, because each is something the "
    "product does differently"
)


class AiGenerationQuery(CamelSchema):
    """Filters of the AI output log, each optional and combined with AND. Leaving both out
    lists everything the reader may see."""

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
            "characters. A value that is not one of them matches nothing and answers 200 "
            "with an empty page."
        ),
        examples=["draft"],
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
                    "reviewedAt": None,
                    "inputTokens": 1840,
                    "outputTokens": 96,
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
        description=f"How far a person has got with it, a fixed kind: {_STATUSES}.",
        examples=["draft"],
    )
    reviewed_at: datetime | None = Field(
        description=(
            "When a person moved the row out of `draft`, as an RFC 3339 timestamp in UTC "
            "(`2026-09-17T09:12:00Z`). Null while nobody has."
        ),
        examples=[None],
    )
    input_tokens: int = Field(
        description="How many tokens went into the call, as the provider counted them. 0 when unknown.",
        examples=[1840],
    )
    output_tokens: int = Field(
        description="How many tokens came back, as the provider counted them. 0 when unknown.",
        examples=[96],
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
