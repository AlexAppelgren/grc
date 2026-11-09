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

from apps.identity import api_keys_logic, mail, rate_limit, roles_logic, session_logic, tokens
from apps.identity.models import (
    Invitation,
    InvitationKind,
    InvitationRole,
    LoginEventKind,
    LoginMethod,
    Membership,
    MembershipRole,
    TenantRole,
    User,
    UserStatus,
    WebAuthnCredential,
)
from apps.identity.security_log import client_ip, log_event
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.audit import Actor, batched, record
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


def first_administrator_invitations(tenant_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Invitation]:
    """Each bank's first-administrator invitation: the one the console sent when it created
    the bank (D-123). A console session holds no bank's zone, so the rows are read through
    the identity lookup, and only these marked rows: nothing a bank's own members sent is
    read."""
    with tenancy.identity_lookup():
        rows = Invitation.objects.filter(tenant_id__in=list(tenant_ids), first_administrator=True).order_by("created_at", "id")
        return {row.tenant_id: row for row in rows if row.tenant_id is not None}


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
    first_administrator: bool = False,
) -> IssuedInvitation:
    """Create the row, email the link. `fixed_token` exists for the E2E seed alone."""
    cleaned = normalise_email(email)
    now = timezone.now()
    user = get_or_create_user(cleaned)
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
        first_administrator=first_administrator,
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
    if has_live_passkey(user):
        # An address that holds a passkey is sent nothing, as on the code request (AC-ID1):
        # since D-122 a bank may invite one, and it joins with its passkey through
        # `accept_signed_in`. The answer and the hashing work are the same either way.
        tokens.hash_code(tokens.new_code(), tokens.new_salt())
        log_event(
            event=LoginEventKind.CODE_REFUSED_ENROLLED,
            method=LoginMethod.EMAIL_CODE,
            success=False,
            request=request,
            user=user,
            tenant_id=invitation.tenant_id,
            failure_reason="passkey_enrolled",
        )
        summary = "Invitation opened; no code: the account holds a passkey."
    else:
        code_logic.issue_code(user=user, tenant_id=invitation.tenant_id, request=request)
        summary = "Invitation opened; a code was sent."
    record(
        action="invitation.opened",
        actor=Actor.system("invitee"),
        subject_type="invitation",
        subject_id=invitation.id,
        subject_title=user.name,
        summary=summary,
        tenant_id=invitation.tenant_id,
    )
    return invitation


INVITATION_ACCEPTED = "invitation_accepted"


def accept_signed_in(*, user: User, token: str, step_up_assertion_id: uuid.UUID, request: HttpRequest) -> Tenant:
    """A person who already holds a passkey joins the bank that invited them (D-122): the
    emailed code is refused to an enrolled account, so their own full session, stepped up
    with that passkey, is the proof instead. Only an open bank invitation to the signed-in
    person's own address is accepted; an unknown, closed or re-enrolment token and one sent
    to anyone else all answer 410 `invitation_expired` alike, so the answer never says
    whether a token exists for someone else. The session stays where it is; the caller
    moves with `switch_context`."""
    invitation = find_by_token(token)
    if (
        invitation is None
        or invitation.tenant_id is None
        or invitation.kind != InvitationKind.INVITE.value
        or invitation.email != normalise_email(user.email)
        or not is_open(invitation)
    ):
        raise InvitationExpired("This invitation link has expired or was already used.", code="invitation_expired")
    tenancy.activate(invitation.tenant_id)
    # Locked and read again inside the bank, so two accepts in flight make one membership.
    invitation = Invitation.objects.select_for_update(of=("self",)).select_related("tenant").get(pk=invitation.pk)
    if not is_open(invitation):
        raise InvitationExpired("This invitation link has expired or was already used.", code="invitation_expired")
    membership = accept_invitation(invitation, user, timezone.now())
    assert membership is not None and invitation.tenant is not None  # a bank invitation always makes one
    log_event(
        event=LoginEventKind.ENROLLED,
        method=LoginMethod.PASSKEY,
        success=True,
        request=request,
        user=user,
        tenant_id=invitation.tenant_id,
        failure_reason=INVITATION_ACCEPTED,
    )
    record(
        action="invitation.accepted",
        actor=session_logic.actor_of(user),
        subject_type="invitation",
        subject_id=invitation.id,
        subject_title=user.name,
        summary="Invitation accepted with a passkey; joined the bank.",
        tenant_id=invitation.tenant_id,
        after={
            "userId": str(user.id),
            "membershipId": str(membership.id),
            "roles": sorted(membership.roles.values_list("key", flat=True)),
        },
        step_up_assertion_id=step_up_assertion_id,
    )
    return invitation.tenant


def accept_invitation(invitation: Invitation, user: User, now: datetime) -> Membership | None:
    """Called when the first passkey is stored: mark accepted and, for a tenant
    invitation, create the membership with the invited roles (a re-enrolment keeps the
    existing membership). The caller has activated the invitation's tenant. Platform staff
    may accept one too (D-122): the membership's grants are read only in this bank's
    sessions."""
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


@batched()
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
    tokens_revoked = api_keys_logic.revoke_person_tokens(tenant_id=tenant.id, person=user, revoked_by=actor_user, now=now)
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
        after={
            "sessionsRevoked": revoked,
            "passkeysRetired": retired,
            "tokensRevoked": tokens_revoked,
            "invitationId": str(issued.invitation.id),
            **(extra_after or {}),
        },
        step_up_assertion_id=step_up_assertion_id,
    )
    return issued
