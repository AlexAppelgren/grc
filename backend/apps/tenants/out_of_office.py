"""Out of office with a delegate (TEN-04): a member's own absence, read and set.

An absence is two columns on the member's own membership, `out_of_office_until` (the last
day away, a plain date on the bank's calendar) and `delegate`. While the bank's local today
is on or before that day, `apps/collab/logic.notify()` sends the member's reminders,
escalations, assignments and sign-off requests to the delegate instead. Delegation routes
notices and grants nothing: the delegate acts under their own roles, so they must already
hold every approve permission the absent person holds (`delegate_cannot_approve`), and four
eyes still refuses a delegate who asked for what they would approve. `on_behalf_of` names
the absent approvers a delegate's approval was made for, for the audit row.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from apps.identity import roles_logic
from apps.identity.models import Membership, User, UserStatus
from apps.library.reading import today_for
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

SUBJECT_TYPE = "membership"


def _approve_permissions(membership: Membership) -> frozenset[str]:
    return roles_logic.permissions_of(membership.roles.all()) & perms.APPROVE_PERMISSIONS


def _is_open(membership: Membership, today: datetime.date) -> bool:
    return membership.out_of_office_until is not None and membership.out_of_office_until >= today


def _snapshot(membership: Membership) -> dict[str, Any]:
    """The absence as the audit event records it: a date and an id, never a label."""
    until = membership.out_of_office_until
    return {
        "untilDate": until.isoformat() if until else None,
        "delegateId": str(membership.delegate_id) if membership.delegate_id else None,
    }


def _out(membership: Membership, today: datetime.date) -> dict[str, Any]:
    delegate = membership.delegate
    return {
        "until_date": membership.out_of_office_until,
        "delegate": {"id": delegate.id, "name": delegate.name} if delegate else None,
        "away": _is_open(membership, today) and delegate is not None,
    }


def _own(tenant: Tenant, user: User, *, for_update: bool = False) -> Membership:
    rows = Membership.objects.select_related("delegate")
    if for_update:
        rows = rows.select_for_update(of=("self",))
    return rows.get(tenant=tenant, user=user)


def get_out_of_office(*, tenant: Tenant, user: User) -> dict[str, Any]:
    return _out(_own(tenant, user), today_for(tenant))


def _delegate(tenant: Tenant, delegate_id: uuid.UUID, absent: Membership) -> Membership:
    """Another active member of the bank, holding every approve permission `absent` holds."""
    delegate = (
        Membership.objects.select_related("user")
        .filter(tenant=tenant, user_id=delegate_id, deactivated_at__isnull=True, user__status=UserStatus.ACTIVE.value)
        .exclude(user_id=absent.user_id)
        .first()  # ordering: (tenant, user) is unique, at most one row
    )
    if delegate is None:
        raise ProblemError(
            status=422,
            code="validation_error",
            detail="Choose another active member of your company as your delegate.",
            errors=[{"field": "delegateId", "message": "Choose another active member of your company."}],
        )
    missing = _approve_permissions(absent) - _approve_permissions(delegate)
    if missing:
        raise ProblemError(
            status=422,
            code="delegate_cannot_approve",
            detail=f"{delegate.user.name} can't approve everything you can. Choose someone whose role lets them approve it.",
            errors=[{"field": "delegateId", "message": "This person can't approve what you approve."}],
        )
    return delegate


def set_out_of_office(
    *, tenant: Tenant, actor: Actor, user: User, until: datetime.date | None, delegate_id: uuid.UUID | None
) -> dict[str, Any]:
    """Start an absence, or end one early with both fields null. The membership row is
    locked first, so two starts at once queue and the second finds the first open."""
    if (until is None) != (delegate_id is None):
        raise ProblemError(
            status=422,
            code="validation_error",
            detail="Give both the last day you are away and your delegate, or neither to end your absence.",
            errors=[{"field": "untilDate" if until is None else "delegateId", "message": "Give both or neither."}],
        )
    today = today_for(tenant)
    membership = _own(tenant, user, for_update=True)
    before = _snapshot(membership)
    if until is None:
        membership.out_of_office_until = None
        membership.delegate = None
        action, summary = "out_of_office.ended", f"{actor.label} is back and no longer has a delegate."
    else:
        assert delegate_id is not None  # both or neither, checked above
        if until < today:
            raise ProblemError(
                status=422,
                code="validation_error",
                detail="The last day you are away can't be in the past.",
                errors=[{"field": "untilDate", "message": "Choose today or a later day."}],
            )
        if _is_open(membership, today):
            raise ProblemError(
                status=409,
                code="already_delegated",
                detail="You are already away with a delegate. End that absence before you set another.",
            )
        delegate = _delegate(tenant, delegate_id, membership)
        membership.out_of_office_until = until
        membership.delegate = delegate.user
        action = "out_of_office.set"
        summary = f"{actor.label} is away until {until.isoformat()} with {delegate.user.name} as delegate."
    membership.save(update_fields=["out_of_office_until", "delegate"])
    record(
        action=action,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=membership.id,
        subject_title=user.name,
        summary=summary,
        tenant_id=tenant.id,
        before=before,
        after=_snapshot(membership),
    )
    return _out(membership, today)


def on_behalf_of(*, tenant: Tenant, delegate_id: uuid.UUID, permission: str, exclude: uuid.UUID | None) -> list[str]:
    """The absent members holding `permission` who name `delegate_id` as their delegate
    through the bank's today, as sorted ids: whom a delegate's approval was made for.
    `exclude` is the requester, who was never asked to approve."""
    absent = Membership.objects.filter(
        tenant=tenant,
        delegate_id=delegate_id,
        out_of_office_until__gte=today_for(tenant),
        deactivated_at__isnull=True,
        roles__permissions__contains=[permission],
    )
    if exclude is not None:
        absent = absent.exclude(user_id=exclude)
    return sorted(str(user_id) for user_id in absent.values_list("user_id", flat=True).distinct())
