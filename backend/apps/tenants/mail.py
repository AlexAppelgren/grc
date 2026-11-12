"""The mail tenants sends: a bank's `security.manage` holders hear that platform support asked
to read their bank (TEN-06, D-49). Delivered by the identity worker after the request's
transaction commits (`apps/identity/mail.py`), as plain text and in the shared HTML layout.
English for now. The purpose and ticket are platform support's own words, written for the
bank; nothing here is logged."""

from __future__ import annotations

from django.conf import settings

from apps.identity import mail
from apps.shared.mail_layout import Facts, Small, Text


def send_support_request(to: str, *, tenant_name: str, requester: str, purpose: str, ticket_ref: str, hours: int) -> None:
    asks = f"{requester} from {settings.PRODUCT_NAME} support asks for read-only access to {tenant_name} for {hours} hours."
    facts = [("Purpose", purpose), *([("Ticket", ticket_ref)] if ticket_ref else [])]
    rule = (
        "Nothing is granted until an administrator approves it under Support access, and the "
        f"request lapses if nobody decides within {settings.SUPPORT_ACCESS_REQUEST_TTL_HOURS} hours."
    )
    lines = [asks, *(f"{label}: {value}" for label, value in facts), rule]
    mail.deliver(
        to,
        f"{settings.PRODUCT_NAME} support asks to read {tenant_name}",
        "\n".join(lines),
        [Text(asks), Facts(facts), Small(rule)],
        tenant_name,
    )
