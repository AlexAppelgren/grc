"""Tenant members (ID-01, ID-09, ADM-01): the list, invitations, role and title changes,
deactivation, sessions and re-enrolment. A tenant always keeps one member holding
`members.manage` (ID-S19): every change that would remove the last one answers 409
`last_admin`. Role changes and re-enrolment need a fresh step-up assertion, which the
route puts on the request and the logic stores on the audit event."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpRequest
from django.utils import timezone

from apps.identity import invitation_logic, roles_logic, session_logic
from apps.identity.models import Invitation, InvitationKind, Membership, MembershipRole, User, UserSession
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.taxonomy.models import Team
from apps.tenants.models import TeamMember


def membership_of(tenant_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    membership = (
        Membership.objects.filter(tenant_id=tenant_id, user_id=user_id, deactivated_at__isnull=True)
        .select_related("user")
        .prefetch_related("roles__labels")
        .first()
    )  # ordering: unique (tenant, user), at most one row
    if membership is None:
        raise ValidationError("Not found.", code="not_found")
    return membership


def _status(membership: Membership) -> str:
    if membership.deactivated_at is not None:
        return "deactivated"
    return membership.user.status


def team_keys(tenant_id: uuid.UUID, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Each person's team keys in the team list's order, in one query (TEN-03)."""
    keys: dict[uuid.UUID, list[str]] = {user_id: [] for user_id in user_ids}
    rows = (
        TeamMember.objects.filter(tenant_id=tenant_id, user_id__in=user_ids)
        .order_by("team__sort_order", "team__key")
        .values_list("user_id", "team__key")
    )
    for user_id, key in rows:
        keys[user_id].append(key)
    return keys


def member_out(membership: Membership, order: list[str], *, passkey_count: int, active_sessions: int, teams: list[str]) -> dict[str, Any]:
    user = membership.user
    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "status": _status(membership),
        "roles": [roles_logic.role_ref(role, order) for role in membership.roles.all()],
        "title": membership.title,
        "last_seen_at": user.last_seen_at,
        "passkey_count": passkey_count,
        "active_sessions": active_sessions,
        "teams": teams,
    }


def list_members(tenant_id: uuid.UUID, order: list[str], *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    now = timezone.now()
    queryset = (
        Membership.objects.filter(tenant_id=tenant_id)
        .select_related("user")
        .prefetch_related("roles__labels")
        .annotate(
            passkey_count=Count("user__credentials", filter=Q(user__credentials__retired_at__isnull=True), distinct=True),
            active_sessions=Count(
                "user__sessions",
                filter=Q(user__sessions__revoked_at__isnull=True, user__sessions__expires_at__gt=now, user__sessions__kind="full", user__sessions__tenant_id=tenant_id),
                distinct=True,
            ),
        )
        .order_by("created_at", "id")
    )
    total = queryset.count()
    rows = list(queryset[offset : offset + limit])
    teams = team_keys(tenant_id, [m.user_id for m in rows])
    return [
        member_out(m, order, passkey_count=m.passkey_count, active_sessions=m.active_sessions, teams=teams[m.user_id]) for m in rows
    ], total


def member_detail(tenant_id: uuid.UUID, user_id: uuid.UUID, order: list[str]) -> dict[str, Any]:
    membership = membership_of(tenant_id, user_id)
    passkeys = membership.user.credentials.filter(retired_at__isnull=True).count()
    sessions = len(session_logic.live_sessions(membership.user, tenant_id=tenant_id))
    teams = team_keys(tenant_id, [user_id])[user_id]
    return member_out(membership, order, passkey_count=passkeys, active_sessions=sessions, teams=teams)


# ---------------------------------------------------------------------------------------
# Last admin (ID-S19)
# ---------------------------------------------------------------------------------------
def admins_besides(tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
    count = 0
    memberships = (
        Membership.objects.filter(tenant_id=tenant_id, deactivated_at__isnull=True)
        .exclude(user_id=user_id)
        .prefetch_related("roles")
    )
    for membership in memberships:
        if perms.MEMBERS_MANAGE in roles_logic.permissions_of(membership.roles.all()):
            count += 1
    return count


def assert_not_last_admin(tenant_id: uuid.UUID, membership: Membership, *, keeps_members_manage: bool) -> None:
    holds = perms.MEMBERS_MANAGE in roles_logic.permissions_of(membership.roles.all())
    if holds and not keeps_members_manage and admins_besides(tenant_id, membership.user_id) == 0:
        raise ValidationError("A tenant always keeps one administrator.", code="last_admin")


# ---------------------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------------------
def invitation_out(invitation: Invitation, order: list[str]) -> dict[str, Any]:
    return {
        "id": invitation.id,
        "email": invitation.email,
        "roles": [roles_logic.role_ref(link.role, order) for link in invitation.role_links.all()],
        "title": invitation.title,
        "kind": invitation.kind,
        "status": invitation_logic.invitation_status(invitation),
        "created_at": invitation.created_at,
        "expires_at": invitation.expires_at,
    }


def invite_member(*, tenant: Tenant, actor: Actor, invited_by: User, email: str, role_keys: Iterable[str], title: str) -> Invitation:
    roles = roles_logic.roles_by_keys(tenant.id, role_keys)
    issued = invitation_logic.create_invitation(tenant=tenant, email=email, roles=roles, title=title, invited_by=invited_by, actor=actor)
    return Invitation.objects.prefetch_related("role_links__role__labels").get(pk=issued.invitation.pk)


def list_invitations(tenant_id: uuid.UUID, order: list[str], *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    queryset = (
        Invitation.objects.filter(tenant_id=tenant_id)
        .prefetch_related("role_links__role__labels")
        .order_by("-created_at", "-id")
    )
    total = queryset.count()
    return [invitation_out(row, order) for row in queryset[offset : offset + limit]], total


def tenant_invitation(tenant_id: uuid.UUID, invitation_id: uuid.UUID) -> Invitation:
    row = Invitation.objects.filter(pk=invitation_id, tenant_id=tenant_id).prefetch_related("role_links__role__labels").first()  # ordering: pk lookup, at most one row
    if row is None:
        raise ValidationError("Not found.", code="not_found")
    return row


# ---------------------------------------------------------------------------------------
# Changing and removing members
# ---------------------------------------------------------------------------------------
def update_member(
    *,
    tenant: Tenant,
    actor: Actor,
    user_id: uuid.UUID,
    role_keys: Iterable[str] | None,
    title: str | None,
    step_up_assertion_id: uuid.UUID | None,
) -> Membership:
    membership = membership_of(tenant.id, user_id)
    before = {"roles": sorted(role.key for role in membership.roles.all()), "title": membership.title}
    if role_keys is not None:
        roles = roles_logic.roles_by_keys(tenant.id, role_keys)
        keeps = perms.MEMBERS_MANAGE in roles_logic.permissions_of(roles)
        assert_not_last_admin(tenant.id, membership, keeps_members_manage=keeps)
        MembershipRole.objects.filter(membership=membership).delete()
        for role in roles:
            MembershipRole.objects.create(tenant=tenant, membership=membership, role=role)
    if title is not None:
        membership.title = title.strip()
        membership.save(update_fields=["title"])
    membership = membership_of(tenant.id, user_id)
    after = {"roles": sorted(role.key for role in membership.roles.all()), "title": membership.title}
    record(
        action="member.updated",
        actor=actor,
        subject_type="membership",
        subject_id=membership.id,
        subject_title=membership.user.name,
        summary="Member roles or title changed.",
        tenant_id=tenant.id,
        before=before,
        after=after,
        step_up_assertion_id=step_up_assertion_id,
    )
    return membership


def deactivate_member(*, tenant: Tenant, actor: Actor, user_id: uuid.UUID, request: HttpRequest | None) -> Membership:
    membership = membership_of(tenant.id, user_id)
    assert_not_last_admin(tenant.id, membership, keeps_members_manage=False)
    now = timezone.now()
    membership.deactivated_at = now
    membership.save(update_fields=["deactivated_at"])
    revoked = session_logic.revoke_all(membership.user, tenant_id=tenant.id, reason="member_deactivated", actor=actor, request=request)
    # An open invitation or re-enrolment for the address would let the person enrol back
    # into the tenant after removal; it closes with the membership (finding F7).
    closed = Invitation.objects.filter(
        tenant=tenant, email=membership.user.email, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)
    record(
        action="member.deactivated",
        actor=actor,
        subject_type="membership",
        subject_id=membership.id,
        subject_title=membership.user.name,
        summary=f"Member deactivated; {revoked} session(s) revoked, {closed} open invitation(s) closed.",
        tenant_id=tenant.id,
        before={"deactivatedAt": None},
        after={"deactivatedAt": membership.deactivated_at.isoformat(), "invitationsClosed": closed},
    )
    return membership


def set_member_teams(*, tenant: Tenant, actor: Actor, user_id: uuid.UUID, keys: Iterable[str]) -> Membership:
    """The whole set of teams a current member is in (TEN-03, D-21), in one audit event with the
    keys before and after. The member row is locked, so two administrators setting the same
    person's teams at once are applied one after the other. A retired team takes nobody new
    but keeps who is already in it."""
    membership = (
        Membership.objects.select_for_update(of=("self",))
        .select_related("user")
        .filter(tenant=tenant, user_id=user_id, deactivated_at__isnull=True)
        .first()
    )  # ordering: unique (tenant, user), at most one row
    if membership is None:
        raise ValidationError("That person is not a member of this bank.", code="unknown_member")
    current = {row.team.key: row for row in TeamMember.objects.filter(tenant=tenant, user_id=user_id).select_related("team")}
    wanted = set(keys)
    teams = {team.key: team for team in Team.objects.filter(tenant=tenant, key__in=wanted - set(current), active=True)}
    if wanted - set(current) - set(teams):
        raise ValidationError("That is not one of this bank's teams.", code="unknown_key")
    before = team_keys(tenant.id, [user_id])[user_id]
    TeamMember.objects.filter(pk__in=[row.pk for key, row in current.items() if key not in wanted]).delete()
    for team in teams.values():
        TeamMember.objects.create(tenant=tenant, team=team, user_id=user_id)
    record(
        action="member.teams_changed",
        actor=actor,
        subject_type="membership",
        subject_id=membership.id,
        subject_title=membership.user.name,
        summary="Member teams changed.",
        tenant_id=tenant.id,
        before={"teams": before},
        after={"teams": team_keys(tenant.id, [user_id])[user_id]},
    )
    return membership


def member_sessions(tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[UserSession]:
    membership = membership_of(tenant_id, user_id)
    return session_logic.live_sessions(membership.user, tenant_id=tenant_id)


def revoke_member_sessions(*, tenant: Tenant, actor: Actor, user_id: uuid.UUID, request: HttpRequest | None) -> int:
    membership = membership_of(tenant.id, user_id)
    revoked = session_logic.revoke_all(membership.user, tenant_id=tenant.id, reason="revoked_by_admin", actor=actor, request=request)
    record(
        action="member.sessions_revoked",
        actor=actor,
        subject_type="membership",
        subject_id=membership.id,
        subject_title=membership.user.name,
        summary=f"{revoked} session(s) revoked by an administrator.",
        tenant_id=tenant.id,
        after={"sessionsRevoked": revoked},
    )
    return revoked


def reissue_enrolment(
    *, tenant: Tenant, actor: Actor, actor_user: User, user_id: uuid.UUID, request: HttpRequest | None, step_up_assertion_id: uuid.UUID | None
) -> Invitation:
    membership = membership_of(tenant.id, user_id)
    issued = invitation_logic.reissue_enrolment(
        tenant=tenant, user=membership.user, actor=actor, actor_user=actor_user, request=request, step_up_assertion_id=step_up_assertion_id
    )
    return issued.invitation


def is_reenrolment(invitation: Invitation) -> bool:
    return invitation.kind == InvitationKind.REENROLMENT.value
