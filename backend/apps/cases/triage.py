"""Triage, dismissal, restore, starting the assessment and the one-person close
(CAS-02, CAS-03, VOC-06; D-92).

Every function loads the caller's case under a row lock, so another bank's case answers 404,
checks `If-Match`, sets what its move supplies and moves the case through
`logic.transition()`, which asks the state machine, writes the ledger row and the audit row,
and raises the version. The answer is the whole case as `case_out()` builds it, with the
moves the state machine allows the reader next.

A key a person sends is resolved against the list it names and refused with 422
`unknown_key` and the list's valid keys: urgencies from the library's list, dismissal and
close reasons and sub-statuses from the bank's own lists, never another bank's. The owner a
triage names must be an active member of the bank who works cases, and is told through
`notify()`, whose one recipient check (D-34) decides who hears; nothing here adds a rule.

The one-person close is Alex's answer to q-case-close, "One person, audited" (D-92, ADR
0060): a reason of the `no_action` or `not_applicable` kind closes an assigned or assessing
case on one person's word; a `signed_off` reason is refused by the state machine and goes
through sign-off and a second person. The note stays on the case and its ledger row and
never reaches an audit value. Restore undoes a dismissal or a one-person close and never a
signed-off one, which the state machine decides.

`start_assessment` is published ahead of its logic and answers 501 `not_built` until
`c9-assessment` builds it.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from django.utils import timezone

from apps.cases import logic, state
from apps.cases.models import ChangeCase, ImpactAssessment
from apps.cases.schemas import AssessmentApplies, CaseCategory, CasesAssessment, CasesCase, CasesCloseBody, CasesReasonBody, CasesTriageBody, CasesVocabularyRef
from apps.collab.logic import notify
from apps.collab.models import NotificationKind
from apps.identity.models import Membership, UserStatus
from apps.library.reading import vocabulary_refs
from apps.shared import permissions as perms
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import Tenant
from apps.taxonomy.models import CaseSubStatusLabel, ClosureReasonLabel, DismissalReasonLabel, EffortSizeLabel
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.schemas import PersonRef
from apps.taxonomy.tenant_lists_logic import VocabularyProblem
from apps.watch.reading import urgency_refs

C = CaseStatusCategory

# The categories a case closes from on one person's word (D-92).
ONE_PERSON_CLOSE_FROM = frozenset({C.ASSIGNED.value, C.ASSESSING.value})

NOT_BUILT = "This part of the case workflow is not available yet."


# ---------------------------------------------------------------------------------------
# What a move is given
# ---------------------------------------------------------------------------------------
def _row(list_name: str, key: str, *, tenant: Tenant, kind: CaseStatusCategory | None = None) -> Any:
    """The active row `key` names in `list_name`, or 422 `unknown_key` with the valid keys.

    A bank's own list is read for this bank only, beside row-level security. `kind` narrows
    a sub-status list to the category the case is moving into, so a sub-status of another
    category is a key this move may not store.
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


# ---------------------------------------------------------------------------------------
# The answer
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
        applies=cast(AssessmentApplies, row.applies),
        why=row.why or None,
        what_must_change=row.what_must_change or None,
        internal_deadline=row.internal_deadline,
        effort=_ref(EffortSizeLabel, row.effort, order),
        saved=row.saved,
        saved_by=_person(row.saved_by),
        saved_at=row.saved_at,
        version=row.version,
    )


def case_out(case: ChangeCase, *, reader: uuid.UUID | None, order: list[str]) -> CasesCase:
    """The whole case as every workflow move answers it, with the moves the state machine
    allows `reader` next (CAS-08)."""
    facts = logic.case_facts(case, actor=reader)
    allowed = state.allowed_transitions(C(case.status), facts)
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
        # Sign-off is asked for only from implementing, so the machine allowing the move is the whole rule.
        can_request_signoff=C.SIGNOFF in allowed,
        allowed_transitions=[category.value for category in allowed],
        version=case.version,
    )


# ---------------------------------------------------------------------------------------
# The moves
# ---------------------------------------------------------------------------------------
def triage_change(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesTriageBody
) -> CasesCase:
    """`new` to `assigned`, with a confirmed urgency and an owner, who is told (CAS-02)."""
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    case.urgency = _row("urgency", body.urgency, tenant=tenant)
    case.urgency_confirmed = True
    case.owner = _owner(tenant, body.owner_id)
    case.sub_status = None if body.sub_status is None else _row("case_sub_status", body.sub_status, tenant=tenant, kind=C.ASSIGNED)
    case.triaged_by = user
    case.triaged_at = timezone.now()
    logic.transition(case, C.ASSIGNED, actor=actor, user=user, audit={"ownerId": str(case.owner.id), "urgency": case.urgency.key})
    notify(
        tenant_id=tenant.id,
        kind=NotificationKind.ASSIGNED,
        subject_type=logic.SUBJECT_TYPE,
        subject_id=case.id,
        candidates=[(case.owner.id, "owner")],
    )
    return case_out(case, reader=user.id, order=order)


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
    return case_out(case, reader=user.id, order=order)


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
    return case_out(case, reader=user.id, order=order)


def start_assessment(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None
) -> CasesCase:
    """`assigned` to `assessing`, opening an empty assessment (CAS-03)."""
    logic.load_case(tenant, change_id, for_update=True)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def close_without_action(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, expected_version: int | None, body: CasesCloseBody
) -> CasesCase:
    """`assigned` or `assessing` to `closed` on one person's word, audited (D-92). The
    note is kept on the case and its ledger row, never in the audit values.

    Only from the two categories a one-person close leaves: the machine also draws
    `signoff` to `closed`, and that edge is sign-off's, whose guard reads the requester and
    not the reason, so this route must never reach it."""
    case = logic.load_case(tenant, change_id, for_update=True)
    logic.check_version(case, expected_version)
    if case.status not in ONE_PERSON_CLOSE_FROM:
        raise state.InvalidTransition("invalid_transition")
    case.close_reason = _row("close_reason", body.reason_key, tenant=tenant)
    case.closed_note = body.note
    case.closed_at = timezone.now()
    case.sub_status = None
    logic.transition(case, C.CLOSED, actor=actor, user=user, note=body.note, audit={"reasonKey": case.close_reason.key})
    return case_out(case, reader=user.id, order=order)
