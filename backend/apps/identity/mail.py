"""The three emails identity sends (ID-01, ID-02, ID-05). Each is composed here and
delivered by the worker (`apps/identity/tasks.py`) after the request's transaction commits,
so a code request costs the same whether or not a mail follows (F12). Plain text, English
for now. The invitation link is the only place a plain invitation token appears (ID-S1)."""

from __future__ import annotations

from django.conf import settings

from apps.identity import tasks
from apps.shared.tasks import queue_after_commit


def _deliver(to: str, subject: str, body: str) -> None:
    queue_after_commit(tasks.deliver_mail, (to, subject, body))


def invitation_link(token: str) -> str:
    """The token rides in the fragment, which a browser never sends to any server, proxy
    or `Referer` header (F29). The page posts it in the body of `POST /auth/invitations/open`."""
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
