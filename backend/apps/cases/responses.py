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
from apps.taxonomy.models import CaseSubStatusLabel, ClosureReasonLabel, DismissalReasonLabel, EffortSizeLabel
from apps.taxonomy.schemas import PersonRef
from apps.watch.reading import urgency_refs


def _person(user: Any) -> PersonRef | None:
    return None if user is None else PersonRef(id=user.id, name=user.name)


def _ref(label_model: type[Any], row: Any, order: list[str]) -> CasesVocabularyRef | None:
    """`{key, kind, label}` of one of the bank's own rows, or None when the case names none."""
    if row is None:
        return None
    ref = vocabulary_refs(label_model, [row], order)[row.id]
    return CasesVocabularyRef(key=ref.key, kind=ref.kind, label=ref.label)


def _assessment(case: ChangeCase, order: list[str]) -> CasesAssessment | None:
    found = ImpactAssessment.objects.select_related("effort", "saved_by").filter(case=case).first()  # ordering: one per case
    if found is None:
        return None
    return CasesAssessment(
        applies=cast(Any, found.applies),
        why=found.why or None,
        what_must_change=found.what_must_change or None,
        internal_deadline=found.internal_deadline,
        effort=_ref(EffortSizeLabel, found.effort, order),
        saved=found.saved,
        saved_by=_person(found.saved_by),
        saved_at=found.saved_at,
        version=found.version,
    )


def case_response(case: ChangeCase, *, reader: uuid.UUID | None, order: list[str]) -> CasesCase:
    """`case` as `reader` sees it, with the case's joins (`logic.CASE_JOINS`) loaded."""
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
        # Sign-off is asked for only from implementing, so "the machine allows the move to
        # signoff" is the whole rule; nothing here restates it.
        can_request_signoff=CaseStatusCategory.SIGNOFF in allowed,
        allowed_transitions=[category.value for category in allowed],
        version=case.version,
    )
