"""The mails identity sends (ID-01, ID-02, ID-05, D-135). Each is composed here and
delivered by the worker (`apps/identity/tasks.py`) after the request's transaction commits,
so a code request costs the same whether or not a mail follows (F12). English for now. Each
mail is its plain text and the same content in the shared HTML layout
(`apps/shared/mail_layout.py`). The invitation link is the only place a plain invitation
token appears (ID-S1)."""

from __future__ import annotations

from collections.abc import Sequence

from django.conf import settings

from apps.identity import tasks
from apps.shared import mail_layout
from apps.shared.mail_layout import Block, Button, Code, Notice, Small, Steps, Text
from apps.shared.tasks import queue_after_commit


def footer() -> str:
    return f"Sent by {settings.PRODUCT_NAME}. Replies to this address are not read."


def deliver(to: str, subject: str, body: str, blocks: Sequence[Block], tenant_name: str | None = None) -> None:
    """Queue one mail: `body` is the plain text and `blocks` the same content for the HTML
    part, under the subject as its heading."""
    html = mail_layout.render(title=subject, blocks=blocks, footer=footer(), tenant_name=tenant_name or "")
    queue_after_commit(tasks.deliver_mail, (to, subject, body, html))


def invitation_link(token: str) -> str:
    """The token rides in the fragment, which a browser never sends to any server, proxy
    or `Referer` header (F29). The page posts it in the body of `POST /auth/invitations/open`."""
    return f"{settings.APP_BASE_URL.rstrip('/')}/invite#{token}"


def send_code(to: str, code: str) -> None:
    minutes = settings.ENROLMENT_CODE_TTL_MINUTES
    deliver(
        to,
        f"Your {settings.PRODUCT_NAME} enrolment code",
        f"Your code is {code}. It works once and expires in {minutes} minutes.",
        [
            Code(code),
            Text(f"The code works once and expires in {minutes} minutes."),
            Small(f"Nobody at {settings.PRODUCT_NAME} asks you for this code."),
        ],
    )


def send_invitation(to: str, token: str, tenant_name: str | None, *, reenrolment: bool) -> None:
    where = tenant_name or settings.PRODUCT_NAME
    hours = settings.INVITATION_TTL_HOURS
    if reenrolment:
        subject = f"Set up your passkey again for {where}"
        lead = "An administrator re-issued your enrolment. Your earlier passkeys and sessions no longer work."
        action = "Set up your passkey"
    else:
        subject = f"You are invited to {where}"
        lead = f"You have been invited to {where} on {settings.PRODUCT_NAME}."
        action = "Open the invitation"
    link = invitation_link(token)
    deliver(
        to,
        subject,
        f"{lead}\nOpen this link within {hours} hours to receive your code: {link}",
        [
            Text(lead),
            Steps(
                [
                    f"Open the link within {hours} hours.",
                    "Enter the code that we send to this address.",
                    "Create your passkey. From then on you sign in with it.",
                ]
            ),
            Button(action, link),
            Small(f"You never need a password, and nobody at {settings.PRODUCT_NAME} asks you for your code."),
        ],
        tenant_name,
    )


def send_device_let_in(to: str, device: str) -> None:
    """D-135: the person learns at once that a device was let into their account, so a code
    they were tricked into approving does not go unnoticed."""
    what = device or "A new device"
    let_in = f"{what} was let into your account with your passkey."
    if_not_you = "If this was not you, open My sessions, sign out everywhere, and tell your administrator at once."
    deliver(
        to,
        f"A device was let into your {settings.PRODUCT_NAME} account",
        f"{let_in} {if_not_you}",
        [Text(let_in), Notice(if_not_you)],
    )


def send_reenrolment_notice(to: str, member_name: str, tenant_name: str | None, actor_name: str) -> None:
    where = tenant_name or settings.PRODUCT_NAME
    body = (
        f"{actor_name} re-issued enrolment for {member_name}. Their sessions were revoked and their "
        "passkeys retired. This notice goes to every administrator."
    )
    deliver(to, f"Enrolment re-issued for {member_name} at {where}", body, [Text(body)], tenant_name)
