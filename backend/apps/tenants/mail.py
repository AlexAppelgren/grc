"""The mail tenants sends: a bank's `security.manage` holders hear that platform support asked
to read their bank (TEN-06, D-49). Delivered by the identity worker after the request's
transaction commits, like every other mail (`apps/identity/mail.py`). Plain text, English for
now, until `c10-mail-catalog` gives every mail the reader's language. The purpose and ticket
are platform support's own words, written for the bank; nothing here is logged."""

from __future__ import annotations

from django.conf import settings
from django.db import transaction

from apps.identity import tasks


def send_support_request(to: str, *, tenant_name: str, requester: str, purpose: str, ticket_ref: str, hours: int) -> None:
    ticket = f"\nTicket: {ticket_ref}" if ticket_ref else ""
    subject = f"{settings.PRODUCT_NAME} support asks to read {tenant_name}"
    body = (
        f"{requester} from {settings.PRODUCT_NAME} support asks for read-only access to {tenant_name} "
        f"for {hours} hours.\nPurpose: {purpose}{ticket}\n"
        "Nothing is granted until an administrator approves it under Support access, and the "
        f"request lapses if nobody decides within {settings.SUPPORT_ACCESS_REQUEST_TTL_HOURS} hours."
    )
    if settings.CELERY_TASK_ALWAYS_EAGER:
        # Tests: inline, now, as identity's mail does; `on_commit` never fires in a TestCase.
        tasks.deliver_mail.apply(args=(to, subject, body))
        return
    transaction.on_commit(lambda: tasks.deliver_mail.delay(to, subject, body))
