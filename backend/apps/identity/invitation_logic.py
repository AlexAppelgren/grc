"""Invitations (ID-01) and re-enrolment (ID-05). An invitation is a single-use, hashed,
72-hour token that opens the emailed-code path; the plain token exists only in the
emailed link. Re-enrolment is the only recovery: an admin (behind step-up) or platform
support (with an out-of-band check) revokes every session, retires every passkey and
opens a re-enrolment invitation for the address, and the person, plus every other admin,
is notified."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from apps.identity import mail, rate_limit, roles_logic, session_logic, tokens
from apps.identity.models import (
    Invitation,
    InvitationKind,
    InvitationRole,
    LoginEventKind,
    LoginMethod,
    Membership,
    MembershipRole,
    PlatformRoleAssignment,
    TenantRole,
    User,
    UserStatus,
    WebAuthnCredential,
)
from apps.identity.security_log import client_ip, log_event
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant


class InvitationExpired(ValidationError):
    """Opened after expiry, after acceptance or after revocation (410 invitation_expired)."""


def normalise_email(email: str) -> str:
    cleaned = email.strip().lower()
    if "@" not in cleaned:
        raise ValidationError("Enter a valid email address.", code="invalid_email")
    return cleaned


def get_or_create_user(email: str, *, name: str | None = None) -> User:
    cleaned = normalise_email(email)
    user = User.objects.filter(email=cleaned).first()  # ordering: email is unique, at most one row
    if user is None:
        user = User.objects.create(email=cleaned, name=name or cleaned.split("@")[0], status=UserStatus.INVITED.value)
    return user


def invitation_status(invitation: Invitation, now: datetime | None = None) -> str:
    now = now or timezone.now()
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.expires_at <= now:
        return "expired"
    return "pending"


def is_open(invitation: Invitation, now: datetime | None = None) -> bool:
    return invitation_status(invitation, now) == "pending"


# ---------------------------------------------------------------------------------------
# Lookups the auth layer makes before a tenant is known
# ---------------------------------------------------------------------------------------
def find_by_token(token: str) -> Invitation | None:
    with tenancy.identity_lookup():
        return Invitation.objects.select_related("tenant").filter(token_hash=tokens.hash_token(token)).first()  # ordering: token_hash is unique, at most one row


def find_open_for_email(email: str) -> Invitation | None:
    now = timezone.now()
    with tenancy.identity_lookup():
        return (
            Invitation.objects.select_related("tenant")
            .filter(email=email, accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=now)
            .order_by("-created_at", "-id")
            .first()
        )


def find_open_for_tenant(email: str, tenant_id: uuid.UUID | None) -> Invitation | None:
    """The open invitation for `email` in one tenant (None: a platform invitation). The
    enrolment ceremony accepts the invitation its session came from, not the newest
    (finding F8). The caller has activated the tenant."""
    now = timezone.now()
    scope = Q(tenant__isnull=True) if tenant_id is None else Q(tenant_id=tenant_id)
    return (
        Invitation.objects.select_related("tenant")
        .filter(scope, email=email, accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=now)
        .order_by("-created_at", "-id")
        .first()
    )


def has_live_passkey(user: User) -> bool:
    return WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).exists()


PLATFORM_ACCOUNT_REFUSAL = (
    "That address belongs to platform staff, who sign in with an account of their own. "
    "Invite this person with a work address the platform does not use."
)


def holds_a_platform_role(user: User) -> bool:
    """True when the account holds any platform role assignment, whether or not that role
    row is still active (a retired role can be brought back, and the account is platform
    staff either way). Read without the identity-lookup flag: platform_role_assignment
    belongs to no tenant and carries no row-level security, so the flag would only add two
    set_config queries and a transaction to every invitation. `build_principal` reads the
    same table the same way."""
    return PlatformRoleAssignment.objects.filter(user=user).exists()


def refuse_platform_account(user: User) -> None:
    """A bank invitation never goes to platform staff (ID-01, ADM-02, hardening H13), and
    never becomes a membership: `bootstrap_platform` refuses an address a bank knows, and
    this refuses the other direction, at creation and again at acceptance, since a role
    can be granted in between. One account holding both zones' grants is what keeps them
    two zones."""
    if holds_a_platform_role(user):
        raise ValidationError(PLATFORM_ACCOUNT_REFUSAL, code="platform_account")


def belongs_to_a_tenant(user: User) -> bool:
    """True when any bank knows this person: a membership, active or deactivated (a
    deactivated member can be invited back), or a bank invitation not yet accepted or
    revoked (an expired one counts, because the bank can resend it). bootstrap_platform
    refuses such a person, since platform staff are separate accounts: a platform role on
    a bank member's account would reach into their bank session."""
    with tenancy.identity_lookup():
        return (
            Membership.objects.filter(user=user).exists()
            or Invitation.objects.filter(
                tenant__isnull=False, email=user.email, accepted_at__isnull=True, revoked_at__isnull=True
            ).exists()
        )


# ---------------------------------------------------------------------------------------
# Creating, resending, revoking
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class IssuedInvitation:
    invitation: Invitation
    token: str


def _new_token_fields(now: datetime) -> tuple[str, str, datetime]:
    token = tokens.new_token(32)
    return token, tokens.hash_token(token), now + timedelta(hours=settings.INVITATION_TTL_HOURS)


def create_invitation(
    *,
    tenant: Tenant | None,
    email: str,
    roles: Iterable[TenantRole],
    title: str,
    invited_by: User | None,
    actor: Actor,
    kind: InvitationKind = InvitationKind.INVITE,
    step_up_assertion_id: uuid.UUID | None = None,
    fixed_token: str | None = None,
) -> IssuedInvitation:
    """Create the row, email the link. `fixed_token` exists for the E2E seed alone."""
    cleaned = normalise_email(email)
    now = timezone.now()
    user = get_or_create_user(cleaned)
    if tenant is not None:
        refuse_platform_account(user)
    if kind is InvitationKind.INVITE and tenant is not None:
        if Membership.objects.filter(tenant=tenant, user=user, deactivated_at__isnull=True).exists():
            raise ValidationError("That person is already a member.", code="already_member")
    token, token_hash, expires_at = _new_token_fields(now)
    if fixed_token is not None:
        token, token_hash = fixed_token, tokens.hash_token(fixed_token)
    # An earlier open invitation for the same address in this tenant is superseded.
    Invitation.objects.filter(
        tenant=tenant, email=cleaned, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)
    invitation = Invitation.objects.create(
        tenant=tenant,
        email=cleaned,
        title=title.strip(),
        token_hash=token_hash,
        kind=kind.value,
        invited_by=invited_by,
        expires_at=expires_at,
    )
    role_keys: list[str] = []
    for role in roles:
        InvitationRole.objects.create(tenant=tenant, invitation=invitation, role=role)
        role_keys.append(role.key)
    mail.send_invitation(cleaned, token, tenant.name if tenant else None, reenrolment=kind is InvitationKind.REENROLMENT)
    record(
        action="invitation.created" if kind is InvitationKind.INVITE else "enrolment.reissued",
        actor=actor,
        subject_type="invitation",
        subject_id=invitation.id,
        subject_title=user.name,
        summary=f"{'Invitation' if kind is InvitationKind.INVITE else 'Re-enrolment'} sent with roles {', '.join(role_keys) or 'none'}.",
        tenant_id=tenant.id if tenant else None,
        after={"userId": str(user.id), "roles": role_keys, "kind": kind.value, "expiresAt": expires_at.isoformat()},
        step_up_assertion_id=step_up_assertion_id,
    )
    return IssuedInvitation(invitation=invitation, token=token)


def resend_invitation(*, tenant: Tenant, invitation: Invitation, actor: Actor) -> IssuedInvitation:
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise ValidationError("This invitation is no longer open.", code="invitation_closed")
    now = timezone.now()
    token, invitation.token_hash, invitation.expires_at = _new_token_fields(now)
    invitation.save(update_fields=["token_hash", "expires_at"])
    mail.send_invitation(invitation.email, token, tenant.name, reenrolment=invitation.kind == InvitationKind.REENROLMENT.value)
    record(
        action="invitation.resent",
        actor=actor,
        subject_type="invitation",
        subject_id=invitation.id,
        subject_title=invitation.email.split("@")[0],
        summary="Invitation resent with a new token.",
        tenant_id=tenant.id,
        after={"expiresAt": invitation.expires_at.isoformat()},
    )
    return IssuedInvitation(invitation=invitation, token=token)


def revoke_invitation(*, tenant: Tenant, invitation: Invitation, actor: Actor) -> Invitation:
    if invitation.revoked_at is None and invitation.accepted_at is None:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
    record(
        action="invitation.revoked",
        actor=actor,
        subject_type="invitation",
        subject_id=invitation.id,
        subject_title=invitation.email.split("@")[0],
        summary="Invitation revoked.",
        tenant_id=tenant.id,
    )
    return invitation


# ---------------------------------------------------------------------------------------
# Opening (ID-02) and accepting (the first passkey, ID-03)
# ---------------------------------------------------------------------------------------
def open_invitation(token: str, request: HttpRequest | None) -> Invitation:
    """A valid token sends a code to the invited address; anything else is 410."""
    from apps.identity import code_logic

    # Per IP before the lookup, so unknown tokens are bounded like every other
    # unauthenticated ceremony step (finding F5).
    rate_limit.enforce("auth:ip", client_ip(request) or "", settings.AUTH_RATE_PER_IP_PER_MINUTE, 60, e2e_exempt=True)
    invitation = find_by_token(token)
    if invitation is None or not is_open(invitation):
        raise InvitationExpired("This invitation link has expired or was already used.", code="invitation_expired")
    code_logic.enforce_code_limits(invitation.email, request)
    if invitation.tenant_id is not None:
        tenancy.activate(invitation.tenant_id)
    user = get_or_create_user(invitation.email)
    code_logic.issue_code(user=user, tenant_id=invitation.tenant_id, request=request)
    record(
        action="invitation.opened",
        actor=Actor.system("invitee"),
        subject_type="invitation",
        subject_id=invitation.id,
        subject_title=user.name,
        summary="Invitation opened; a code was sent.",
        tenant_id=invitation.tenant_id,
    )
    return invitation


def accept_invitation(invitation: Invitation, user: User, now: datetime) -> Membership | None:
    """Called when the first passkey is stored: mark accepted and, for a tenant
    invitation, create the membership with the invited roles (a re-enrolment keeps the
    existing membership). The caller has activated the invitation's tenant."""
    if invitation.tenant_id is not None:
        # A platform role granted after the invitation was sent: refuse before anything is
        # written, so the enrolment leaves no membership behind (hardening H13).
        refuse_platform_account(user)
    invitation.accepted_at = now
    invitation.accepted_user = user
    invitation.save(update_fields=["accepted_at", "accepted_user"])
    if invitation.tenant_id is None:
        return None
    membership = Membership.objects.filter(tenant_id=invitation.tenant_id, user=user).first()  # ordering: unique (tenant, user), at most one row
    if membership is None:
        membership = Membership.objects.create(
            tenant_id=invitation.tenant_id, user=user, title=invitation.title, invited_by=invitation.invited_by
        )
    elif membership.deactivated_at is not None:
        # A deactivated member invited again comes back with the roles of the new
        # invitation, not the old ones (a full session needs an active membership,
        # finding F7).
        membership.deactivated_at = None
        membership.title = invitation.title
        membership.invited_by = invitation.invited_by
        membership.save(update_fields=["deactivated_at", "title", "invited_by"])
        MembershipRole.objects.filter(membership=membership).delete()
    else:
        return membership
    for link in invitation.role_links.select_related("role"):
        MembershipRole.objects.create(tenant_id=invitation.tenant_id, membership=membership, role=link.role)
    return membership


# ---------------------------------------------------------------------------------------
# Re-enrolment (ID-05)
# ---------------------------------------------------------------------------------------
def other_admin_emails(tenant: Tenant, *, excluding: User) -> list[str]:
    emails: list[str] = []
    memberships = (
        Membership.objects.filter(tenant=tenant, deactivated_at__isnull=True)
        .exclude(user=excluding)
        .select_related("user")
        .prefetch_related("roles")
    )
    for membership in memberships:
        if perms.MEMBERS_MANAGE in roles_logic.permissions_of(membership.roles.all()):
            emails.append(membership.user.email)
    return emails


def reissue_enrolment(
    *,
    tenant: Tenant,
    user: User,
    actor: Actor,
    actor_user: User,
    request: HttpRequest | None,
    step_up_assertion_id: uuid.UUID | None,
    extra_after: dict[str, object] | None = None,
) -> IssuedInvitation:
    membership = Membership.objects.filter(tenant=tenant, user=user, deactivated_at__isnull=True).first()  # ordering: unique (tenant, user), at most one row
    if membership is None:
        raise ValidationError("Not found.", code="not_found")
    now = timezone.now()
    revoked = session_logic.revoke_all(user, tenant_id=None, reason="reenrolment", actor=actor, request=request)
    retired = WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).update(retired_at=now)
    # Awaiting enrolment again: the next passkey registration sets her active.
    user.status = UserStatus.INVITED.value
    user.save(update_fields=["status"])
    issued = create_invitation(
        tenant=tenant,
        email=user.email,
        roles=list(membership.roles.all()),
        title=membership.title,
        invited_by=actor_user,
        actor=actor,
        kind=InvitationKind.REENROLMENT,
        step_up_assertion_id=step_up_assertion_id,
    )
    for admin_email in other_admin_emails(tenant, excluding=user):
        if admin_email != actor_user.email:
            mail.send_reenrolment_notice(admin_email, user.name, tenant.name, actor_user.name)
    log_event(
        event=LoginEventKind.REENROLMENT_ISSUED,
        method=LoginMethod.EMAIL_CODE,
        success=True,
        request=request,
        user=user,
        tenant_id=tenant.id,
        failure_reason="",
    )
    record(
        action="member.enrolment_reissued",
        actor=actor,
        subject_type="user",
        subject_id=user.id,
        subject_title=user.name,
        summary=f"Enrolment re-issued: {revoked} session(s) revoked, {retired} passkey(s) retired.",
        tenant_id=tenant.id,
        after={"sessionsRevoked": revoked, "passkeysRetired": retired, "invitationId": str(issued.invitation.id), **(extra_after or {})},
        step_up_assertion_id=step_up_assertion_id,
    )
    return issued
