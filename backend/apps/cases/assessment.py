"""The impact assessment (CAS-03, CAS-08; D-92).

Starting it is a move, `assigned` to `assessing`, that opens the assessment at version 1.
Saving it replaces the bank's whole answer under the case's `If-Match` and moves the case
nowhere: adding the first action does that (R2_CROSS_CUTTING (j)). The one exception is
`applies = no`, which closes the case on one person's word with the bank's reason of the
`not_applicable` kind (D-92), restorable to triage; only a holder of `cases.work` may, so
the route, gated by `cases.contribute`, says whether the caller holds it.

Both writes go through `logic.load_case()` and `logic.check_version()`, and every move
through `logic.transition()`. The texts are tenant content: the audit row carries keys,
dates and the version, never the why or what must change (R2_CROSS_CUTTING (m)).
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from apps.cases import logic, state
from apps.cases.models import AssessmentApplies, ChangeCase, ImpactAssessment
from apps.cases.schemas import AssessmentApplies as AssessmentAppliesValue
from apps.cases.schemas import CaseCategory, CasesAssessment, CasesAssessmentBody, CasesCase, CasesVocabularyRef
from apps.library.reading import vocabulary_refs
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.kinds import CaseStatusCategory, CloseReason
from apps.shared.models import Tenant
from apps.shared.permissions import CASES_WORK
from apps.taxonomy.models import CaseSubStatus, CaseSubStatusLabel, ClosureReason, ClosureReasonLabel, DismissalReasonLabel, EffortSizeLabel
from apps.taxonomy.schemas import PersonRef
from apps.taxonomy.tenant_lists_logic import VocabularyProblem
from apps.watch.keys import resolve_keys
from apps.watch.reading import urgency_refs

SAVED = "case.assessment_saved"
# Spelled out, not imported, so the audit guard reads a tenant subject (tests_hardening).
SUBJECT_TYPE = "change_case"

# Where the assessment is open for saving: being assessed, or being implemented while
# the bank refines its answer. Before the start there is none; from sign-off on it is
# the record a second person signs.
SAVABLE = frozenset({CaseStatusCategory.ASSESSING, CaseStatusCategory.IMPLEMENTING})


def start_assessment(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None
) -> CasesCase:
    """`assigned` to `assessing`, opening an empty assessment at version 1.

    A case restored and triaged again opens the assessment it already has: nothing is
    overwritten. The sub-status is cleared, because it sat inside the category the case
    leaves.
    """
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    case.sub_status = None
    with transaction.atomic():
        logic.transition(case, CaseStatusCategory.ASSESSING, actor=actor, user=user)
        ImpactAssessment.objects.get_or_create(case=case, defaults={"tenant_id": case.tenant_id})
    return case_response(case, reader=user.id, order=order)


def save_assessment(
    *,
    tenant: Tenant,
    actor: Actor,
    user: Any,
    order: list[str],
    change_id: uuid.UUID,
    expected_version: int | None,
    body: CasesAssessmentBody,
    may_close: bool,
) -> CasesCase:
    """The whole assessment, replacing what was saved, under the case's `If-Match`.
    `may_close` says whether the caller holds `cases.work`, which `applies = no` needs."""
    case = logic.load_case(tenant, change_id, for_update=True)
    closes = body.applies == AssessmentApplies.NO.value
    if closes and not may_close:
        raise ProblemError(
            status=403,
            code="permission_denied",
            detail="Only someone who works the case can close it as not applicable.",
            required_permission=CASES_WORK,
        )
    logic.check_version(case, expected_version)
    if CaseStatusCategory(case.status) not in SAVABLE:
        raise state.InvalidTransition("invalid_transition")
    ending_in = CaseStatusCategory.CLOSED if closes else CaseStatusCategory(case.status)
    effort = resolve_keys("effort_size", [body.effort])[0] if body.effort else None
    case.sub_status = _sub_status(body.sub_status, ending_in) if body.sub_status else None

    with transaction.atomic():
        assessment = ImpactAssessment.objects.select_for_update().get(case=case)
        assessment.applies = body.applies
        assessment.why = body.why
        assessment.what_must_change = body.what_must_change
        assessment.internal_deadline = body.internal_deadline
        assessment.effort = effort
        assessment.saved = True
        assessment.saved_by = user
        assessment.saved_at = timezone.now()
        assessment.version += 1
        assessment.save()
        if closes:
            case.close_reason = ClosureReason.objects.filter(kind=CloseReason.NOT_APPLICABLE.value, active=True).first()  # ordering: Meta.ordering, the list's first
            case.closed_at = timezone.now()
            logic.transition(case, CaseStatusCategory.CLOSED, actor=actor, user=user)
        else:
            case.version += 1
            case.save()
        record(
            action=SAVED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=case.id,
            subject_title=case.change.title,
            summary=f"{actor.label} saved the impact assessment.",
            tenant_id=case.tenant_id,
            after={
                "applies": assessment.applies,
                "internalDeadline": None if assessment.internal_deadline is None else assessment.internal_deadline.isoformat(),
                "effort": None if effort is None else effort.key,
                "subStatus": None if case.sub_status is None else case.sub_status.key,
                "closeReason": case.close_reason.key if closes and case.close_reason else None,
                "version": case.version,
            },
        )
    return case_response(case, reader=user.id, order=order)


def _sub_status(key: str, category: CaseStatusCategory) -> CaseSubStatus:
    """The bank's active sub-status `key` inside `category`, or 422 `unknown_key` listing
    the keys that category holds: a sub-status of another category is not one this case
    can carry."""
    rows = CaseSubStatus.objects.filter(kind=category.value, active=True).order_by("sort_order", "key")
    found = next((row for row in rows if row.key == key), None)
    if found is None:
        valid = [row.key for row in rows]
        raise VocabularyProblem(
            f"Not a case_sub_status key of {category.value}: {key}. Valid keys: {', '.join(valid)}.",
            code="unknown_key",
            extra={"vocabulary": "case_sub_status", "validKeys": valid},
        )
    return found


# ---------------------------------------------------------------------------------------
# The response
# ---------------------------------------------------------------------------------------
def _person(user: Any) -> PersonRef | None:
    return None if user is None else PersonRef(id=user.id, name=user.name)


def _ref(label_model: type[Any], row: Any, order: list[str]) -> CasesVocabularyRef | None:
    if row is None:
        return None
    ref = vocabulary_refs(label_model, [row], order)[row.id]
    return CasesVocabularyRef(key=ref.key, kind=ref.kind, label=ref.label)


def _assessment(case: ChangeCase, order: list[str]) -> CasesAssessment | None:
    row = ImpactAssessment.objects.select_related("effort", "saved_by").filter(case=case).first()  # ordering: one per case
    if row is None:
        return None
    return CasesAssessment(
        applies=cast(AssessmentAppliesValue, row.applies),
        why=row.why or None,
        what_must_change=row.what_must_change or None,
        internal_deadline=row.internal_deadline,
        effort=_ref(EffortSizeLabel, row.effort, order),
        saved=row.saved,
        saved_by=_person(row.saved_by),
        saved_at=row.saved_at,
        version=row.version,
    )


def case_response(case: ChangeCase, *, reader: uuid.UUID, order: list[str]) -> CasesCase:
    """The case as a workflow write answers it, with the moves open to `reader` from the
    state machine through the same facts every guard reads."""
    facts = logic.case_facts(case, actor=reader)
    allowed = state.allowed_transitions(CaseStatusCategory(case.status), facts)
    return CasesCase(
        id=case.id,
        change_id=case.change_id,
        status=cast(CaseCategory, case.status),
        sub_status=_ref(CaseSubStatusLabel, case.sub_status, order),
        urgency=urgency_refs([case.urgency_id], order)[case.urgency_id],
        urgency_confirmed=case.urgency_confirmed,
        footprint_match=case.footprint_match,
        owner=_person(case.owner),
        triaged_by=_person(case.triaged_by),
        triaged_at=case.triaged_at,
        dismissed_reason=_ref(DismissalReasonLabel, case.dismissed_reason, order),
        dismissed_by=_person(case.dismissed_by),
        dismissed_at=case.dismissed_at,
        signoff_requested_by=_person(case.signoff_requested_by),
        signoff_requested_at=case.signoff_requested_at,
        signed_off_by=_person(case.signed_off_by),
        close_reason=_ref(ClosureReasonLabel, case.close_reason, order),
        closed_note=case.closed_note or None,
        closed_at=case.closed_at,
        assessment=_assessment(case, order),
        open_action_count=facts.open_action_count,
        can_request_signoff=CaseStatusCategory.SIGNOFF in allowed,
        allowed_transitions=[category.value for category in allowed],
        version=case.version,
    )
