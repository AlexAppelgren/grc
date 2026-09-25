"""The bank's session policy (ID-08, ADM-01): the read and the write, nothing else.

`apps/identity/session_logic.limits` enforces the limits at every refresh; this module
decides nothing about a session. A bank with no row reads the platform defaults, and the row
is created by the first write, never by a backfill. The write is a security change: the
route asks for `security.manage` and a passkey step-up, and the audit row carries the step-up
assertion. The credential policy on the same row (ID-07, ADR 0048) is out of R2 (D-100) and
nothing here reads or writes it.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings

from apps.identity.models import Membership, UserStatus
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.tenants.models import SecurityPolicy


def _row(tenant: Tenant) -> SecurityPolicy | None:
    return SecurityPolicy.objects.select_related("updated_by").filter(tenant=tenant).first()  # ordering: tenant is unique, at most one row


def _limits(policy: SecurityPolicy | None) -> dict[str, Any]:
    """The limits as the audit event records them: numbers or null, never a label."""
    return {
        "sessionIdleMinutes": policy.session_idle_minutes if policy else None,
        "sessionAbsoluteHours": policy.session_absolute_hours if policy else None,
    }


def policy_out(tenant: Tenant) -> dict[str, Any]:
    policy = _row(tenant)
    return {
        "session_idle_minutes": policy.session_idle_minutes if policy else None,
        "session_absolute_hours": policy.session_absolute_hours if policy else None,
        "session_idle_minutes_default": settings.SESSION_IDLE_MINUTES_DEFAULT,
        "session_idle_minutes_max": settings.SESSION_IDLE_MINUTES_MAX,
        "session_absolute_hours_default": settings.SESSION_ABSOLUTE_HOURS_DEFAULT,
        "session_absolute_hours_max": settings.SESSION_ABSOLUTE_HOURS_MAX,
        "updated_at": policy.updated_at if policy else None,
        "updated_by": {"id": policy.updated_by.id, "name": policy.updated_by.name} if policy and policy.updated_by else None,
    }


def _check_maximums(idle_minutes: int | None, absolute_hours: int | None) -> None:
    errors = []
    if idle_minutes is not None and idle_minutes > settings.SESSION_IDLE_MINUTES_MAX:
        errors.append({"field": "sessionIdleMinutes", "message": f"The idle limit can be at most {settings.SESSION_IDLE_MINUTES_MAX} minutes."})
    if absolute_hours is not None and absolute_hours > settings.SESSION_ABSOLUTE_HOURS_MAX:
        errors.append({"field": "sessionAbsoluteHours", "message": f"The session limit can be at most {settings.SESSION_ABSOLUTE_HOURS_MAX} hours."})
    if errors:
        raise ProblemError(
            status=422,
            code="above_platform_maximum",
            detail=" ".join(error["message"] for error in errors),
            errors=errors,
        )


def _other_holders(tenant: Tenant, actor: Actor) -> list[str]:
    """The bank's other active members whose roles carry `security.manage`: permissions,
    never role names. Ids only, sorted so the payload is stable; the outbox row names its
    audit event itself, so the payload does not repeat it."""
    users = (
        Membership.objects.filter(
            tenant=tenant,
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__permissions__contains=[perms.SECURITY_MANAGE],
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    return sorted(str(user_id) for user_id in users if user_id != actor.id)


def set_session_policy(
    *,
    tenant: Tenant,
    actor: Actor,
    idle_minutes: int | None,
    absolute_hours: int | None,
    step_up_assertion_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Replace the bank's session limits (null is the platform default), refusing either
    above its platform maximum. The tenant row is locked first, so two first writes at once
    queue rather than both creating the policy row."""
    _check_maximums(idle_minutes, absolute_hours)
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    policy = _row(tenant)
    before = _limits(policy)
    if policy is None:
        policy = SecurityPolicy(tenant=tenant)
    policy.session_idle_minutes = idle_minutes
    policy.session_absolute_hours = absolute_hours
    policy.updated_by_id = actor.id
    policy.save()
    record(
        action="security_policy.updated",
        actor=actor,
        subject_type="security_policy",
        subject_id=tenant.id,
        subject_title=tenant.name,
        summary="Session limits changed.",
        tenant_id=tenant.id,
        before=before,
        after=_limits(policy),
        step_up_assertion_id=step_up_assertion_id,
        payload={"subjectId": str(tenant.id), "notify": _other_holders(tenant, actor)},
    )
    return policy_out(tenant)
