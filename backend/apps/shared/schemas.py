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
    """What a sign-in page needs before anyone has signed in: the product's own name."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"productName": "Compliance Watch"}]})

    product_name: str = Field(
        description=(
            "The name this deployment of the product goes by, for a sign-in page to show "
            "before anyone has signed in; a passkey prompt names the service by the same "
            "name. The platform operator sets it for each deployment, so a rebrand changes "
            "it without a new release: show what this returns rather than a name of your "
            "own. It is the product's name and never a bank's; nothing about any bank or "
            "person is in it."
        )
    )


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
            "The subject line as sent, in plain text, for example the sign-in code mail or "
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
