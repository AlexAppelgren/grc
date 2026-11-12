"""Adding a device by its code (ID-04, D-135).

A device a person wants to use asks for a link and shows its code. On a device where the
person is already signed in, they type that code and confirm with a passkey made for that
code alone. The new device, which has been waiting, then trades the secret only it holds for
a session that can do nothing but register a passkey on it, like an enrolment session; that
registration opens the full session (`passkey_logic.verify_registration`).

So the new device never holds a full session without a passkey of its own, and the person
is emailed the moment a device is let in. The emailed code still opens nothing once a
passkey exists (ID-03). Nothing an existing passkey or session holds changes. Codes and
secrets are stored as keyed hashes, work once, and live DEVICE_LINK_TTL_MINUTES."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.identity import mail, passkey_names, rate_limit, session_logic, tokens
from apps.identity.models import DeviceLink, LoginEventKind, LoginMethod, SessionKind, User, UserStatus
from apps.identity.security_log import client_ip, log_event, user_agent
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError

EXPIRED = "This code has expired or was already used. Start again on the new device."


class DeviceLinkExpired(ValidationError):
    """An unknown, expired, used or cancelled link (410 device_link_expired)."""


@dataclass(frozen=True)
class StartedLink:
    link: DeviceLink
    secret: str
    code: str


def start(request: HttpRequest | None) -> StartedLink:
    """A fresh link for the device asking; nothing is tied to any account yet. The audit
    row is the platform's, since no person or bank is named until an approval."""
    rate_limit.enforce("auth:ip", client_ip(request) or "", settings.AUTH_RATE_PER_IP_PER_MINUTE, 60, e2e_exempt=True)
    secret = tokens.new_token()
    code = tokens.new_device_link_code()
    link = DeviceLink.objects.create(
        secret_hash=tokens.hash_token(secret),
        code_hash=tokens.hash_device_link_code(code),
        expires_at=timezone.now() + timedelta(minutes=settings.DEVICE_LINK_TTL_MINUTES),
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    record(
        action="device_link.started",
        actor=Actor.system("new_device"),
        subject_type="device_link",
        subject_id=link.id,
        subject_title=passkey_names.describe_browser(link.user_agent) or "",
        summary="A device asked to be let in.",
        tenant_id=None,
        after={"expiresAt": link.expires_at.isoformat()},
    )
    return StartedLink(link=link, secret=secret, code=code)


def _step_up_again() -> ProblemError:
    return ProblemError(status=403, code="step_up_required", detail="Confirm this device with your passkey.")


def approve(
    *,
    user: User,
    tenant_id: uuid.UUID | None,
    session_id: uuid.UUID,
    code: str,
    step_up_at: datetime,
    step_up_assertion_id: uuid.UUID,
) -> str:
    """The signed-in person vouches for the device showing `code`, with a passkey assertion
    made after that code existed and spent on no other device, so no earlier confirmation
    lets a code through unseen. Answers what that device said it was (its browser).
    `tenant_id` is the approving session's zone, which the audit row belongs to."""
    now = timezone.now()
    link = (
        DeviceLink.objects.select_for_update()
        .filter(code_hash=tokens.hash_device_link_code(code), approved_at__isnull=True, expires_at__gt=now)
        .order_by("-created_at")
        .first()
    )
    if link is None:
        raise DeviceLinkExpired(EXPIRED, code="device_link_expired")
    if step_up_at <= link.created_at:
        raise _step_up_again()
    link.user = user
    link.approved_session_id = session_id
    link.step_up_assertion_id = step_up_assertion_id
    link.approved_at = now
    # The device gets its whole window from the approval, so a late approval still lets it in.
    link.expires_at = now + timedelta(minutes=settings.DEVICE_LINK_TTL_MINUTES)
    try:
        with transaction.atomic():
            link.save(update_fields=["user", "approved_session_id", "step_up_assertion_id", "approved_at", "expires_at"])
    except IntegrityError:
        raise _step_up_again() from None
    device = passkey_names.describe_browser(link.user_agent) or ""
    record(
        action="device_link.approved",
        actor=session_logic.actor_of(user),
        subject_type="device_link",
        subject_id=link.id,
        subject_title=user.name,
        summary="A new device was let in with a passkey.",
        tenant_id=tenant_id,
        after={"device": device},
        step_up_assertion_id=step_up_assertion_id,
    )
    mail.send_device_let_in(user.email, device)
    return device


def _open_link(secret: str, now: datetime, *, lock: bool) -> DeviceLink:
    rows = DeviceLink.objects.select_related("user").filter(secret_hash=tokens.hash_token(secret))
    if lock:
        rows = rows.select_for_update(of=("self",))
    link = rows.first()  # ordering: unique hash, at most one row
    if link is None or link.claimed_at is not None or link.expires_at <= now:
        raise DeviceLinkExpired(EXPIRED, code="device_link_expired")
    return link


def is_approved(secret: str) -> bool:
    """The waiting device's poll: a read, so it writes nothing and spends no rate limit (the
    secret is 256 random bits and cannot be guessed). 410 once the link is gone."""
    return _open_link(secret, timezone.now(), lock=False).approved_at is not None


def claim(secret: str, request: HttpRequest | None) -> session_logic.SessionBundle:
    """Once approved, the waiting device trades its secret for a session that may only
    register a passkey, in the bank a passkey sign-in would land in; the link is then spent.
    Before approval, 409 device_link_pending."""
    now = timezone.now()
    link = _open_link(secret, now, lock=True)
    if link.approved_at is None:
        raise ValidationError("Nobody has approved this code yet.", code="device_link_pending")
    user = link.user
    assert user is not None  # an approval always names its person
    assert link.approved_session_id is not None  # set with the approval
    # Signing out the approving session, or every session, cancels a link not yet claimed.
    if user.status != UserStatus.ACTIVE.value or not session_logic.session_is_live(link.approved_session_id):
        raise DeviceLinkExpired(EXPIRED, code="device_link_expired")
    tenant_id = session_logic.choose_tenant(user)
    if tenant_id is not None:
        tenancy.activate(tenant_id)
    log_event(event=LoginEventKind.SIGNIN, method=LoginMethod.DEVICE_LINK, success=True, request=request, user=user, tenant_id=tenant_id)
    bundle = session_logic.create_session(user=user, kind=SessionKind.ENROLMENT, tenant_id=tenant_id, request=request, now=now)
    link.claimed_at = now
    link.session_id = bundle.session.id
    link.save(update_fields=["claimed_at", "session_id"])
    return bundle


def for_session(session_id: uuid.UUID) -> DeviceLink | None:
    """The link a registration-only session came from, if it came from one."""
    return DeviceLink.objects.filter(session_id=session_id, claimed_at__isnull=False).first()  # ordering: unique session id, at most one row
