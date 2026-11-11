"""The case as every workflow move answers it (`CasesCase`, CAS-02 to CAS-08).

One builder, so every move reports the case the same way: the people named, the bank's own
reasons labelled in the reader's language, and the moves the state machine allows for that
reader. `canRequestSignoff` is read off the same `allowed_transitions()` the request's own
guard runs, so the screen and the server never disagree (CAS-06). It reads and never writes.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from apps.cases import logic, state
from apps.cases.models import ChangeCase, ImpactAssessment
from apps.cases.schemas import CaseCategory, CasesAssessment, CasesCase, CasesVocabularyRef
from apps.library.reading import vocabulary_refs
from apps.shared.kinds import CaseStatusCategory
from apps.taxonomy.models import CaseSubStatusLabel, ClosureReasonLabel, DismissalReasonLabel, EffortSizeLabel, TeamLabel
from apps.watch.reading import urgency_refs
from apps.shared.people import person_ref


def _ref(label_model: type[Any], row: Any, order: list[str]) -> CasesVocabularyRef | None:
    """`{key, kind, label}` of one of the bank's own rows, or None when the case names none."""
    if row is None:
        return None
    ref = vocabulary_refs(label_model, [row], order)[row.id]
    return CasesVocabularyRef(key=ref.key, kind=ref.kind, label=ref.label)


def assessment_of(row: ImpactAssessment | None, order: list[str]) -> CasesAssessment | None:
    """The assessment as every case read answers it, from a row read with its effort and
    saver; one label query when it names an effort. None before the assessment starts."""
    if row is None:
        return None
    return CasesAssessment(
        applies=cast(Any, row.applies),
        why=row.why or None,
        what_must_change=row.what_must_change or None,
        internal_deadline=row.internal_deadline,
        effort=_ref(EffortSizeLabel, row.effort, order),
        saved=row.saved,
        saved_by=person_ref(row.saved_by),
        saved_at=row.saved_at,
        version=row.version,
    )


def workflow_fields(case: ChangeCase, *, reader: uuid.UUID | None, order: list[str], assessment: ImpactAssessment | None) -> dict[str, Any]:
    """What every case answer says about the workflow, `case` loaded with its joins
    (`logic.CASE_JOINS`): the people, the bank's own reasons labelled, the assessment and
    the moves the state machine allows `reader` through the facts every guard reads. Shared
    by `CasesCase` and the change page's `WatchCaseWorkflow`."""
    facts = logic.case_facts(case, actor=reader)
    allowed = state.allowed_transitions(CaseStatusCategory(case.status), facts)
    return {
        "owner": person_ref(case.owner),
        "owner_team": _ref(TeamLabel, case.owner_team, order),
        "triaged_by": person_ref(case.triaged_by),
        "triaged_at": case.triaged_at,
        "dismissed_reason": _ref(DismissalReasonLabel, case.dismissed_reason, order),
        "dismissed_by": person_ref(case.dismissed_by),
        "dismissed_at": case.dismissed_at,
        "signoff_requested_by": person_ref(case.signoff_requested_by),
        "signoff_requested_at": case.signoff_requested_at,
        "signed_off_by": person_ref(case.signed_off_by),
        "close_reason": _ref(ClosureReasonLabel, case.close_reason, order),
        "closed_note": case.closed_note or None,
        "closed_at": case.closed_at,
        "assessment": assessment_of(assessment, order),
        "open_action_count": facts.open_action_count,
        # Sign-off is asked for only from implementing, so "the machine allows the move to
        # signoff" is the whole rule; nothing here restates it.
        "can_request_signoff": CaseStatusCategory.SIGNOFF in allowed,
        "allowed_transitions": [category.value for category in allowed],
        "version": case.version,
    }


def case_response(case: ChangeCase, *, reader: uuid.UUID | None, order: list[str]) -> CasesCase:
    """`case` as `reader` sees it, with the case's joins (`logic.CASE_JOINS`) loaded."""
    assessment = ImpactAssessment.objects.select_related("effort", "saved_by").filter(case=case).first()  # ordering: one per case
    return CasesCase(
        id=case.id,
        change_id=case.change_id,
        status=cast(CaseCategory, case.status),
        sub_status=_ref(CaseSubStatusLabel, case.sub_status, order),
        urgency=urgency_refs([case.urgency_id], order)[case.urgency_id],
        urgency_confirmed=case.urgency_confirmed,
        footprint_match=case.footprint_match,
        **workflow_fields(case, reader=reader, order=order, assessment=assessment),
    )
