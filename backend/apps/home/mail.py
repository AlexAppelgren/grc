"""The weekly briefing mail (HOM-02, I18N-02), composed in the recipient's own language.

English and Swedish, which is what R1's banks read; `c10-mail-catalog` extends this to the
other three content languages with the rest of the product's mail (chunk 6 ruling 21). A
language this module does not hold falls back to English rather than sending nothing.

Plain text, like every other mail the product sends. Three rules decide what may be in it,
and each of them is a product invariant rather than a style choice:

- **Library facts and a confirmed judgement only.** The week's titles are the library's; the
  "So what?" travels only once a person has confirmed it. An unconfirmed draft is still an
  agent's reading, it is labelled as one on screen, and a mail carries no label a reader can
  see — so it never leaves this way (WAT-05).
- **No case note, no owner, no other bank.** A mail lands in an inbox outside our control.
- **Nothing here is logged.** Not the address, not the subject, not the body (playbook 4.7).

The link points at the snapshot, not at the running week, so opening it in a month shows
what the mail said rather than what the feed has become.
"""

from __future__ import annotations

import datetime

from django.conf import settings

from apps.shared.adapters.mailer import OutgoingMail

FALLBACK_LANGUAGE = "en"

# One entry per language: the subject line, the opening, what introduces the lead's "So
# what?", the heading over the rest of the week and the closing line with the link. The week
# is named by its dates rather than by its ISO number, because a person reads dates.
_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject": "This week in regulation: {week_start} to {week_end}",
        "opening": "Here is what reached {tenant} between {week_start} and {week_end}.",
        "lead": "Leading this week: {title}",
        "so_what": "What it means for us: {so_what}",
        "also": "Also this week:",
        "quiet": "Nothing new matched your regulatory scope this week.",
        "closing": "Read the full briefing: {url}",
    },
    "sv": {
        "subject": "Veckans regelnyheter: {week_start} till {week_end}",
        "opening": "Det här nådde {tenant} mellan {week_start} och {week_end}.",
        "lead": "Veckans viktigaste: {title}",
        "so_what": "Vad det betyder för oss: {so_what}",
        "also": "Också den här veckan:",
        "quiet": "Inget nytt matchade er regulatoriska omfattning den här veckan.",
        "closing": "Läs hela sammanfattningen: {url}",
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
    """One recipient's copy of one week.

    `titles` are the week's changes in the briefing's own order, so the first is the lead.
    `confirmed_so_what` is empty unless a person has confirmed the lead's "So what?", and an
    empty one simply leaves that line out — a mail never says an agent's draft is a bank's
    view of a rule.
    """
    texts = _TEXTS.get(locale or FALLBACK_LANGUAGE, _TEXTS[FALLBACK_LANGUAGE])
    dates = {"week_start": week_start.isoformat(), "week_end": week_end.isoformat()}
    lines = [texts["opening"].format(tenant=tenant_name, **dates), ""]
    if titles:
        lines.append(texts["lead"].format(title=titles[0]))
        if confirmed_so_what:
            lines.append(texts["so_what"].format(so_what=confirmed_so_what))
        if titles[1:]:
            lines.extend(["", texts["also"], *(f"- {title}" for title in titles[1:])])
    else:
        lines.append(texts["quiet"])
    lines.extend(["", texts["closing"].format(url=briefing_url(week_start))])
    return OutgoingMail(to=to, subject=texts["subject"].format(**dates), body="\n".join(lines))
