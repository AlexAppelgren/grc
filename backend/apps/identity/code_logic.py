"""The emailed one-time code (ID-02, ID-03, AC-ID1): six digits, single use, ten minutes,
stored as a keyed, salted hash (`tokens.hash_code`, F30), five attempts, rate limited per address and per IP, compared in
constant time. All numbers are settings.

The code is an enrolment bootstrap, never a fallback: `request_code` answers every
address the same way and does the same hashing work on every path, and it sends a
code only to an address with an open invitation or re-enrolment and no live passkey.
An enrolled address gets `code_refused_enrolled` in the security log and nothing else."""

from __future__ import annotations

import uuid
from datetime import timedelta

from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import F
from django.http import HttpRequest
from django.utils import timezone

from apps.identity import invitation_logic, mail, rate_limit, session_logic, tokens
from apps.identity.models import Invitation, LoginEventKind, LoginMethod, OtpCode, SessionKind, User
from apps.identity.security_log import client_ip, log_event
from apps.shared import tenancy
from apps.shared.audit import Actor, record

HOUR = 3600
MINUTE = 60


def enforce_code_limits(email: str, request: HttpRequest | None) -> None:
    """Per address and per IP (playbook 4.2), on both doors to a code: the invitation
    link and the code request."""
    rate_limit.enforce("code-request:address", email, settings.ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR, HOUR, e2e_exempt=True)
    rate_limit.enforce("code-request:ip", client_ip(request) or "", settings.ENROLMENT_CODE_RATE_PER_IP_PER_HOUR, HOUR, e2e_exempt=True)


def _limit_verify(request: HttpRequest | None) -> None:
    rate_limit.enforce("auth:ip", client_ip(request) or "", settings.AUTH_RATE_PER_IP_PER_MINUTE, MINUTE, e2e_exempt=True)


def issue_code(*, user: User, tenant_id: uuid.UUID | None, request: HttpRequest | None) -> OtpCode:
    """Mint, hash, store and email one code. The caller has activated `tenant_id`."""
    now = timezone.now()
    code = tokens.new_code()
    salt = tokens.new_salt()
    OtpCode.objects.filter(email=user.email, consumed_at__isnull=True).update(consumed_at=now)
    row = OtpCode.objects.create(
        user=user,
        email=user.email,
        code_hash=tokens.hash_code(code, salt),
        salt=salt,
        max_attempts=settings.ENROLMENT_CODE_MAX_ATTEMPTS,
        expires_at=now + timedelta(minutes=settings.ENROLMENT_CODE_TTL_MINUTES),
        ip=client_ip(request),
    )
    mail.send_code(user.email, code)
    log_event(event=LoginEventKind.CODE_SENT, method=LoginMethod.EMAIL_CODE, success=True, request=request, user=user, tenant_id=tenant_id)
    return row


def request_code(email: str, request: HttpRequest | None) -> None:
    """Neutral by construction: the same work, the same answer, whatever the address."""
    cleaned = email.strip().lower()
    enforce_code_limits(cleaned, request)
    user = User.objects.filter(email=cleaned).first()  # ordering: email is unique, at most one row
    invitation = invitation_logic.find_open_for_email(cleaned)
    enrolled = user is not None and invitation_logic.has_live_passkey(user)
    # The same hashing work on every path (playbook 4.2: constant time), whether or not
    # a code is about to be sent.
    decoy_salt = tokens.new_salt()
    tokens.hash_code(tokens.new_code(), decoy_salt)
    if user is not None and invitation is not None and not enrolled:
        if invitation.tenant_id is not None:
            tenancy.activate(invitation.tenant_id)
        issue_code(user=user, tenant_id=invitation.tenant_id, request=request)
        subject_id, title, summary = user.id, user.name, "A code was sent."
    elif enrolled and user is not None:
        log_event(
            event=LoginEventKind.CODE_REFUSED_ENROLLED,
            method=LoginMethod.EMAIL_CODE,
            success=False,
            request=request,
            user=user,
            tenant_id=None,
            failure_reason="passkey_enrolled",
        )
        subject_id, title, summary = user.id, user.name, "No code: the account holds a passkey."
    else:
        subject_id, title, summary = None, "unknown address", "No code: no open invitation."
    record(
        action="auth.code_requested",
        actor=Actor.system("code-request"),
        subject_type="user",
        subject_id=subject_id,
        subject_title=title,
        summary=summary,
        tenant_id=None,
    )


def _open_code(email: str, now: datetime) -> OtpCode | None:
    return (
        OtpCode.objects.select_related("user")
        .filter(email=email, consumed_at__isnull=True, expires_at__gt=now)
        .order_by("-created_at", "-id")
        .first()
    )


def _claim_attempt(row: OtpCode) -> bool:
    """Spend one attempt with a single conditional UPDATE, so concurrent guesses at the
    same code serialise on the row and can never exceed `max_attempts` together (an
    in-memory `attempts += 1` let N parallel requests each see attempt 0; security review
    2026-09-19, finding F2)."""
    claimed = OtpCode.objects.filter(pk=row.pk, consumed_at__isnull=True, attempts__lt=F("max_attempts")).update(
        attempts=F("attempts") + 1
    )
    return claimed == 1


def verify_code(email: str, code: str, request: HttpRequest | None) -> session_logic.SessionBundle:
    """The sign-in page's "First time here?" path: the address names the code, and its
    newest open invitation the tenant."""
    _limit_verify(request)
    cleaned = email.strip().lower()
    return _verify(cleaned, code, invitation_logic.find_open_for_email(cleaned), request)


def verify_invitation_code(token: str, code: str, request: HttpRequest | None) -> session_logic.SessionBundle:
    """The invitation path: the link's token names the invitation, and only a code issued
    for that invitation's address can verify. No address travels. Rate limited per IP
    before the lookup, like opening the link (finding F5); a closed or unknown invitation
    is 410 `invitation_expired`."""
    _limit_verify(request)
    invitation = invitation_logic.find_by_token(token)
    if invitation is None or not invitation_logic.is_open(invitation):
        raise invitation_logic.InvitationExpired("This invitation link has expired or was already used.", code="invitation_expired")
    return _verify(invitation.email, code, invitation, request)


def _verify(cleaned: str, code: str, invitation: Invitation | None, request: HttpRequest | None) -> session_logic.SessionBundle:
    """A right code within its window yields an enrolment session in `invitation`'s
    tenant; a wrong one counts an attempt and answers `invalid_code`; the sixth answers
    `code_locked` even when right. The caller has spent the per-IP limit."""
    now = timezone.now()
    row = _open_code(cleaned, now)
    # A decoy keeps the comparison work identical when no code exists for the address.
    salt = row.salt if row else tokens.new_salt()
    stored_hash = row.code_hash if row else tokens.hash_code("000000", salt)
    matches = tokens.constant_equal(tokens.hash_code(code.strip(), salt), stored_hash)
    # Failures belong in the tenant's security log (ID-11): the invitation names the
    # tenant, and the log row is written after that tenant is activated.
    tenant_id = invitation.tenant_id if invitation is not None else None
    if tenant_id is not None:
        tenancy.activate(tenant_id)
    if row is None:
        log_event(event=LoginEventKind.CODE_FAILED, method=LoginMethod.EMAIL_CODE, success=False, request=request, tenant_id=tenant_id, email=cleaned, failure_reason="no_open_code")
        raise ValidationError("That code is not right.", code="invalid_code")
    if row.attempts >= row.max_attempts or not _claim_attempt(row):
        log_event(event=LoginEventKind.CODE_LOCKED, method=LoginMethod.EMAIL_CODE, success=False, request=request, user=row.user, tenant_id=tenant_id, email=cleaned, failure_reason="too_many_attempts")
        raise ValidationError("Too many attempts. Ask for a new code.", code="code_locked")
    row.refresh_from_db(fields=["attempts"])
    if not matches:
        locked = row.attempts >= row.max_attempts
        log_event(
            event=LoginEventKind.CODE_LOCKED if locked else LoginEventKind.CODE_FAILED,
            method=LoginMethod.EMAIL_CODE,
            success=False,
            request=request,
            user=row.user,
            tenant_id=tenant_id,
            email=cleaned,
            failure_reason="wrong_code",
        )
        raise ValidationError("That code is not right.", code="invalid_code")
    # Single use, claimed with a conditional UPDATE so two right answers in flight yield
    # one enrolment session, not two (finding F2).
    if OtpCode.objects.filter(pk=row.pk, consumed_at__isnull=True).update(consumed_at=now) != 1:
        log_event(event=LoginEventKind.CODE_FAILED, method=LoginMethod.EMAIL_CODE, success=False, request=request, user=row.user, tenant_id=tenant_id, email=cleaned, failure_reason="already_consumed")
        raise ValidationError("That code is not right.", code="invalid_code")
    row.consumed_at = now
    user = row.user or invitation_logic.get_or_create_user(cleaned)
    if invitation is None or invitation_logic.has_live_passkey(user):
        # The code was right but the door is closed: no invitation, or a passkey exists.
        log_event(event=LoginEventKind.CODE_FAILED, method=LoginMethod.EMAIL_CODE, success=False, request=request, user=user, tenant_id=tenant_id, failure_reason="no_open_invitation")
        raise ValidationError("That code is not right.", code="invalid_code")
    return session_logic.create_session(user=user, kind=SessionKind.ENROLMENT, tenant_id=invitation.tenant_id, request=request, now=now)
