"""The collab mails (COL-02, I18N-01): the reminders before and after a due date, the reminder
of a next review, the escalation and the weekly digest, each composed in the recipient's own
language from the catalog in `mail_strings/`.

Only these leave by mail; every other notification stays in the product (CHUNK10_TASKS
default). Plain text, like every mail the product sends. Three rules decide what may be in
one, and each of them is a product invariant rather than a style choice:

- **Typed context only.** A template can interpolate a record title (a library title, or a
  bank's own action, case or register entry), a date, a count, a person's name or a link,
  because `MailContext` has no other field. A comment, a note, an assessment or a summary
  has nowhere to go (CHUNK10_TASKS rule 13).
- **A link stays in the product.** It must start with `APP_BASE_URL`, so a link cannot carry
  text of its own to another host.
- **Nothing here is logged.** Not the address, not the subject, not the body (playbook 4.7).
  A string missing from the recipient's language falls back to English and logs its key.

`send()` hands the mail to `tasks.deliver_mail` once the caller's transaction commits, the
path `identity/mail.py` uses; the task composes it, sends it and writes the `email_message`
row that makes a second send the same day do nothing.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import string
import uuid
from typing import Literal, get_args

from django.conf import settings
from django.db import transaction

from apps.collab.mail_strings import CATALOGS, FALLBACK_LANGUAGE
from apps.identity.models import Membership
from apps.shared.adapters.mailer import OutgoingMail

logger = logging.getLogger(__name__)

Template = Literal["due_soon", "overdue", "review_due", "escalation", "weekly_digest"]
TEMPLATES: tuple[str, ...] = get_args(Template)
# What the composer fills itself, beside the context: whom the mail greets and who sent it.
COMPOSER_FIELDS = ("recipient", "product")


@dataclasses.dataclass(frozen=True)
class MailContext:
    """Everything a collab mail may say about its record, and nothing else.

    `title` is a record's own title, `date` a plain date, `count` a number of items or days,
    `name` a person's name and `link` a page of the product. Titles and names are folded to
    one line, because a subject line cannot hold a line break.
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


def compose(membership: Membership, template: Template, context: MailContext) -> OutgoingMail:
    """One recipient's copy of one mail, in their language: the header, the template's body
    and the footer, under the template's subject. A recipient with no language, or one the
    catalog does not hold, reads English."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown collab mail template {template!r}")
    user = membership.user
    language = user.locale.key if user.locale else FALLBACK_LANGUAGE
    values = {key: value for key, value in dataclasses.asdict(context).items() if value is not None}
    values["date"] = context.date.isoformat() if context.date else None
    values["recipient"] = user.name
    values["product"] = settings.PRODUCT_NAME
    parts = [
        _string(language, key).format(**values) for key in ("header", f"{template}.body", "footer")
    ]
    return OutgoingMail(
        to=user.email,
        subject=_string(language, f"{template}.subject").format(**values),
        body="\n\n".join(parts),
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
    if settings.CELERY_TASK_ALWAYS_EAGER:
        # Tests: inline, now. `on_commit` never fires inside a TestCase transaction.
        tasks.deliver_mail.apply(args=args)
        return
    transaction.on_commit(lambda: tasks.deliver_mail.delay(*args))
