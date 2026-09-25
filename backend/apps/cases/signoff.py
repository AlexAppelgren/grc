"""Sign-off: requested by one person, approved by a second with a passkey, or sent back
(CAS-06, CAS-08).

Each move goes through `logic.transition()`, so the guards stay in `state.py`: no open
action and one piece of evidence the scanner passed before the request, and a second
person to approve. The requester's own approval is refused there before anything is
written, and the database's `change_case_four_eyes` CHECK refuses it again should that
guard ever be wrong. Signing off closes the bank's case and nothing else: no library or
register row moves, and it says nothing about whether the bank complies (REG-02).

A note is tenant content. It is kept on the case (`closed_note`) and on the transition
ledger row, never in the audit values (R2_CROSS_CUTTING (m)).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone

from apps.cases import logic, state
from apps.cases.models import ChangeCase
from apps.cases.responses import case_response
from apps.cases.schemas import CasesCase, CasesNoteBody
from apps.collab.logic import notify
from apps.collab.models import NotificationKind
from apps.identity.models import Membership, UserStatus
from apps.shared import permissions as perms
from apps.shared.audit import Actor
from apps.shared.kinds import CaseStatusCategory, CloseReason
from apps.shared.models import Tenant
from apps.taxonomy.models import ClosureReason

C = CaseStatusCategory


def _approvers(case: ChangeCase, requester: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    """The bank's active members whose roles hold `cases.signoff`, the requester left out:
    they can never sign off what they asked for. Permissions, never role names; `notify()`
    applies D-34's recipient check on top."""
    people = (
        Membership.objects.filter(
            tenant_id=case.tenant_id,
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__permissions__contains=[perms.CASES_SIGNOFF],
        )
        .exclude(user_id=requester)
        .values_list("user_id", flat=True)
        .distinct()
    )
    return [(person, "approver") for person in people]


def request_signoff(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None
) -> CasesCase:
    """`implementing` to `signoff`, with no open action and clean evidence. A refusal for
    either carries the counts beside its code, so the screen can say what is missing."""
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    case.signoff_requested_by = user
    case.signoff_requested_at = timezone.now()
    try:
        logic.transition(case, C.SIGNOFF, actor=actor, user=user)
    except state.InvalidTransition as refusal:
        if refusal.code in ("open_actions", "evidence_missing"):
            facts = logic.case_facts(case, actor=user.id)
            refusal.extra = {  # type: ignore[attr-defined]
                "openActionCount": facts.open_action_count,
                "cleanEvidenceCount": facts.clean_evidence_count,
            }
        raise
    notify(
        tenant_id=case.tenant_id,
        kind=NotificationKind.SIGNOFF_REQUESTED,
        subject_type=logic.SUBJECT_TYPE,
        subject_id=case.id,
        candidates=_approvers(case, user.id),
    )
    return case_response(case, reader=user.id, order=order)


def approve_signoff(
    *,
    tenant: Tenant,
    actor: Actor,
    user: Any,
    order: list[str],
    change_id: uuid.UUID,
    expected_version: int | None,
    body: CasesNoteBody,
    step_up_assertion_id: uuid.UUID,
) -> CasesCase:
    """`signoff` to `closed` by a second person, the step-up named on the audit row."""
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    # This is the sign-off edge only. `assigned` and `assessing` also reach `closed`, by the
    # one-person close, which is another route with its own reasons (D-92).
    if case.status != C.SIGNOFF.value:
        raise state.InvalidTransition("invalid_transition")
    case.signed_off_by = user
    case.close_reason = ClosureReason.objects.get(tenant=tenant, key=CloseReason.SIGNED_OFF.value)
    case.closed_note = body.note
    case.closed_at = timezone.now()
    logic.transition(case, C.CLOSED, actor=actor, user=user, note=body.note, step_up_assertion_id=step_up_assertion_id)
    return case_response(case, reader=user.id, order=order)


def send_back_signoff(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesNoteBody
) -> CasesCase:
    """`signoff` back to `implementing`, with the second person's note. The request columns
    are cleared, so the next request is a fresh one by whoever asks."""
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    case.signoff_requested_by = None
    case.signoff_requested_at = None
    logic.transition(case, C.IMPLEMENTING, actor=actor, user=user, note=body.note)
    return case_response(case, reader=user.id, order=order)
