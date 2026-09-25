"""Swedish collab mail strings. Keys match `en.py` exactly."""

from __future__ import annotations

STRINGS: dict[str, str] = {
    "header": "Hej {recipient},",
    "footer": "Skickat av {product}. Svar till den här adressen läses inte.",
    "due_soon.subject": "Förfaller {date}: {title}",
    "due_soon.body": "{title} ska vara klar den {date}.\nÖppna: {link}",
    "overdue.subject": "Försenad sedan {date}: {title}",
    "overdue.body": "{title} skulle ha varit klar den {date} och är inte klar än.\nÖppna: {link}",
    "review_due.subject": "Granskning senast {date}: {title}",
    "review_due.body": "Nästa granskning av {title} ska göras senast {date}.\nÖppna: {link}",
    "escalation.subject": "Eskalerad till dig: {title}",
    "escalation.body": (
        "{title}, som ägs av {name}, skulle ha varit klar den {date} och är fortfarande inte klar.\n"
        "Dagar försenad: {count}\nÖppna: {link}"
    ),
    "weekly_digest.subject": "Dina öppna uppgifter, veckan från {date}: {count}",
    "weekly_digest.body": "Dina öppna uppgifter per den {date}: {count}\nSe alla: {link}",
    "weekly_digest.overdue": "Försenade: {count}",
    "weekly_digest.due_soon": "Snart dags: {count}",
    "weekly_digest.aware": "Ändringar på dina uppgifter: {count}",
    "weekly_digest.open": "Allt du ansvarar för: {count}",
    "weekly_digest.item": "- {title}\n  {link}",
    "weekly_digest.more": "...och {count} till.",
}
