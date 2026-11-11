"""The impact assessment (CAS-03, CAS-08; D-92).

Starting it moves `assigned` to `assessing` and opens it at version 1. Saving replaces the
whole answer under the case's `If-Match` and moves nothing (the first action does,
R2_CROSS_CUTTING (j)), except `applies = no`, which closes the case on one `cases.work`
holder's word with a `not_applicable` reason (D-92), restorable to triage. Moves go through
`logic.transition()`. Audit rows carry keys, dates and the version, never the texts
(R2_CROSS_CUTTING (m)).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.cases import logic, state
from apps.cases.models import AssessmentApplies, ImpactAssessment
from apps.cases.schemas import CasesAssessmentBody, CasesCase
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.kinds import CaseStatusCategory, CloseReason
from apps.shared.models import Tenant
from apps.shared.permissions import CASES_WORK
from apps.taxonomy.models import CaseSubStatus, ClosureReason
from apps.taxonomy.tenant_lists_logic import VocabularyProblem
from apps.watch.keys import resolve_keys
from apps.cases.responses import case_response

SAVED = "case.assessment_saved"
# Spelled out, not imported, so the audit guard reads a tenant subject (tests_hardening).
SUBJECT_TYPE = "change_case"

# Where the assessment can be saved: being assessed or implemented. From sign-off on it is
# the record a second person signs.
SAVABLE = frozenset({CaseStatusCategory.ASSESSING, CaseStatusCategory.IMPLEMENTING})


def start_assessment(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None
) -> CasesCase:
    """`assigned` to `assessing`, opening an empty assessment at version 1. A restored and
    re-triaged case keeps the assessment it has. The sub-status is cleared.
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
            case.close_reason = ClosureReason.objects.filter(tenant=tenant, kind=CloseReason.NOT_APPLICABLE.value, active=True).first()  # ordering: Meta.ordering, the list's first
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
