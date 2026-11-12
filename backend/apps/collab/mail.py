"""The collab mails (COL-02, I18N-01): due-date and next-review reminders, the escalation and
the weekly digest, in the recipient's language from `mail_strings/`. Only these leave by
mail; every other notification stays in the product. Each is plain text and the same lines in
the shared HTML layout (`apps/shared/mail_layout.py`).

- Typed context only: `MailContext` holds a title, date, count, name or link, so a comment,
  note, assessment or summary has nowhere to go (CHUNK10_TASKS rule 13).
- A link must start with `APP_BASE_URL`, so it cannot carry text to another host.
- Nothing is logged (playbook 4.7), except the key of a string missing in a language.
- One catalog for both parts: a catalog line that ends in `: {link}` is the mail's button in
  HTML, its words before the colon the label, and a digest row is its title as a link.

`send()` queues `tasks.deliver_mail` after commit; its `email_message` row makes a second
send the same day do nothing.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import string
import uuid
from collections.abc import Sequence
from typing import Literal, get_args

from django.conf import settings

from apps.collab.mail_strings import CATALOGS, FALLBACK_LANGUAGE
from apps.identity.models import Membership
from apps.shared import mail_layout
from apps.shared.adapters.mailer import OutgoingMail
from apps.shared.mail_layout import Block, Button, Items, Text
from apps.shared.tasks import queue_after_commit

logger = logging.getLogger(__name__)

Template = Literal["due_soon", "overdue", "review_due", "escalation", "weekly_digest"]
TEMPLATES: tuple[str, ...] = get_args(Template)
# What the composer fills itself, beside the context: whom the mail greets and who sent it.
COMPOSER_FIELDS = ("recipient", "product")
# How a catalog line ends when it is the mail's action: the label, then the page it opens.
ACTION = ": {link}"


@dataclasses.dataclass(frozen=True)
class MailContext:
    """Everything a collab mail may say about its record, and nothing else. Titles and names
    are folded to one line, since a subject line cannot hold a line break.
    """

    title: str | None = None
    date: datetime.date | None = None
    count: int | None = None
    name: str | None = None
    link: str | None = None

    def __post_init__(self) -> None:
        for field in ("title", "name", "link"):
            value = getattr(self, field)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"MailContext.{field} must be text")
        if self.date is not None and (
            not isinstance(self.date, datetime.date) or isinstance(self.date, datetime.datetime)
        ):
            raise TypeError("MailContext.date must be a plain date")
        if self.count is not None and (
            not isinstance(self.count, int) or isinstance(self.count, bool) or self.count < 0
        ):
            raise TypeError("MailContext.count must be a whole number, zero or more")
        if self.link is not None and not self.link.startswith(
            settings.APP_BASE_URL.rstrip("/") + "/"
        ):
            raise ValueError("MailContext.link must be a page of the product")
        for field in ("title", "name"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, " ".join(value.split()))

    def to_task(self) -> dict[str, str | int]:
        """The context as the delivery task's argument: JSON values, the date as ISO."""
        values = {field.name: getattr(self, field.name) for field in dataclasses.fields(self)}
        return {
            key: value.isoformat() if isinstance(value, datetime.date) else value
            for key, value in values.items()
            if value is not None
        }

    @classmethod
    def from_task(cls, values: dict[str, str | int]) -> MailContext:
        date, count = values.get("date"), values.get("count")
        return cls(
            title=_text(values.get("title")),
            date=datetime.date.fromisoformat(date) if isinstance(date, str) else None,
            count=count if isinstance(count, int) else None,
            name=_text(values.get("name")),
            link=_text(values.get("link")),
        )


def _text(value: str | int | None) -> str | None:
    return value if isinstance(value, str) else None


def placeholders(text: str) -> set[str]:
    """The names a catalog string interpolates."""
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def _string(language: str, key: str) -> str:
    catalog = CATALOGS.get(language, {})
    if key in catalog:
        return catalog[key]
    logger.warning("collab mail string %s fell back to %s", key, FALLBACK_LANGUAGE)
    return CATALOGS[FALLBACK_LANGUAGE][key]


def compose(
    membership: Membership,
    template: Template,
    context: MailContext,
    *,
    sections: Sequence[Sequence[tuple[str, MailContext]]] = (),
    tenant_name: str = "",
) -> OutgoingMail:
    """One recipient's copy of one mail in their language (English by default): header,
    body and footer under the template's subject. `sections` are extra paragraphs built from
    the template's own keys and typed context, so they can say no more than the body. The
    HTML part says the same lines in the same order, under `tenant_name`, the bank the mail
    is about: the caller passes it, so composing reads no row."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown collab mail template {template!r}")
    user = membership.user
    language = user.locale.key if user.locale else FALLBACK_LANGUAGE

    def fill(text: str, values: MailContext) -> str:
        filled = {name: value for name, value in dataclasses.asdict(values).items() if value is not None}
        filled["recipient"] = user.name
        filled["product"] = settings.PRODUCT_NAME
        return text.format(**filled)

    def render(key: str, values: MailContext) -> str:
        return fill(_string(language, key), values)

    def section_block(section: Sequence[tuple[str, MailContext]]) -> Block:
        """A digest section in HTML: its heading over its rows, each row the title as a link.
        A section with no row, the count the cap left out, is a paragraph."""
        heading = " ".join(render(key, values) for key, values in section if values.link is None)
        rows = [(values.title or "", values.link) for _key, values in section if values.link is not None]
        return Items(heading, rows) if rows else Text(heading)

    for section in sections:
        for key, _values in section:
            if not key.startswith(f"{template}."):
                raise ValueError(f"{key!r} is not a string of the {template!r} mail")
    subject, header, footer = (render(key, context) for key in (f"{template}.subject", "header", "footer"))
    body = _string(language, f"{template}.body")
    parts = [
        header,
        fill(body, context),
        *("\n".join(render(key, values) for key, values in section) for section in sections),
        footer,
    ]
    lines = body.split("\n")
    blocks: list[Block] = [
        Text(header),
        *(Text(fill(line, context)) for line in lines if not line.endswith(ACTION)),
        *(section_block(section) for section in sections),
        # The button closes the mail, under the sections it sums up.
        *(Button(fill(line.removesuffix(ACTION), context), context.link or "") for line in lines if line.endswith(ACTION)),
    ]
    return OutgoingMail(
        to=user.email,
        subject=subject,
        body="\n\n".join(parts),
        html=mail_layout.render(title=subject, blocks=blocks, footer=footer, tenant_name=tenant_name, language=language),
    )


def send(
    membership: Membership,
    template: Template,
    context: MailContext,
    *,
    subject_type: str | None,
    subject_id: uuid.UUID | None,
) -> None:
    """Mail one member about one record once the caller's transaction commits. The record
    (`subject_type`, `subject_id`) is what makes a second send the same day do nothing; the
    digest, which names no record, passes neither."""
    from apps.collab import tasks

    compose(
        membership, template, context
    )  # refuse a bad template or context here, not in the worker
    args = (
        str(membership.tenant_id),
        str(membership.user_id),
        template,
        context.to_task(),
        subject_type,
        str(subject_id) if subject_id else None,
    )
    queue_after_commit(tasks.deliver_mail, args)
