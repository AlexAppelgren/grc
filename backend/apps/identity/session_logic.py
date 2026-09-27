"""Sessions (D-06, ADR 0006): a short-lived HMAC access token, a rotating refresh token in
an HttpOnly cookie scoped to the auth path, a `user_session` row behind every refresh so
a person or an admin revokes at once. Idle and absolute limits are enforced on refresh;
they are the bank's security policy (ID-08), the platform defaults where it sets none, and
never above the SESSION_*_MAX settings. A replay inside the grace window answers like the
original, a replay after it revokes the whole session (ID-S9).

`resolve_access_token` is what the three auth classes call. It reads the session row
in identity-lookup mode (the tenant is not known yet), then activates the session's
tenant so every later query in the request is scoped (playbook 14).

A support session (TEN-06, ADR 0042) is minted here and nowhere else: a platform person
enters one bank under a grant it approved, and the session activates that bank exactly as a
member's does, then re-reads the grant under the bank's own policies on every request. The
one window onto a grant before any bank is active, `app.platform_user_id`, is also set here
and nowhere else (`own_grants`); `apps/shared/tests_support_session.py` pins both."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.identity import tokens
from apps.identity.models import (
    LoginEventKind,
    LoginMethod,
    Membership,
    PlatformRoleAssignment,
    SessionKind,
    StepUpAssertion,
    User,
    UserSession,
    UserStatus,
)
from apps.identity.security_log import client_ip, log_event, user_agent
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.audit import Actor, ActorType, record
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.errors import ProblemError
from apps.tenants.models import SecurityPolicy, SupportAccess

# What a support session holds (D-49, ADR 0042): the seven reads and nothing else. No search
# or Ask, which would spend the bank's AI budget, no role rows and no platform grant. Which
# routes it reaches is `SUPPORT_READ_ROUTES` (apps/shared/routes.py), not this set alone.
SUPPORT_PERMISSIONS: frozenset[str] = frozenset(
    {
        perms.LIBRARY_READ,
        perms.WATCH_READ,
        perms.ROADMAP_READ,
        perms.REGISTER_READ,
        perms.CASES_READ,
        perms.REPORTS_READ,
        perms.AUDIT_READ,
    }
)
PLATFORM_USER_SETTING = "app.platform_user_id"


@dataclass(frozen=True)
class SessionBundle:
    session: UserSession
    access_token: str
    expires_in: int
    refresh_value: str


def actor_of(user: User) -> Actor:
    return Actor(kind=ActorType.USER, id=user.id, label=user.name)


# ---------------------------------------------------------------------------------------
# Limits (ID-08)
# ---------------------------------------------------------------------------------------
def limits(tenant_id: uuid.UUID | None) -> tuple[timedelta, timedelta]:
    """The idle and absolute limits of a session in `tenant_id`: its bank's policy, the
    platform default where the bank sets none (or for a platform session), and never above
    the platform maximum, even for a row written around the policy route's check. Activates
    the tenant, as every session in it runs there."""
    idle, absolute = settings.SESSION_IDLE_MINUTES_DEFAULT, settings.SESSION_ABSOLUTE_HOURS_DEFAULT
    if tenant_id is not None:
        tenancy.activate(tenant_id)
        policy = SecurityPolicy.objects.filter(tenant_id=tenant_id).first()  # ordering: tenant is unique, at most one row
        if policy is not None:
            idle = policy.session_idle_minutes or idle
            absolute = policy.session_absolute_hours or absolute
    return (
        timedelta(minutes=min(idle, settings.SESSION_IDLE_MINUTES_MAX)),
        timedelta(hours=min(absolute, settings.SESSION_ABSOLUTE_HOURS_MAX)),
    )


# ---------------------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------------------
def set_refresh_cookie(response: HttpResponse, value: str) -> None:
    """The cookie lives as long as its session may: until the session's absolute end."""
    session, _ = _load_by_refresh(value)
    remaining = session.expires_at - timezone.now() if session is not None else timedelta(0)
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        value,
        max_age=max(0, int(remaining.total_seconds())),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="Strict",
        path=settings.REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: HttpResponse) -> None:
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH, samesite="Strict")


# ---------------------------------------------------------------------------------------
# Creating sessions
# ---------------------------------------------------------------------------------------
def choose_tenant(user: User) -> uuid.UUID | None:
    """The tenant a full session binds to: the person's oldest active membership (R1 has no
    tenant switcher); platform staff without one get a platform session."""
    with tenancy.identity_lookup():
        membership = (
            Membership.objects.filter(user=user, deactivated_at__isnull=True)
            .order_by("created_at", "id")
            .values_list("tenant_id", flat=True)
            .first()
        )
    return membership


def create_session(
    *, user: User, kind: SessionKind, tenant_id: uuid.UUID | None, request: HttpRequest | None, now: datetime | None = None
) -> SessionBundle:
    now = now or timezone.now()
    _, absolute = limits(tenant_id)
    session = UserSession(
        user=user,
        tenant_id=tenant_id,
        kind=kind.value,
        last_seen_at=now,
        expires_at=now + absolute,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    refresh_value, refresh_hash = tokens.new_refresh_token(session.id)
    session.refresh_token_hash = refresh_hash
    session.save()
    access_token, expires_in = tokens.issue_access_token(session.id, kind.value, now)
    record(
        action="session.created",
        actor=actor_of(user),
        subject_type="user_session",
        subject_id=session.id,
        subject_title=user.name,
        summary=f"{kind.value.capitalize()} session started.",
        tenant_id=tenant_id,
        after={"kind": kind.value, "expiresAt": session.expires_at.isoformat()},
    )
    return SessionBundle(session=session, access_token=access_token, expires_in=expires_in, refresh_value=refresh_value)


# ---------------------------------------------------------------------------------------
# Resolving an access token into a principal
# ---------------------------------------------------------------------------------------
def _live(session: UserSession, now: datetime) -> bool:
    return session.revoked_at is None and session.expires_at > now


def latest_step_up(session_id: uuid.UUID) -> StepUpAssertion | None:
    return StepUpAssertion.objects.filter(session_id=session_id).order_by("-created_at", "-id").first()


def build_principal(session: UserSession) -> Principal | None:
    """Flatten the person's grants in the session's tenant (plus platform grants) into a
    Principal. Called after the tenant is activated so the role rows are readable.

    None when a full session in a tenant stands on no active membership there
    (deactivated, or never created): the token then resolves to nothing, so no route that
    takes "any member" as its grant answers a non-member (security review 2026-09-19,
    finding F7). An enrolment session has no membership yet by definition.

    A session holds the permissions of its own zone and no others (hardening H2, H13). A
    tenant session reads the membership's role rows and keeps what `TENANT_PERMISSIONS`
    names, so a row written around the seeds and the role editor cannot smuggle
    `proposals.review` past the library fence; a platform session reads the platform
    assignments and keeps what `PLATFORM_PERMISSIONS` names. Platform staff are separate
    accounts (bootstrap_platform and every bank invitation refuse an address the other
    zone knows), so a platform grant is never read in a bank session at all."""
    user = session.user
    if session.kind == SessionKind.ENROLMENT.value:
        return Principal(kind=PrincipalKind.ENROLMENT, subject_id=user.id, tenant_id=session.tenant_id, session_id=session.id)
    if session.kind == SessionKind.SUPPORT.value:
        # The seven reads in the granted bank, never a role row of it and never a platform
        # grant; a support session never steps up, so no step-up route answers it either.
        return Principal(
            kind=PrincipalKind.USER,
            subject_id=user.id,
            tenant_id=session.tenant_id,
            permissions=SUPPORT_PERMISSIONS,
            session_id=session.id,
            session_created_at=session.created_at,
            support_access_id=session.support_access_id,
        )
    granted: set[str] = set()
    is_platform_staff = False
    if session.tenant_id is not None:
        # One row per role of the active membership; one row with NULL for an active
        # membership with no role; no row at all when there is no active membership.
        role_rows = list(
            Membership.objects.filter(tenant_id=session.tenant_id, user=user, deactivated_at__isnull=True)
            .values_list("roles__permissions", flat=True)
        )
        if not role_rows:
            return None
        for permissions in role_rows:
            granted.update(permissions or [])
        granted &= perms.TENANT_PERMISSIONS
    else:
        platform_rows = PlatformRoleAssignment.objects.filter(user=user, role__active=True).values_list(
            "role__permissions", flat=True
        )
        for permissions in platform_rows:
            is_platform_staff = True
            granted.update(permissions or [])
        granted &= perms.PLATFORM_PERMISSIONS
    assertion = latest_step_up(session.id)
    return Principal(
        kind=PrincipalKind.USER,
        subject_id=user.id,
        tenant_id=session.tenant_id,
        permissions=frozenset(granted),
        is_platform_staff=is_platform_staff,
        step_up_at=assertion.created_at if assertion else None,
        step_up_assertion_id=assertion.id if assertion else None,
        session_id=session.id,
        session_created_at=session.created_at,
    )


def enrolment_token_presented(request: HttpRequest) -> bool:
    """True when the request carries a live enrolment access token: a SessionAuth route
    then answers 403 `enrolment_only` instead of 401 (AC-ID2). Signature and expiry only,
    no row read: the answer is the same whether the session row still exists."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    claims = tokens.parse_access_token(token.strip(), timezone.now())
    return claims is not None and claims.kind == SessionKind.ENROLMENT.value


def resolve_access_token(token: str, *, want: PrincipalKind) -> Principal | None:
    now = timezone.now()
    claims = tokens.parse_access_token(token, now)
    if claims is None:
        return None
    wanted_kinds = (
        {SessionKind.ENROLMENT.value} if want is PrincipalKind.ENROLMENT else {SessionKind.FULL.value, SessionKind.SUPPORT.value}
    )
    if claims.kind not in wanted_kinds:
        return None
    with tenancy.identity_lookup():
        session = UserSession.objects.select_related("user").filter(pk=claims.session_id).first()  # ordering: pk lookup, at most one row
    if session is None or session.kind != claims.kind or session.revoked_at is not None:
        return None
    support = session.kind == SessionKind.SUPPORT.value
    if (not support and not _live(session, now)) or session.user.status == UserStatus.DEACTIVATED.value:
        return None
    if session.tenant_id is not None:
        tenancy.activate(session.tenant_id)
    # A support session ends with its grant: past the window, or revoked by the bank, every
    # request answers 401 `support_access_ended` and nothing else runs (ADR 0042).
    if support and (session.expires_at <= now or not _grant_live(session)):
        raise ProblemError(status=401, code="support_access_ended", detail="The bank's support access has ended.")
    return build_principal(session)


# ---------------------------------------------------------------------------------------
# Support sessions (TEN-06, D-49, ADR 0042)
# ---------------------------------------------------------------------------------------
def _grant_live(session: UserSession) -> bool:
    """Whether the grant a support session stands on is still open, read after the session's
    bank is active and under its own policies, so the read proves the grant is that bank's."""
    from apps.tenants import support_access

    assert session.tenant_id is not None and session.support_access_id is not None  # the CHECK on user_session
    return support_access.live_grant(tenant_id=session.tenant_id, grant_id=session.support_access_id) is not None


def support_token_presented(request: HttpRequest) -> bool:
    """True when the request carries a support session's access token, by its signed kind
    alone: the read-only guard refuses a route off the allow-list before any row is read."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    claims = tokens.parse_access_token(token.strip(), timezone.now())
    return claims is not None and claims.kind == SessionKind.SUPPORT.value


@contextmanager
def own_grants(principal: Principal) -> Iterator[None]:
    """For the block, let a platform session read the `support_access` rows that name it and
    no other (the `support_access_own_grants` policy, tenants 0004): `SET LOCAL` of the
    caller's own user id, cleared when the block ends, even on an error. A bank's session,
    or a support session, never opens it."""
    if principal.kind is not PrincipalKind.USER or principal.tenant_id is not None or not principal.is_platform_staff:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [PLATFORM_USER_SETTING, str(principal.subject_id)])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, %s, true)", [PLATFORM_USER_SETTING, ""])


def create_support_session(
    *, user: User, grant: SupportAccess, replacing: uuid.UUID, request: HttpRequest | None
) -> SessionBundle:
    """Replace the platform person's console session with a support session in the grant's
    bank, expiring with the grant's window. The console session is revoked first, in the
    zone it lives in, then the bank is activated and the new session written there."""
    now = timezone.now()
    console = UserSession.objects.select_related("user").get(pk=replacing, user=user, tenant__isnull=True)
    revoke_session(console, reason="support_entered", actor=actor_of(user), request=request)
    tenancy.activate(grant.tenant_id)
    assert grant.expires_at is not None  # an active grant has a window (support_access.state_of)
    session = UserSession(
        user=user,
        tenant_id=grant.tenant_id,
        kind=SessionKind.SUPPORT.value,
        support_access=grant,
        last_seen_at=now,
        expires_at=grant.expires_at,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    refresh_value, refresh_hash = tokens.new_refresh_token(session.id)
    session.refresh_token_hash = refresh_hash
    session.save()
    access_token, expires_in = tokens.issue_access_token(session.id, session.kind, now)
    record(
        action="session.created",
        actor=actor_of(user),
        subject_type="user_session",
        subject_id=session.id,
        subject_title=user.name,
        summary="Support session started.",
        tenant_id=grant.tenant_id,
        after={"kind": session.kind, "expiresAt": session.expires_at.isoformat(), "grantId": str(grant.id)},
    )
    return SessionBundle(session=session, access_token=access_token, expires_in=expires_in, refresh_value=refresh_value)


# ---------------------------------------------------------------------------------------
# Refresh, sign-out, revocation
# ---------------------------------------------------------------------------------------
def _load_by_refresh(value: str | None) -> tuple[UserSession | None, str | None]:
    parsed = tokens.parse_refresh_token(value or "")
    if parsed is None:
        return None, None
    session_id, presented_hash = parsed
    with tenancy.identity_lookup():
        session = UserSession.objects.select_related("user").filter(pk=session_id).first()  # ordering: pk lookup, at most one row
    return session, presented_hash


def refresh(value: str | None, request: HttpRequest | None) -> tuple[str, int, str | None]:
    """Rotate the refresh token. Returns (access token, expires in, new refresh value or
    None when a replay inside the grace window is answered without a third token)."""
    now = timezone.now()
    session, presented_hash = _load_by_refresh(value)
    if session is None or presented_hash is None or not _live(session, now):
        raise ValidationError("Sign in again.", code="unauthenticated")
    idle_limit, absolute_limit = limits(session.tenant_id)
    current = tokens.constant_equal(presented_hash, session.refresh_token_hash)
    previous = session.previous_refresh_hash is not None and tokens.constant_equal(
        presented_hash, session.previous_refresh_hash
    )
    if previous and session.rotated_at is not None:
        within_grace = now - session.rotated_at <= timedelta(seconds=settings.REFRESH_REPLAY_GRACE_SECONDS)
        if within_grace:
            access_token, expires_in = tokens.issue_access_token(session.id, session.kind, now)
            record(
                action="session.refreshed",
                actor=actor_of(session.user),
                subject_type="user_session",
                subject_id=session.id,
                subject_title=session.user.name,
                summary="Refresh replayed inside the grace window (concurrent tab).",
                tenant_id=session.tenant_id,
            )
            return access_token, expires_in, None
        revoke_session(session, reason="refresh_replay", actor=actor_of(session.user), request=request)
        log_event(
            event=LoginEventKind.REFRESH_REPLAY,
            method=LoginMethod.PASSKEY,
            success=False,
            request=request,
            user=session.user,
            tenant_id=session.tenant_id,
            failure_reason="refresh_replay",
        )
        raise ValidationError("Sign in again.", code="unauthenticated")
    if not current:
        raise ValidationError("Sign in again.", code="unauthenticated")
    # A limit the bank lowered since sign-in applies now; a raised one never extends.
    deadline = min(session.expires_at, session.created_at + absolute_limit)
    if now >= deadline:
        revoke_session(session, reason="absolute", actor=actor_of(session.user), request=request)
        raise ValidationError("Sign in again.", code="unauthenticated")
    if now - session.last_seen_at > idle_limit:
        revoke_session(session, reason="idle", actor=actor_of(session.user), request=request)
        raise ValidationError("Sign in again.", code="unauthenticated")
    if session.kind == SessionKind.SUPPORT.value and not _grant_live(session):
        revoke_session(session, reason="support_access_ended", actor=actor_of(session.user), request=request)
        raise ProblemError(status=401, code="support_access_ended", detail="The bank's support access has ended.")
    session.expires_at = deadline
    new_value, new_hash = tokens.new_refresh_token(session.id)
    session.previous_refresh_hash = session.refresh_token_hash
    session.refresh_token_hash = new_hash
    session.rotated_at = now
    session.last_seen_at = now
    session.save(update_fields=["previous_refresh_hash", "refresh_token_hash", "rotated_at", "last_seen_at", "expires_at"])
    access_token, expires_in = tokens.issue_access_token(session.id, session.kind, now)
    record(
        action="session.refreshed",
        actor=actor_of(session.user),
        subject_type="user_session",
        subject_id=session.id,
        subject_title=session.user.name,
        summary="Refresh token rotated.",
        tenant_id=session.tenant_id,
    )
    return access_token, expires_in, new_value


def _holds_secret(session: UserSession, presented_hash: str, now: datetime) -> bool:
    """The cookie carries the session's current refresh secret, or the one it just rotated
    away from inside the replay grace window (a tab signing out while another refreshes)."""
    if tokens.constant_equal(presented_hash, session.refresh_token_hash):
        return True
    return (
        session.previous_refresh_hash is not None
        and session.rotated_at is not None
        and now - session.rotated_at <= timedelta(seconds=settings.REFRESH_REPLAY_GRACE_SECONDS)
        and tokens.constant_equal(presented_hash, session.previous_refresh_hash)
    )


def sign_out(value: str | None, request: HttpRequest | None) -> None:
    """Idempotent: a stale or missing cookie still answers 204, and the attempt is still a
    write for the audit rule (AC-AUD1), recorded with no subject.

    The cookie is the only credential here, and a session id is no secret (every
    `session.created` audit row names one), so a cookie naming a session without holding
    its refresh secret signs nobody out and writes nothing in that person's name."""
    session, presented_hash = _load_by_refresh(value)
    if (
        session is None
        or presented_hash is None
        or session.revoked_at is not None
        or not _holds_secret(session, presented_hash, timezone.now())
    ):
        record(
            action="session.sign_out_without_session",
            actor=Actor.system("sign-out"),
            subject_type="user_session",
            subject_id=None,
            subject_title="",
            summary="Sign-out with no live session.",
            tenant_id=None,
        )
        return
    if session.tenant_id is not None:
        tenancy.activate(session.tenant_id)
    revoke_session(session, reason="sign_out", actor=actor_of(session.user), request=request)


def revoke_session(session: UserSession, *, reason: str, actor: Actor, request: HttpRequest | None = None) -> None:
    if session.revoked_at is not None:
        return
    session.revoked_at = timezone.now()
    session.revoked_reason = reason
    session.save(update_fields=["revoked_at", "revoked_reason"])
    log_event(
        event=LoginEventKind.SESSION_REVOKED,
        method=LoginMethod.PASSKEY if session.kind == SessionKind.FULL.value else LoginMethod.EMAIL_CODE,
        success=True,
        request=request,
        user=session.user,
        tenant_id=session.tenant_id,
        failure_reason=reason,
    )
    record(
        action="session.revoked",
        actor=actor,
        subject_type="user_session",
        subject_id=session.id,
        subject_title=session.user.name,
        summary=f"Session revoked ({reason}).",
        tenant_id=session.tenant_id,
        after={"reason": reason},
    )


def revoke_all(user: User, *, tenant_id: uuid.UUID | None, reason: str, actor: Actor, request: HttpRequest | None = None) -> int:
    """Revoke every live session of `user`; in one tenant when `tenant_id` is given
    (an admin acts inside their tenant), everywhere when None (the person themself)."""
    queryset = UserSession.objects.filter(user=user, revoked_at__isnull=True).select_related("user")
    if tenant_id is not None:
        queryset = queryset.filter(tenant_id=tenant_id)
    count = 0
    for session in queryset:
        revoke_session(session, reason=reason, actor=actor, request=request)
        count += 1
    return count


def live_sessions(user: User, *, tenant_id: uuid.UUID | None) -> list[UserSession]:
    now = timezone.now()
    queryset = UserSession.objects.filter(
        user=user, revoked_at__isnull=True, expires_at__gt=now, kind=SessionKind.FULL.value
    )
    if tenant_id is not None:
        queryset = queryset.filter(tenant_id=tenant_id)
    return list(queryset.order_by("-last_seen_at", "-id"))


def revoke_own_session(principal: Principal, session_id: uuid.UUID, request: HttpRequest | None) -> None:
    """A person revokes one of their own sessions (ID-04); another user's is a 404."""
    session = UserSession.objects.select_related("user").filter(pk=session_id, user_id=principal.subject_id).first()  # ordering: pk lookup, at most one row
    if session is None:
        raise ValidationError("Not found.", code="not_found")
    revoke_session(session, reason="revoked_by_user", actor=actor_of(session.user), request=request)
