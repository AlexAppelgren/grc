"""The three emails identity sends (ID-01, ID-02, ID-05). Each is composed here and
delivered by the worker (`apps/identity/tasks.py`), enqueued when the request's
transaction commits, so the request itself never waits on a mail relay and a code
request costs the same whether or not a mail follows (finding F12). Plain text, English
for now: the message catalogs are a frontend concern and a mail catalog is a later
chunk. The invitation link is the only place a plain invitation token ever appears
(ID-S1)."""

from __future__ import annotations

from django.conf import settings
from django.db import transaction

from apps.identity import tasks


def _deliver(to: str, subject: str, body: str) -> None:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        # Tests: inline, now. `on_commit` never fires inside a TestCase transaction, and
        # the assertion is about the message, not the queue.
        tasks.deliver_mail.apply(args=(to, subject, body))
        return
    transaction.on_commit(lambda: tasks.deliver_mail.delay(to, subject, body))


def invitation_link(token: str) -> str:
    """The token rides in the fragment, which a browser never sends to any server, proxy
    or `Referer` header, so no request line ever holds it (security review F29). The page
    reads it and posts it in the body of `POST /auth/invitations/open`."""
    return f"{settings.APP_BASE_URL.rstrip('/')}/invite#{token}"


def send_code(to: str, code: str) -> None:
    minutes = settings.ENROLMENT_CODE_TTL_MINUTES
    _deliver(
        to,
        f"Your {settings.PRODUCT_NAME} enrolment code",
        f"Your code is {code}. It works once and expires in {minutes} minutes.",
    )


def send_invitation(to: str, token: str, tenant_name: str | None, *, reenrolment: bool) -> None:
    where = tenant_name or settings.PRODUCT_NAME
    hours = settings.INVITATION_TTL_HOURS
    if reenrolment:
        subject = f"Set up your passkey again for {where}"
        lead = "An administrator re-issued your enrolment. Your earlier passkeys and sessions no longer work."
    else:
        subject = f"You are invited to {where}"
        lead = f"You have been invited to {where} on {settings.PRODUCT_NAME}."
    _deliver(to, subject, f"{lead}\nOpen this link within {hours} hours to receive your code: {invitation_link(token)}")


def send_reenrolment_notice(to: str, member_name: str, tenant_name: str | None, actor_name: str) -> None:
    where = tenant_name or settings.PRODUCT_NAME
    _deliver(
        to,
        f"Enrolment re-issued for {member_name} at {where}",
        f"{actor_name} re-issued enrolment for {member_name}. Their sessions were revoked and their "
        "passkeys retired. This notice goes to every administrator.",
    )
