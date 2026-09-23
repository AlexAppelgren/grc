"""Shared Pydantic schemas. snake_case in the database, camelCase in the API through the
alias generator on `CamelSchema` (playbook 4.1). Every app's schemas.py subclasses it.
Schema class names are global across apps (Ninja flattens components), so app-specific
shapes carry the app prefix."""

from __future__ import annotations

from typing import Annotated, Any

from django.conf import settings
from ninja import Schema
from pydantic import AfterValidator, ConfigDict, Field, RootModel
from pydantic.alias_generators import to_camel

# A pill's tone follows its slot or its row's kind, never a person's choice (NFR-03), so a
# write naming one is refused rather than dropped: the writer learns it is not theirs to set.
CHOSEN_TONE_KEYS = frozenset({"tone", "colour", "color"})


class CamelSchema(Schema):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class WriteBody(CamelSchema):
    """A write's request body or a proposal's payload: a field the schema does not name
    answers 422 instead of being dropped, so a tone or a colour never rides along unseen
    (NFR-S10). Response schemas stay open, so a new field never breaks an older client."""

    model_config = ConfigDict(extra="forbid")


def _no_chosen_tone(extra: dict[str, Any]) -> dict[str, Any]:
    chosen = sorted(key for key in extra if key.casefold() in CHOSEN_TONE_KEYS)
    if chosen:
        raise ValueError(f"{', '.join(chosen)} cannot be set: a value's tone follows its kind.")
    return extra


# A vocabulary write's `extra`: the list's own columns (an urgency's ordinal and SLA days),
# never a tone or a colour (NFR-S10).
VocabularyExtra = Annotated[dict[str, Any], AfterValidator(_no_chosen_tone)]


class ProductInfo(CamelSchema):
    product_name: str


class PageQuery(Schema):
    """Pagination on every list (playbook 10): `limit` default 20, max 100, `offset`.
    The numbers come from settings; a value above the maximum is a 422, not a clamp.
    `offset` is bounded too: PostgreSQL walks every skipped row and raises above a signed
    64-bit integer, so an unbounded offset answers 500 on every list (hardening H1)."""

    limit: int = Field(
        default=settings.API_PAGE_SIZE_DEFAULT,
        ge=1,
        le=settings.API_PAGE_SIZE_MAX,
        description=(
            f"How many records to return in one page: {settings.API_PAGE_SIZE_DEFAULT} by "
            f"default, {settings.API_PAGE_SIZE_MAX} at most and 1 at least. A larger number "
            "is refused with a 422 rather than quietly trimmed, so a short page always means "
            "the data ran out and never that the server capped you without saying so."
        ),
        examples=[settings.API_PAGE_SIZE_DEFAULT],
    )
    offset: int = Field(
        default=0,
        ge=0,
        le=settings.API_PAGE_OFFSET_MAX,
        description=(
            "How many records to skip before this page begins, counting from 0: with the "
            f"default page size, `offset={settings.API_PAGE_SIZE_DEFAULT}` is the second "
            f"page. The deepest offset accepted is {settings.API_PAGE_OFFSET_MAX}, because "
            "PostgreSQL walks every skipped row and an unbounded offset answered 500 on every "
            "list (hardening H1); narrow the list with filters rather than paging past it. "
            "Totals are counted at the moment of the call, so a record written between two "
            "pages can shift what the later page holds."
        ),
        examples=[0],
    )


class MailOutboxMessage(CamelSchema):
    """One message the mock mailer sent, for E2E journeys (playbook 8.3)."""

    to: str
    subject: str
    body: str


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


# ---------------------------------------------------------------------------------------
# AUD-02, D-66, D-80: what an agent reports about the model call behind its words
# ---------------------------------------------------------------------------------------
class AiCitation(CamelSchema):
    """One public page the model's output rests on, so a reader can check a sentence
    against its source rather than trusting it. Stored on the generation row as JSON."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "label": "Finansinspektionen, decision memorandum FI Dnr 25-12345",
                    "url": "https://www.fi.se/en/published/news/2026/reporting/",
                }
            ]
        }
    )

    label: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "How the cited source reads in a sentence, 1 to 500 characters, in the "
            "publisher's own words. Source: reported by whoever made the model call. Do not "
            "read it as a verified reference; it is checked by opening `url`."
        ),
        examples=["Finansinspektionen, decision memorandum FI Dnr 25-12345"],
    )
    url: str = Field(
        min_length=1,
        max_length=2000,
        pattern=r"^https?://",
        description=(
            "The public page the citation points at, 1 to 2000 characters starting with "
            "http:// or https://, so the claim can be opened and read; any other address is "
            "refused with a 422 naming the field. Source: the public source the model was "
            "given. It is always a public page: no bank's own record is ever cited here, "
            "because nothing from a bank's zone reaches a prompt (NFR-04, D-07)."
        ),
        examples=["https://www.fi.se/en/published/news/2026/reporting/"],
    )


# Said in the shape and in every route that takes it, so nobody reads it as bleqq's own
# measurement (D-66, D-80).
_DECISION_REPORTED = (
    "Reported by the agent that made the decision, not measured by bleqq (D-80, as D-66 "
    "for a drafted “So what?”). In R1 every agent is bleqq's own, so this is a reporting "
    "boundary; it becomes a trust boundary the day a bank runs its own reviewing agent."
)


class AgentDecision(WriteBody):
    """The model call behind a confirming agent's decision on another agent's work:
    approving, correcting or rejecting a proposal, or confirming a watch item's curation.

    An agent's decision is a model call, and every model call is logged (AUD-02), so the
    agent sends this with the decision and the write turns it into one `ai_generation` row
    under the purpose `agent_review`, marked as reported by the agent, naming the run the
    decision was made in and the proposal or change it was about (D-80). A decision sent
    without a model, a version or a citation is refused rather than logged as one nobody
    can attribute or check.

    Public facts only: the sources a confirming agent reads are the pages the proposal or
    the change already cites, and nothing from a bank's zone ever reaches its prompt
    (NFR-04, D-07)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "model": "claude-opus-5",
                    "modelVersion": "2026-05-01",
                    "promptTemplate": "library-confirmer/decide/v1",
                    "promptHash": "9f2a1c7d4b8e05f3",
                    "output": (
                        "Approve. The proposed wording matches the amended regulation as the "
                        "decision memorandum publishes it, and the date it applies from is the "
                        "one the memorandum states."
                    ),
                    "citations": [
                        {
                            "label": "Finansinspektionen, decision memorandum FI Dnr 25-12345",
                            "url": "https://www.fi.se/en/published/news/2026/reporting/",
                        }
                    ],
                }
            ]
        }
    )

    model: str = Field(
        min_length=1,
        max_length=120,
        description=(
            "Which model made the decision, as the provider names it, 1 to 120 characters. "
            f"{_DECISION_REPORTED} Required: a decision nobody can attribute to a model is not "
            "something the AI output log can record, so the call is refused rather than stored."
        ),
        examples=["claude-opus-5"],
    )
    model_version: str = Field(
        min_length=1,
        max_length=120,
        description=(
            "Which version of that model, 1 to 120 characters, so two decisions months apart "
            f"can be told apart. {_DECISION_REPORTED} Required, for the same reason as `model`."
        ),
        examples=["2026-05-01"],
    )
    prompt_template: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Which prompt produced the decision, by name and version, at most 200 characters, "
            "so an odd decision can be traced to the instructions behind it. Optional. Send "
            "the name, never the prompt: bleqq stores no prompt text at all."
        ),
        examples=["library-confirmer/decide/v1"],
    )
    prompt_hash: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "A hash of the prompt actually sent, at most 128 characters, so two calls can be "
            "compared without either prompt being kept. Optional, and the only thing about "
            "the input that is stored."
        ),
        examples=["9f2a1c7d4b8e05f3"],
    )
    output: str = Field(
        min_length=1,
        max_length=settings.AI_GENERATION_OUTPUT_MAX_CHARS,
        description=(
            "What the model concluded and why, 1 to "
            f"{settings.AI_GENERATION_OUTPUT_MAX_CHARS} characters: the decision in words and "
            "what in the cited sources supports it, or what they did not support. Longer is "
            "refused with a 422 naming the field rather than cut short. It is stored as AI "
            "output, labelled as such, and never reads as a person's review."
        ),
        examples=["Approve. The proposed wording matches the amended regulation as published."],
    )
    citations: list[AiCitation] = Field(
        min_length=1,
        max_length=settings.AI_GENERATION_CITATIONS_MAX,
        description=(
            "The public pages the decision rests on, at least one and at most "
            f"{settings.AI_GENERATION_CITATIONS_MAX}; none, or more, answers 422 naming the "
            "field. At least one, because a decision a reader cannot check against a source "
            "is not one to let into the shared library. Every citation is a public page: no "
            "bank's own record is ever cited, because nothing from a bank's zone reaches the "
            "prompt (NFR-04, D-07)."
        ),
    )
