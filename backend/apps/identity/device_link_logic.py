"""Adding a device by its code (ID-04, D-135).

A device a person wants to use asks for a link and shows its code. On a device where the
person is already signed in, they type that code and confirm with their passkey. The new
device, which has been waiting, then trades the secret only it holds for a full session in
the zone the confirmation came from, and adds a passkey of its own on My passkeys.

The new device never sees an email or a code from the server: the person's passkey is the
proof, so ID-03 holds (the emailed code still opens nothing once a passkey exists). Nothing
an existing passkey or session holds changes. Codes and secrets are stored as hashes, work
once, and live DEVICE_LINK_TTL_MINUTES."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.utils import timezone

from apps.identity import passkey_names, rate_limit, session_logic, tokens
from apps.identity.models import DeviceLink, LoginEventKind, LoginMethod, SessionKind, User, UserStatus
from apps.identity.security_log import client_ip, log_event, user_agent
from apps.shared import tenancy
from apps.shared.audit import Actor, record

EXPIRED = "This code has expired or was already used. Start again on the new device."


class DeviceLinkExpired(ValidationError):
    """An unknown, expired, used or already approved link (410 device_link_expired)."""


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


def approve(*, user: User, tenant_id: uuid.UUID | None, code: str, step_up_assertion_id: uuid.UUID | None) -> str:
    """The signed-in person vouches for the device showing `code`. Answers what that device
    said it was (its browser), so the person sees which device they let in. `tenant_id` is
    the approving session's zone, which the audit row belongs to."""
    now = timezone.now()
    link = DeviceLink.objects.select_for_update().filter(code_hash=tokens.hash_device_link_code(code)).first()  # ordering: unique hash, at most one row
    if link is None or link.approved_at is not None or link.expires_at <= now:
        raise DeviceLinkExpired(EXPIRED, code="device_link_expired")
    link.user = user
    link.approved_at = now
    link.save(update_fields=["user", "approved_at"])
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
    """Once approved, the waiting device trades its secret for a full session where a passkey
    sign-in would land; the link is then spent. Before approval, 409 device_link_pending."""
    now = timezone.now()
    link = _open_link(secret, now, lock=True)
    if link.approved_at is None:
        raise ValidationError("Nobody has approved this code yet.", code="device_link_pending")
    user = link.user
    assert user is not None  # an approval always names its person
    if user.status != UserStatus.ACTIVE.value:
        raise DeviceLinkExpired(EXPIRED, code="device_link_expired")
    link.claimed_at = now
    link.save(update_fields=["claimed_at"])
    tenant_id = session_logic.choose_tenant(user)
    if tenant_id is not None:
        tenancy.activate(tenant_id)
    log_event(event=LoginEventKind.SIGNIN, method=LoginMethod.PASSKEY, success=True, request=request, user=user, tenant_id=tenant_id, failure_reason="device_link")
    return session_logic.create_session(user=user, kind=SessionKind.FULL, tenant_id=tenant_id, request=request, now=now)
