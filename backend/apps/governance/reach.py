"""Tenant reach (ACC-08, D-72, ADR 0057): whether a bank's own register may reach the agents
it runs itself.

It is an egress decision about the bank's confidential judgement, so it carries the four
eyes that exports and tenant exit carry: one person holding `security.manage` requests it
and a different one approves it, each with a fresh passkey assertion. The check here answers
409 `four_eyes_violation`; the `tenant_reach_request_four_eyes` check constraint is the
database's word on it. Switching it off needs one person and takes effect from the next
read, because it is the lever a security function reaches for at three in the morning.

`tenant_reach_on(tenant)` is the one question the register reads for an agent access
credential ask, before any entry's own toggle counts. No state row reads as off."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.governance.models import TenantReach, TenantReachRequest
from apps.governance.schemas import TenantReachRequestRow, TenantReachView
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.taxonomy.models import ApprovalStatus
from apps.taxonomy.schemas import PersonRef

SUBJECT_TYPE = "tenant_reach"
REQUEST_SUBJECT_TYPE = "tenant_reach_request"
TITLE = "Tenant reach"


def tenant_reach_on(tenant_id: uuid.UUID) -> bool:
    """True once a second person approved reach and nobody has switched it off since. Reads
    under row-level security, so the tenant must be activated."""
    return TenantReach.objects.filter(tenant_id=tenant_id, enabled=True).exists()


def _person(user: Any) -> PersonRef | None:
    return None if user is None else PersonRef(id=user.id, name=user.name)


def request_row(request: TenantReachRequest) -> TenantReachRequestRow:
    return TenantReachRequestRow(
        id=request.id,
        status=request.status,  # type: ignore[arg-type]
        requested_by=PersonRef(id=request.requested_by.id, name=request.requested_by.name),
        requested_at=request.requested_at,
        decided_by=_person(request.decided_by),
        decided_at=request.decided_at,
        version=request.version,
    )


def view(tenant_id: uuid.UUID) -> TenantReachView:
    state = TenantReach.objects.filter(tenant_id=tenant_id).select_related("changed_by").first()  # ordering: one row per tenant, by constraint
    waiting = pending(tenant_id)
    return TenantReachView(
        enabled=bool(state and state.enabled),
        changed_by=_person(state.changed_by if state else None),
        changed_at=state.changed_at if state else None,
        pending=request_row(waiting) if waiting else None,
    )


def pending(tenant_id: uuid.UUID) -> TenantReachRequest | None:
    return (
        TenantReachRequest.objects.filter(tenant_id=tenant_id, status=ApprovalStatus.PENDING.value)
        .select_related("requested_by", "decided_by")
        .first()  # ordering: at most one pending row per tenant, by constraint
    )


def _locked_state(tenant: Tenant) -> TenantReach:
    """The state row, created off on first use, locked so two switches queue on it."""
    TenantReach.objects.get_or_create(tenant=tenant)
    return TenantReach.objects.select_for_update().get(tenant=tenant)


def request_reach(*, tenant: Tenant, requester: Any, actor: Actor, step_up_assertion_id: uuid.UUID) -> TenantReachRequest:
    """One pending request per bank (409 `request_pending`, from the partial unique
    constraint), and none while reach is already on (409 `invalid_transition`)."""
    if _locked_state(tenant).enabled:
        raise ValidationError("Tenant reach is already on.", code="invalid_transition")
    try:
        with transaction.atomic():
            request = TenantReachRequest.objects.create(tenant=tenant, requested_by=requester)
    except IntegrityError as exc:
        diag = getattr(exc.__cause__, "diag", None)
        if getattr(diag, "constraint_name", None) != "tenant_reach_request_one_pending":
            raise
        raise ValidationError("A request for tenant reach is already waiting for a decision.", code="request_pending") from exc
    record(
        action="tenant_reach.requested",
        actor=actor,
        subject_type=REQUEST_SUBJECT_TYPE,
        subject_id=request.id,
        subject_title=TITLE,
        summary="Asked to let the register reach the bank's own agents.",
        tenant_id=tenant.id,
        after={"status": request.status, "requestedBy": str(requester.id)},
        step_up_assertion_id=step_up_assertion_id,
    )
    return request


def _decidable(request: TenantReachRequest, decider: Any, expected_version: int | None) -> None:
    """Lock the row, then check status, version and four eyes under the lock, so two
    decisions queue and the second reads what the first committed."""
    request.refresh_from_db(from_queryset=TenantReachRequest.objects.select_for_update())
    if request.status != ApprovalStatus.PENDING.value:
        raise ValidationError("This request for tenant reach has already been decided.", code="invalid_transition")
    if expected_version is not None and expected_version != request.version:
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")
    if request.requested_by_id == decider.id:
        raise ValidationError(
            "Tenant reach is decided by someone other than the person who asked for it.", code="four_eyes_violation"
        )


def approve(
    *,
    tenant: Tenant,
    request: TenantReachRequest,
    decider: Any,
    actor: Actor,
    step_up_assertion_id: uuid.UUID,
    expected_version: int | None = None,
) -> TenantReachRequest:
    """The second person's approval: reach is on in the same transaction."""
    _decidable(request, decider, expected_version)
    state = _locked_state(tenant)
    _decide(request, decider, ApprovalStatus.APPROVED)
    state.enabled = True
    state.request = request
    state.changed_by = decider
    state.changed_at = request.decided_at
    state.save(update_fields=["enabled", "request", "changed_by", "changed_at"])
    _record_decision(tenant, request, actor, "tenant_reach.approved", step_up_assertion_id)
    return request


def reject(
    *,
    tenant: Tenant,
    request: TenantReachRequest,
    decider: Any,
    actor: Actor,
    step_up_assertion_id: uuid.UUID,
    expected_version: int | None = None,
) -> TenantReachRequest:
    """The second person's refusal: reach stays off and the request is final."""
    _decidable(request, decider, expected_version)
    _decide(request, decider, ApprovalStatus.REJECTED)
    _record_decision(tenant, request, actor, "tenant_reach.rejected", step_up_assertion_id)
    return request


def switch_off(*, tenant: Tenant, user: Any, actor: Actor, step_up_assertion_id: uuid.UUID) -> TenantReach:
    """Off for every entry from the next read, whatever each entry's own toggle says."""
    state = _locked_state(tenant)
    if not state.enabled:
        raise ValidationError("Tenant reach is already off.", code="invalid_transition")
    state.enabled = False
    state.changed_by = user
    state.changed_at = timezone.now()
    state.save(update_fields=["enabled", "changed_by", "changed_at"])
    record(
        action="tenant_reach.switched_off",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=state.id,
        subject_title=TITLE,
        summary="Switched tenant reach off for every agent access entry.",
        tenant_id=tenant.id,
        before={"enabled": True},
        after={"enabled": False, "changedBy": str(user.id)},
        step_up_assertion_id=step_up_assertion_id,
    )
    return state


def _decide(request: TenantReachRequest, decider: Any, status: ApprovalStatus) -> None:
    request.status = status.value
    request.decided_by = decider
    request.decided_at = timezone.now()
    request.version += 1
    request.save(update_fields=["status", "decided_by", "decided_at", "version"])


def _record_decision(tenant: Tenant, request: TenantReachRequest, actor: Actor, action: str, step_up_assertion_id: uuid.UUID) -> None:
    record(
        action=action,
        actor=actor,
        subject_type=REQUEST_SUBJECT_TYPE,
        subject_id=request.id,
        subject_title=TITLE,
        summary=f"Tenant reach request {request.status}.",
        tenant_id=tenant.id,
        before={"status": ApprovalStatus.PENDING.value, "version": request.version - 1},
        after={
            "status": request.status,
            "version": request.version,
            "requestedBy": str(request.requested_by_id),
            "decidedBy": str(request.decided_by_id),
        },
        step_up_assertion_id=step_up_assertion_id,
    )
