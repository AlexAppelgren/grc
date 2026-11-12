"""The weekly briefing mail (HOM-02, I18N-02) in the recipient's language, as plain text
and in the shared HTML layout (`apps/shared/mail_layout.py`); English and Swedish so far,
any other language falls back to English.

- Library facts and a confirmed judgement only: an unconfirmed "So what?" is an agent's
  reading and a mail carries no label, so it never leaves this way (WAT-05).
- No case note, no owner, no other bank: a mail lands outside our control.
- Nothing here is logged (playbook 4.7).

The link points at the snapshot, so it says the same thing in a month. `send()` queues the
mail after the caller's transaction commits, so the snapshot is stored before any mail
leaves (H21).
"""

from __future__ import annotations

import datetime
import uuid

from django.conf import settings

from apps.shared import mail_layout
from apps.shared.adapters.mailer import OutgoingMail
from apps.shared.mail_layout import Block, Button, Items, Lead, Text
from apps.shared.tasks import queue_after_commit

FALLBACK_LANGUAGE = "en"

# Per language: subject, opening, the labels of the lead, its "So what?", the rest and the
# link, the line for a quiet week and the footer of the HTML part. The week is named by its
# dates, because a person reads dates.
_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject": "This week in regulation: {week_start} to {week_end}",
        "opening": "Here is what reached {tenant} between {week_start} and {week_end}.",
        "lead": "Leading this week",
        "so_what": "What it means for us",
        "also": "Also this week",
        "quiet": "Nothing new matched your regulatory scope this week.",
        "closing": "Read the full briefing",
        "footer": "Sent by {product}. Replies to this address are not read.",
    },
    "sv": {
        "subject": "Veckans regelnyheter: {week_start} till {week_end}",
        "opening": "Det här nådde {tenant} mellan {week_start} och {week_end}.",
        "lead": "Veckans viktigaste",
        "so_what": "Vad det betyder för oss",
        "also": "Också den här veckan",
        "quiet": "Inget nytt matchade er regulatoriska omfattning den här veckan.",
        "closing": "Läs hela sammanfattningen",
        "footer": "Skickat av {product}. Svar till den här adressen läses inte.",
    },
}


def briefing_url(week_start: datetime.date) -> str:
    """Where the snapshot lives. A past week, addressed by its Monday, so the link says the
    same thing in a month as it does today."""
    return f"{settings.APP_BASE_URL.rstrip('/')}/briefing/{week_start.isoformat()}"


def weekly_briefing(
    *,
    to: str,
    locale: str | None,
    tenant_name: str,
    week_start: datetime.date,
    week_end: datetime.date,
    titles: list[str],
    confirmed_so_what: str,
) -> OutgoingMail:
    """One recipient's copy of one week. `titles` are in briefing order, the lead first.
    An empty `confirmed_so_what` leaves that line out: a mail never presents an agent's draft
    as the bank's view.
    """
    language = locale if locale in _TEXTS else FALLBACK_LANGUAGE
    texts = _TEXTS[language]
    dates = {"week_start": week_start.isoformat(), "week_end": week_end.isoformat()}
    subject = texts["subject"].format(**dates)
    opening = texts["opening"].format(tenant=tenant_name, **dates)
    url = briefing_url(week_start)
    lines = [opening, ""]
    blocks: list[Block] = [Text(opening)]
    if titles:
        lines.append(f"{texts['lead']}: {titles[0]}")
        if confirmed_so_what:
            lines.append(f"{texts['so_what']}: {confirmed_so_what}")
        blocks.append(Lead(texts["lead"], titles[0], texts["so_what"], confirmed_so_what))
        if titles[1:]:
            lines.extend(["", f"{texts['also']}:", *(f"- {title}" for title in titles[1:])])
            blocks.append(Items(texts["also"], [(title, None) for title in titles[1:]]))
    else:
        lines.append(texts["quiet"])
        blocks.append(Text(texts["quiet"]))
    lines.extend(["", f"{texts['closing']}: {url}"])
    blocks.append(Button(texts["closing"], url))
    return OutgoingMail(
        to=to,
        subject=subject,
        body="\n".join(lines),
        html=mail_layout.render(
            title=subject,
            blocks=blocks,
            footer=texts["footer"].format(product=settings.PRODUCT_NAME),
            tenant_name=tenant_name,
            language=language,
        ),
    )


def send(tenant_id: uuid.UUID, message_id: uuid.UUID) -> None:
    """Deliver one queued briefing mail once the caller's transaction commits."""
    from apps.home import tasks

    queue_after_commit(tasks.deliver_briefing, (str(tenant_id), str(message_id)))
