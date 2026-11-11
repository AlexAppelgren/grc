"""Triage, dismissal, restore, starting the assessment and the one-person close (CAS-02,
CAS-03, VOC-06; D-92).

Each function loads the case under a row lock (another bank's is 404), checks `If-Match`,
sets what its move supplies and calls `logic.transition()`. A key is resolved against its
list (library urgencies, the bank's own reasons and sub-statuses), else 422 `unknown_key`.
A triage owner must be an active member who works cases, told through `notify()` (D-34).

The one-person close (D-92, ADR 0060): a `no_action` or `not_applicable` reason closes an
assigned or assessing case; a `signed_off` reason goes through sign-off. The note stays on the
case and ledger row. Restore undoes a dismissal or one-person close, never a sign-off.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone

from apps.cases import logic, state
from apps.cases.schemas import CasesCase, CasesCloseBody, CasesReasonBody, CasesTriageBody
from apps.collab.logic import notify
from apps.collab.models import NotificationKind
from apps.identity.models import Membership, UserStatus
from apps.shared import permissions as perms
from apps.shared.audit import Actor
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import Tenant
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.tenant_lists_logic import VocabularyProblem
from apps.cases.responses import case_response

C = CaseStatusCategory

# The categories a case closes from on one person's word (D-92).
ONE_PERSON_CLOSE_FROM = frozenset({C.ASSIGNED.value, C.ASSESSING.value})

# --- What a move is given ---
def _row(list_name: str, key: str, *, tenant: Tenant, kind: CaseStatusCategory | None = None) -> Any:
    """The active row `key` names in `list_name`, or 422 `unknown_key` with the valid keys.
    A bank list is read for this bank only; `kind` narrows a sub-status list to the target
    category.
    """
    entry = REGISTRY[list_name]
    rows = entry.model._default_manager.filter(active=True)
    if not entry.is_library:
        rows = rows.filter(tenant=tenant)
    if kind is not None:
        rows = rows.filter(kind=kind.value)
    found = rows.filter(key=key).first()  # ordering: unique key per list, at most one row
    if found is None:
        valid = list(rows.order_by(*(entry.model._meta.ordering or ("key",))).values_list("key", flat=True))
        raise VocabularyProblem(
            f"Not a {list_name} key: {key}. Valid keys: {', '.join(valid)}.",
            code="unknown_key",
            extra={"vocabulary": list_name, "validKeys": valid},
        )
    return found


def _owner(tenant: Tenant, owner_id: uuid.UUID) -> Any:
    """The person a triage names, when they are an active member of this bank whose roles
    work a case; anyone else is refused as no owner at all."""
    membership = (
        Membership.objects.select_related("user")
        .filter(
            tenant=tenant,
            user_id=owner_id,
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__permissions__contains=[perms.CASES_WORK],
        )
        .first()  # ordering: unique (tenant, user), at most one membership
    )
    if membership is None:
        raise state.InvalidTransition("owner_required")
    return membership.user


# --- The moves ---
def triage_change(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesTriageBody
) -> CasesCase:
    """`new` to `assigned`, with a confirmed urgency and an owner, who is told, and
    optionally a team of the bank beside the owner (CAS-02, TEN-03)."""
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    case.urgency = _row("urgency", body.urgency, tenant=tenant)
    case.urgency_confirmed = True
    case.owner = _owner(tenant, body.owner_id)
    case.owner_team = None if body.owner_team is None else _row("team", body.owner_team, tenant=tenant)
    case.sub_status = None if body.sub_status is None else _row("case_sub_status", body.sub_status, tenant=tenant, kind=C.ASSIGNED)
    case.triaged_by = user
    case.triaged_at = timezone.now()
    audit = {"ownerId": str(case.owner.id), "urgency": case.urgency.key}
    if case.owner_team is not None:
        audit["ownerTeam"] = case.owner_team.key
    logic.transition(case, C.ASSIGNED, actor=actor, user=user, audit=audit)
    notify(
        tenant_id=tenant.id,
        kind=NotificationKind.ASSIGNED,
        subject_type=logic.SUBJECT_TYPE,
        subject_id=case.id,
        candidates=[(case.owner.id, "owner")],
        actor_id=user.id,
    )
    return case_response(case, reader=user.id, order=order)


def dismiss_change(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesReasonBody
) -> CasesCase:
    """`new` to `dismissed`, with a reason from the bank's list (CAS-02, VOC-06)."""
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    case.dismissed_reason = _row("dismissal_reason", body.reason_key, tenant=tenant)
    case.dismissed_by = user
    case.dismissed_at = timezone.now()
    case.sub_status = None
    logic.transition(case, C.DISMISSED, actor=actor, user=user, audit={"reasonKey": case.dismissed_reason.key})
    return case_response(case, reader=user.id, order=order)


def restore_change(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None
) -> CasesCase:
    """`dismissed`, or a one-person close, back to `new` (CAS-02). The state machine reads
    the close reason, so the decision is cleared only once the move is allowed; the ledger
    and the audit trail keep it."""
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    logic.transition(case, C.NEW, actor=actor, user=user)
    case.dismissed_reason = case.dismissed_by = case.dismissed_at = None
    case.close_reason = case.closed_at = case.sub_status = None
    case.closed_note = ""
    case.save(
        update_fields=["dismissed_reason", "dismissed_by", "dismissed_at", "close_reason", "closed_at", "closed_note", "sub_status", "updated_at"]
    )
    return case_response(case, reader=user.id, order=order)


def close_without_action(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesCloseBody
) -> CasesCase:
    """`assigned` or `assessing` to `closed` on one person's word, audited (D-92); the note
    stays on the case and ledger row. Never from `signoff`: that edge is sign-off's, whose
    guard reads the requester rather than the reason."""
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    if case.status not in ONE_PERSON_CLOSE_FROM:
        raise state.InvalidTransition("invalid_transition")
    case.close_reason = _row("close_reason", body.reason_key, tenant=tenant)
    case.closed_note = body.note
    case.closed_at = timezone.now()
    case.sub_status = None
    logic.transition(case, C.CLOSED, actor=actor, user=user, note=body.note, audit={"reasonKey": case.close_reason.key})
    return case_response(case, reader=user.id, order=order)
