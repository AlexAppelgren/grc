"""English collab mail strings. Keys match `sv.py` exactly."""

from __future__ import annotations

STRINGS: dict[str, str] = {
    "header": "Hello {recipient},",
    "footer": "Sent by {product}. Replies to this address are not read.",
    "due_soon.subject": "Due {date}: {title}",
    "due_soon.body": "{title} is due on {date}.\nOpen it: {link}",
    "overdue.subject": "Overdue since {date}: {title}",
    "overdue.body": "{title} was due on {date} and is not done yet.\nOpen it: {link}",
    "review_due.subject": "Review due {date}: {title}",
    "review_due.body": "The next review of {title} is due on {date}.\nOpen it: {link}",
    "escalation.subject": "Escalated to you: {title}",
    "escalation.body": (
        "{title}, owned by {name}, was due on {date} and is still not done.\nDays overdue: {count}\nOpen it: {link}"
    ),
    "weekly_digest.subject": "Your open items, week of {date}: {count}",
    "weekly_digest.body": "Your open items as of {date}: {count}\nSee them all: {link}",
    # The digest's sections, My work's four buckets in its order, each row a title and a link.
    "weekly_digest.overdue": "Overdue: {count}",
    "weekly_digest.due_soon": "Due soon: {count}",
    "weekly_digest.aware": "Changes on your items: {count}",
    "weekly_digest.open": "Everything you're responsible for: {count}",
    "weekly_digest.item": "- {title}\n  {link}",
    "weekly_digest.more": "...and {count} more.",
}
