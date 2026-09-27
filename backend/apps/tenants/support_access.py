"""Support access, requested by the platform and granted by the bank (TEN-06, D-49, ADR
0042). A request grants nothing; a tenant admin approves it with a passkey, declines it or
revokes it, and support then reads under it and never writes. Each tenant-side function loads
the request in the caller's bank, so another bank's id answers 404.

This module is the request, the decision and the grant a support session stands on: entering
a bank under a grant (`enter`), the per-request check that the grant is still open
(`live_grant`) and the `support_access.read` row each request writes (`record_read`). It is
the one module that loads a grant (apps/shared/tests_support_session.py pins it), and the
console's own list of the caller's grants (`my_grants`) reads through the same own-grants policy.

A pending request and an open window lapse on read, with no job: `state_of()` is the one
place that reads the clock against a row.
"""

from __future__ import annotations

import datetime
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.identity import roles_logic
from apps.identity.models import Membership, User
from apps.identity.schemas import SessionTokens
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.audit import Actor, ActorType, record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy.schemas import PersonRef
from apps.tenants import mail
from apps.tenants.models import SupportAccess, SupportAccessLevel, SupportAccessStatus
from apps.tenants.schemas import (
    ConsoleSupportAccessBody,
    ConsoleSupportAccessGrant,
    ConsoleSupportAccessPage,
    SupportAccessGrant,
    SupportAccessPage,
    SupportAccessState,
)

PENDING: SupportAccessState = "pending"
ACTIVE: SupportAccessState = "active"


def state_of(grant: SupportAccess, now: datetime.datetime) -> SupportAccessState:
    """The published state (`SupportAccessState`): the stored status read against the clock."""
    if grant.access_level == SupportAccessLevel.WRITE.value:
        return "recovery"
    if grant.status == SupportAccessStatus.REQUESTED.value:
        return "lapsed" if grant.request_expires_at is None or now >= grant.request_expires_at else PENDING
    if grant.status == SupportAccessStatus.APPROVED.value:
        return "ended" if grant.expires_at is None or now >= grant.expires_at else ACTIVE
    if grant.status == SupportAccessStatus.EXPIRED.value:
        return "ended" if grant.started_at is not None else "lapsed"
    return "declined" if grant.status == SupportAccessStatus.DECLINED.value else "revoked"


def _person(user: User | None) -> PersonRef | None:
    return None if user is None else PersonRef(id=user.id, name=user.name)


def _ends_at(grant: SupportAccess) -> datetime.datetime | None:
    return grant.ended_at if grant.status == SupportAccessStatus.REVOKED.value else grant.expires_at


def _decided_at(grant: SupportAccess) -> datetime.datetime | None:
    if grant.ended_by_id is not None:
        return grant.ended_at
    return grant.started_at if grant.approved_by_id is not None else None


def _out(grant: SupportAccess, now: datetime.datetime) -> SupportAccessGrant:
    return SupportAccessGrant(
        id=grant.id,
        state=state_of(grant, now),
        purpose=grant.reason,
        ticket_ref=grant.ticket_ref,
        hours=grant.hours,
        platform_person=PersonRef(id=grant.platform_user.id, name=grant.platform_user.name),
        requested_at=grant.requested_at,
        decided_by=_person(grant.ended_by or grant.approved_by),
        decided_at=_decided_at(grant),
        ends_at=_ends_at(grant),
    )


def grant_of(tenant: Tenant, grant_id: uuid.UUID) -> SupportAccess:
    """The request, in the caller's bank and under its row-level security, or 404. Locked,
    so two admins deciding at once decide one after the other."""
    grant = (
        SupportAccess.objects.select_for_update(of=("self",))
        .select_related("platform_user")
        .filter(tenant=tenant, pk=grant_id)
        .first()  # ordering: pk lookup, at most one row
    )
    if grant is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return grant


def _security_holders(tenant: Tenant) -> list[str]:
    """The addresses of the bank's active members who hold `security.manage`."""
    memberships = (
        Membership.objects.filter(tenant=tenant, deactivated_at__isnull=True)
        .select_related("user")
        .prefetch_related("roles")
    )
    return [
        membership.user.email
        for membership in memberships
        if perms.SECURITY_MANAGE in roles_logic.permissions_of(membership.roles.all())
    ]


def request_access(
    *, tenant_id: uuid.UUID, requester: User, actor: Actor, body: ConsoleSupportAccessBody
) -> ConsoleSupportAccessGrant:
    """`POST /console/tenants/{tenantId}/support-access`: writes the request and its audit
    row in the bank, and nothing else, then tells the bank's `security.manage` holders."""
    tenant = Tenant.objects.filter(pk=tenant_id).first()  # ordering: pk lookup, at most one row
    if tenant is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    if not body.purpose.strip():
        raise ValidationError("Say why support needs to look.", code="validation_error")
    if body.hours > settings.SUPPORT_ACCESS_MAX_HOURS:
        raise ValidationError(
            f"Ask for at most {settings.SUPPORT_ACCESS_MAX_HOURS} hours.", code="validation_error"
        )
    now = timezone.now()
    # Platform staff have no bypass: the request is written in the bank's own zone, and it
    # opens nothing there.
    tenancy.activate(tenant.id)
    grant = SupportAccess.objects.create(
        tenant=tenant,
        platform_user=requester,
        reason=body.purpose.strip(),
        ticket_ref=body.ticket_ref,
        access_level=SupportAccessLevel.READ.value,
        status=SupportAccessStatus.REQUESTED.value,
        hours=body.hours,
        requested_at=now,
        request_expires_at=now + datetime.timedelta(hours=settings.SUPPORT_ACCESS_REQUEST_TTL_HOURS),
    )
    record(
        action="support_access.requested",
        actor=actor,
        subject_type="support_access",
        subject_id=grant.id,
        subject_title=requester.name,
        summary="Platform support asked to read the bank.",
        tenant_id=tenant.id,
        after={"purpose": grant.reason, "ticketRef": grant.ticket_ref, "hours": grant.hours, "platformUserId": str(requester.id)},
    )
    for address in _security_holders(tenant):
        mail.send_support_request(
            address,
            tenant_name=tenant.name,
            requester=requester.name,
            purpose=grant.reason,
            ticket_ref=grant.ticket_ref,
            hours=grant.hours,
        )
    return _console_out(grant, tenant, now)


def _console_out(grant: SupportAccess, tenant: Tenant, now: datetime.datetime) -> ConsoleSupportAccessGrant:
    """A grant as the console shows it: the bank by its name, a decision by its time, and
    never the member who took it."""
    return ConsoleSupportAccessGrant(
        id=grant.id,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        state=state_of(grant, now),
        purpose=grant.reason,
        ticket_ref=grant.ticket_ref,
        hours=grant.hours,
        requested_at=grant.requested_at,
        decided_at=_decided_at(grant),
        ends_at=_ends_at(grant),
    )


def my_grants(*, principal: Principal, limit: int, offset: int) -> ConsoleSupportAccessPage:
    """`GET /console/support-access`: the caller's own requests across banks, newest first.
    No bank is active: the `support_access_own_grants` policy shows the rows naming the
    caller and nothing else, and the filter says the same thing again."""
    from apps.identity import session_logic

    now = timezone.now()
    with session_logic.own_grants(principal):
        rows = SupportAccess.objects.filter(platform_user_id=principal.subject_id).select_related("tenant")
        total = rows.count()
        page = list(rows.order_by("-requested_at", "-id")[offset : offset + limit])
    return ConsoleSupportAccessPage(items=[_console_out(grant, grant.tenant, now) for grant in page], total=total)


def live_grant(*, tenant_id: uuid.UUID, grant_id: uuid.UUID) -> SupportAccess | None:
    """The grant, when it is an open read-level window of the active bank; None when it is
    missing, another bank's, not approved, revoked or past its window. Read under the bank's
    own policies, so the caller activates `tenant_id` first and no read crosses a bank."""
    grant = SupportAccess.objects.filter(tenant_id=tenant_id, pk=grant_id).first()  # ordering: pk lookup, at most one row
    if grant is None or state_of(grant, timezone.now()) != ACTIVE:
        return None
    return grant


def enter(
    *, principal: Principal, grant_id: uuid.UUID, step_up_assertion_id: uuid.UUID, request: HttpRequest, response: HttpResponse
) -> SessionTokens:
    """`POST /console/support-access/{grantId}/enter`: replace the caller's console session
    with a support session in the bank that approved the grant.

    The grant is found through the `support_access_own_grants` policy, which shows the
    caller the rows naming them and nothing else, so another person's grant is 404 exactly as
    a missing one is, and so is a grant that is not open. The session is then written in the
    grant's bank, whose composite key refuses any other bank, and every request under it
    re-reads the grant under that bank's own policies (`live_grant`)."""
    from apps.identity import session_logic

    with session_logic.own_grants(principal):
        grant = SupportAccess.objects.filter(pk=grant_id, platform_user_id=principal.subject_id).first()  # ordering: pk lookup, at most one row
    if grant is None or state_of(grant, timezone.now()) != ACTIVE:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    user = User.objects.get(pk=principal.subject_id)
    assert principal.session_id is not None  # a person's session always names itself
    bundle = session_logic.create_support_session(user=user, grant=grant, replacing=principal.session_id, request=request)
    record(
        action="support_access.entered",
        actor=Actor(kind=ActorType.USER, id=user.id, label=user.name),
        subject_type="support_access",
        subject_id=grant.id,
        subject_title=user.name,
        summary="Platform support entered the bank read-only under its grant.",
        tenant_id=grant.tenant_id,
        after={"platformUserId": str(user.id), "sessionId": str(bundle.session.id), "endsAt": bundle.session.expires_at.isoformat()},
        step_up_assertion_id=step_up_assertion_id,
    )
    session_logic.set_refresh_cookie(response, bundle.refresh_value)
    return SessionTokens(access_token=bundle.access_token, session_kind=bundle.session.kind, expires_in=bundle.expires_in)


def record_read(*, principal: Principal, method: str, route: str, path_ids: dict[str, str]) -> None:
    """One `support_access.read` row in the bank for a request under a grant: who, which
    grant, the method, the route template and its path ids. Never a query string, a body or
    anything the bank wrote."""
    assert principal.support_access_id is not None and principal.tenant_id is not None  # a support principal
    user = User.objects.get(pk=principal.subject_id)
    record(
        action="support_access.read",
        actor=Actor(kind=ActorType.USER, id=user.id, label=user.name),
        subject_type="support_access",
        subject_id=principal.support_access_id,
        subject_title=user.name,
        summary="Platform support read the bank under its grant.",
        tenant_id=principal.tenant_id,
        after={"method": method, "route": route, "pathIds": path_ids, "platformUserId": str(user.id)},
    )


def list_for_tenant(*, tenant: Tenant, limit: int, offset: int) -> SupportAccessPage:
    """`GET /tenant/support-access`: every request the bank has had, newest first."""
    grants = SupportAccess.objects.filter(tenant=tenant).select_related("platform_user", "approved_by", "ended_by")
    now = timezone.now()
    page = grants.order_by("-requested_at", "-id")[offset : offset + limit]
    return SupportAccessPage(items=[_out(grant, now) for grant in page], total=grants.count())


def _refuse_unless(grant: SupportAccess, state: SupportAccessState, now: datetime.datetime, detail: str) -> None:
    if state_of(grant, now) != state:
        raise ValidationError(detail, code="invalid_transition")


def _decided(
    grant: SupportAccess,
    *,
    was: SupportAccessState,
    action: str,
    actor: Actor,
    summary: str,
    now: datetime.datetime,
    step_up_assertion_id: uuid.UUID | None = None,
) -> SupportAccessGrant:
    """Record the decision in the bank, naming both people, and answer with the request."""
    ends_at = _ends_at(grant)
    record(
        action=action,
        actor=actor,
        subject_type="support_access",
        subject_id=grant.id,
        subject_title=grant.platform_user.name,
        summary=summary,
        tenant_id=grant.tenant_id,
        before={"state": was},
        after={
            "state": state_of(grant, now),
            "platformUserId": str(grant.platform_user_id),
            "decidedBy": str(actor.id),
            "endsAt": None if ends_at is None else ends_at.isoformat(),
        },
        step_up_assertion_id=step_up_assertion_id,
    )
    grant = SupportAccess.objects.select_related("platform_user", "approved_by", "ended_by").get(pk=grant.pk)
    return _out(grant, now)


def approve(*, tenant: Tenant, actor: Actor, grant_id: uuid.UUID, step_up_assertion_id: uuid.UUID) -> SupportAccessGrant:
    """`POST /tenant/support-access/{grantId}/approve`: the window starts now."""
    grant = grant_of(tenant, grant_id)
    now = timezone.now()
    _refuse_unless(grant, PENDING, now, "Only a pending request can be approved.")
    if actor.id == grant.platform_user_id:
        raise ValidationError("The person who asked cannot approve their own access.", code="four_eyes_violation")
    grant.status = SupportAccessStatus.APPROVED.value
    grant.approved_by_id = actor.id
    grant.approved_step_up_assertion_id = step_up_assertion_id
    grant.started_at = now
    grant.expires_at = now + datetime.timedelta(hours=grant.hours)
    grant.save(update_fields=["status", "approved_by", "approved_step_up_assertion_id", "started_at", "expires_at"])
    return _decided(
        grant,
        was=PENDING,
        action="support_access.approved",
        actor=actor,
        summary="The bank let platform support read it for the window asked for.",
        now=now,
        step_up_assertion_id=step_up_assertion_id,
    )


def decline(*, tenant: Tenant, actor: Actor, grant_id: uuid.UUID) -> SupportAccessGrant:
    """`POST /tenant/support-access/{grantId}/decline`: nothing was ever granted."""
    grant = grant_of(tenant, grant_id)
    now = timezone.now()
    _refuse_unless(grant, PENDING, now, "Only a pending request can be declined.")
    _end(grant, SupportAccessStatus.DECLINED, actor, now)
    return _decided(grant, was=PENDING, action="support_access.declined", actor=actor, summary="The bank refused platform support's request.", now=now)


def revoke(*, tenant: Tenant, actor: Actor, grant_id: uuid.UUID) -> SupportAccessGrant:
    """`POST /tenant/support-access/{grantId}/revoke`: the window closes now, and the support
    session's next request finds the grant ended."""
    grant = grant_of(tenant, grant_id)
    now = timezone.now()
    _refuse_unless(grant, ACTIVE, now, "Only an open grant can be revoked.")
    _end(grant, SupportAccessStatus.REVOKED, actor, now)
    return _decided(grant, was=ACTIVE, action="support_access.revoked", actor=actor, summary="The bank ended platform support's access.", now=now)


def _end(grant: SupportAccess, status: SupportAccessStatus, actor: Actor, now: datetime.datetime) -> None:
    grant.status = status.value
    grant.ended_at = now
    grant.ended_by_id = actor.id
    grant.save(update_fields=["status", "ended_at", "ended_by"])
