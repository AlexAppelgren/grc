"""Shared Pydantic schemas. snake_case in the database, camelCase in the API through the
alias generator on `CamelSchema` (playbook 4.1). Every app's schemas.py subclasses it.
Schema class names are global across apps (Ninja flattens components), so app-specific
shapes carry the app prefix."""

from __future__ import annotations

import unicodedata
from typing import Annotated, Any
from uuid import UUID

from django.conf import settings
from ninja import Schema
from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    RootModel,
    ValidationInfo,
    model_validator,
)
from pydantic.alias_generators import to_camel

# A pill's tone follows its slot or its row's kind, never a person's choice (NFR-03), so a
# write naming one is refused rather than dropped: the writer learns it is not theirs to set.
CHOSEN_TONE_KEYS = frozenset({"tone", "colour", "color"})


class CamelSchema(Schema):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


def _nul_at(value: Any, path: str) -> str | None:
    """Where in a request body a NUL character sits, as a dotted path of field names, or
    None. Keys are walked as well as values, since a key reaches a JSON column as it is;
    a key holding one is named by the object it sits in, so the key is never echoed."""
    if isinstance(value, str):
        return path if "\x00" in value else None
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and "\x00" in key:
                return path
            if (found := _nul_at(item, f"{path}.{key}" if path else str(key))) is not None:
                return found
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            if (found := _nul_at(item, f"{path}.{index}" if path else str(index))) is not None:
                return found
    return None


class WriteBody(CamelSchema):
    """A write's request body or a proposal's payload: a field the schema does not name
    answers 422 instead of being dropped, so a tone or a colour never rides along unseen
    (NFR-S10). Response schemas stay open, so a new field never breaks an older client.

    No string anywhere in it, nested or a key, may hold a NUL character (`\\x00`):
    PostgreSQL refuses one in a text column, so it answered 500 on every free-text write
    (hardening H39). It is refused with a 422 naming where it sat; the value is not echoed."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _no_nul(cls, values: Any) -> Any:
        if (where := _nul_at(values, "")) is not None:
            raise ValueError(f"{where or 'The body'} cannot contain a NUL character.")
        return values


# Unicode's control (Cc) and format (Cf) categories: line breaks, tabs, NUL, and the
# invisible marks that reorder or hide text (bidi overrides, zero-width characters).
_NOT_IN_A_NAME = frozenset({"Cc", "Cf"})


def _single_line(value: str) -> str:
    if any(unicodedata.category(character) in _NOT_IN_A_NAME for character in value):
        raise ValueError("A name is one line of visible text: no line breaks, tabs or invisible characters.")
    return value


# A name a person gives something that other people then read in a list, a heading or a
# mail's subject line: a bank, a team, a role. It refuses every control and format
# character, so a line break cannot break the mail the name goes into and a bidi override
# cannot make it read as something else (hardening H38).
SingleLineName = Annotated[str, AfterValidator(_single_line)]


class LibraryResponse(CamelSchema):
    """A response the server builds from plain values, never from an ORM object, and
    pydantic validates natively when it is built. Ninja's own root validator wraps every
    value in its Django getter, one Python call per field of every nested object, which was
    most of a page's server time (NFR-02, measured 2026-09-19). Ninja answers a validated
    instance of the route's response type as it is, without validating it again.

    Declared here rather than in apps/library/schemas.py because `AgentRef`, which the
    taxonomy's list and term reads share with the library's, is built on it too, and the
    library's schemas import the taxonomy's."""

    @model_validator(mode="wrap")
    @classmethod
    def _run_root_validator(cls, values: Any, handler: ModelWrapValidatorHandler[Any], info: ValidationInfo) -> Any:
        # Replaces ninja.Schema's validator of the same name, which wraps `values` in its getter.
        return handler(values)


def _no_chosen_tone(extra: dict[str, Any]) -> dict[str, Any]:
    chosen = sorted(key for key in extra if key.casefold() in CHOSEN_TONE_KEYS)
    if chosen:
        raise ValueError(f"{', '.join(chosen)} cannot be set: a value's tone follows its kind.")
    return extra


class NamedRef(LibraryResponse):
    """A record named on another, as every screen and list reads it: the id to store and
    compare, and a name to show. A person, a unit of the bank's organisation or one of its
    agent access entries; the field that carries the reference says which. A person's id and
    name are the only personal data a record carries about them (playbook 4.7)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lindqvist"}]})

    id: UUID = Field(
        description=(
            "The record's identifier, a UUID that never changes, the same one its own list and the "
            "audit log carry. Store and compare this, never the name."
        ),
        examples=["8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60"],
    )
    name: str = Field(
        description=(
            "The record's name for display only: a person's name as they gave it, or the name the "
            "bank gave a unit or an entry. It may change at any time and two records may share it, "
            "so nothing may match on it."
        ),
        examples=["Sara Lindqvist"],
    )


class VocabRef(LibraryResponse):
    """A row of a vocabulary as every picker, pill, filter and export reads it: the key to
    store and compare, the kind when its list has one, and the label in the reader's language
    (playbook 15). The field that carries the reference names the list and the endpoint that
    returns its live set. A tone is never here: a pill's tone follows its slot or the row's
    own kind and is nobody's to send (NFR-03)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"key": "act_now", "kind": None, "label": "Act now"}]},
        json_schema_serialization_defaults_required=True,
    )

    key: str = Field(
        description=(
            "The row's immutable key, and the only part of this reference to store, compare or send "
            "back. Which vocabulary it is drawn from is settled by the field that carries the "
            "reference, which names the list and the endpoint that returns its live set: the shared "
            "library's vocabularies and taxonomy terms, which an admin may extend through an approved "
            "proposal, a bank's own lists such as its roles, teams, tags and statuses, which the bank's "
            "admin may extend, relabel, reorder or retire without a deploy, and the platform's fixed "
            "lists such as the languages. A key you have not seen before is new data and not an error. "
            "Match on the key and never on the label, and never construct one: a key the list does not "
            "hold answers 422 `unknown_key` with the valid keys."
        ),
        examples=["act_now"],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "The row's fixed kind where its list has one, so a screen can branch or pick a pill tone "
            "without reading the label, and null by default where it has none. By list: a jurisdiction "
            "is `supranational` (the European Union), `country` (one national market) or `international` "
            "(a standards body such as ISO/IEC); an urgency is its pill tone, one of `information`, "
            "`notice`, `positive`, `warning`, `negative` and `brand`; a change type is its lifecycle "
            "kind; a case sub-status is its case category (`new`, `assigned`, `assessing`, "
            "`implementing`, `signoff`, `closed` or `dismissed`) and a close reason one of `signed_off`, "
            "`no_action` or `not_applicable`; a compliance status is `compliant`, `partly`, `gap` or "
            "`not_assessed` and a gap status `open`, `remediating`, `risk_accepted` or `closed`; a "
            "taxonomy dimension is `scope` (its terms say who or what a rule covers), `classification` "
            "(its terms only describe a record) or `opt_in` (the standards a bank follows). Where one "
            "field carries rows of more than one list, it is the list's name. A taxonomy term, a "
            "language, a role, a team, a tag, a risk rating and a link kind are null. Kinds are fixed "
            "in code, so the rules may branch on them; an admin never adds one."
        ),
        examples=[None],
    )
    label: str = Field(
        description=(
            "The row's label in the reader's language: the caller's own language first, then the "
            "organisation's default language, then English, then any label the row has, and the key "
            "itself when it has none; a language reads in itself, such as `Svenska`. For display only: a "
            "person wrote it and may reword or translate it at any time, so nothing may match on it."
        ),
        examples=["Act now"],
    )


# A vocabulary write's `extra`: the list's own columns (an urgency's ordinal and SLA days),
# never a tone or a colour (NFR-S10).
VocabularyExtra = Annotated[dict[str, Any], AfterValidator(_no_chosen_tone)]


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
    """One message the stand-in mailer sent during an end-to-end test run. Test
    environments only: a deployed environment never returns one."""

    to: str = Field(
        description=(
            "The one address the message went to, as the sender wrote it. A message to "
            "several people is several entries, so a test filters on this to find the mail "
            "meant for the person it is driving."
        )
    )
    subject: str = Field(
        description=(
            "The subject line as sent, in plain text, for example the enrolment code mail or "
            "an invitation naming the bank. It is written for a person to read, so a test "
            "should find its mail by address and read the code or link from the body rather "
            "than match on this wording."
        )
    )
    body: str = Field(
        description=(
            "The plain-text body as sent, lines separated by a newline. It carries whatever "
            "the mail carried, including a one-time enrolment code or an invitation link "
            "whose token rides after the `#`, which is exactly why the outbox is readable "
            "only in a test environment and never where a real person's mail is sent."
        )
    )


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
                    "promptTemplate": "library-confirmer/decide/v2",
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
        examples=["library-confirmer/decide/v2"],
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
