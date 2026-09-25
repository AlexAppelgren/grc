"""What every case workflow module shares (CAS-02 to CAS-08): finding the caller's case,
`If-Match`, the facts the guards read, and the one way a case changes category.

Nothing else lives here. Each route's own logic is in its own module — `triage.py`,
`assessment.py`, `actions.py`, `evidence.py`, `signoff.py`, `case_file.py` — and every
one of them loads its case through `load_case()` and moves it through `transition()`.

A case is addressed by its change (CHUNK9 ruling 1): a bank has exactly one case per
change, so the change id names it. An action or a piece of evidence is addressed by its
own id and loads its case the same way. Every loader filters by the caller's tenant as
well as leaving it to row-level security, and a change nobody has a case for, a case of
another bank and a removed child all answer the same 404, so no id can be probed
(playbook 4.4).

The state machine decides; this module only feeds it. `case_facts()` reads what the
guards need in one query for any number of cases, from live actions that are not done
and live evidence the scanner passed, and `transition()` asks `state.check_transition()`
before it writes. No transition table is restated here or anywhere else (CHUNK9 rule 11).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from apps.cases import state
from apps.cases.models import Action, CaseTransition, ChangeCase, Evidence, ImpactAssessment
from apps.shared.adapters.scanner import ScanState
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.kinds import CaseStatusCategory, CloseReason
from apps.shared.models import Tenant

SUBJECT_TYPE = "change_case"
MOVED = "case.moved"

# What a workflow read and write joins beside the case, so naming the people and the
# reasons costs no query of its own.
CASE_JOINS = (
    "change",
    "urgency",
    "sub_status",
    "owner",
    "triaged_by",
    "dismissed_reason",
    "dismissed_by",
    "signoff_requested_by",
    "signed_off_by",
    "close_reason",
)


def _not_found() -> ProblemError:
    return ProblemError(status=404, code="not_found", detail="Not found.")


# ---------------------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------------------
def load_case(tenant: Tenant, change_id: uuid.UUID, *, for_update: bool = False) -> ChangeCase:
    """This bank's case for that change, or 404. `for_update` locks the row until the
    request's transaction ends, so two writes to one case queue and the second reads what
    the first committed."""
    queryset = ChangeCase.objects.select_related(*CASE_JOINS).filter(tenant=tenant, change_id=change_id)
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    case = queryset.first()  # ordering: unique (tenant, change), at most one row
    if case is None:
        raise _not_found()
    return case


def load_action(tenant: Tenant, action_id: uuid.UUID) -> Action:
    """One live action of this bank, its case beside it, or 404. A removed action answers
    404 as well: it stays in the case file and is never edited again."""
    action = (
        Action.objects.select_related("case")
        .filter(tenant=tenant, pk=action_id, removed_at__isnull=True)
        .first()  # ordering: pk lookup, at most one row
    )
    if action is None:
        raise _not_found()
    return action


def load_evidence(tenant: Tenant, evidence_id: uuid.UUID) -> Evidence:
    """One live piece of this bank's evidence, its case beside it, or 404."""
    evidence = (
        Evidence.objects.select_related("case")
        .filter(tenant=tenant, pk=evidence_id, removed_at__isnull=True)
        .first()  # ordering: pk lookup, at most one row
    )
    if evidence is None:
        raise _not_found()
    return evidence


# ---------------------------------------------------------------------------------------
# If-Match
# ---------------------------------------------------------------------------------------
class StaleWrite(ValidationError):
    """`If-Match` missing or older than the case: 409 `stale_write`, carrying the current
    version so the screen can reload and say what changed (CAS-08, INPUT_DELTAS §4)."""

    def __init__(self, current_version: int) -> None:
        super().__init__("Someone changed this case first. Reload it and try again.", code="stale_write")
        self.extra = {"currentVersion": current_version}


def check_version(case: ChangeCase, expected: int | None) -> None:
    """Every case write names the version it read. No `If-Match` is refused like a stale
    one: a write that did not say what it read cannot say it read the latest."""
    if expected is None or expected != case.version:
        raise StaleWrite(case.version)


# ---------------------------------------------------------------------------------------
# What the guards read
# ---------------------------------------------------------------------------------------
def _count(queryset: Any) -> Coalesce:
    return Coalesce(
        Subquery(queryset.order_by().values("case_id").annotate(n=Count("pk")).values("n"), output_field=IntegerField()),
        Value(0),
    )


def _close_reason_kind(case: ChangeCase) -> CloseReason | None:
    """The fixed kind of the close reason the case carries or its close chooses."""
    reason = case.close_reason
    return None if reason is None or not reason.kind else CloseReason(reason.kind)


def case_facts_for(cases: Sequence[ChangeCase], *, actor: uuid.UUID | None) -> dict[uuid.UUID, state.CaseFacts]:
    """The guards' facts for each case, keyed by case id, from one query however many
    cases there are (NFR-02). `actor` is the person reading or moving: the sign-off guard
    compares them with whoever asked.

    What a move supplies — the owner a triage names, the reason a dismissal or a close
    gives — is read off the case as the caller has set it in memory, before
    `transition()` saves it; a read has set nothing, and `allowed_transitions()` does not
    test those guards.
    """
    if not cases:
        return {}
    counted = {
        row["id"]: row
        for row in ChangeCase.objects.filter(pk__in=[case.id for case in cases])
        .order_by()
        .annotate(
            open_actions=_count(Action.objects.filter(case=OuterRef("pk"), done_at__isnull=True, removed_at__isnull=True)),
            clean_evidence=_count(
                Evidence.objects.filter(case=OuterRef("pk"), removed_at__isnull=True, scan_state=ScanState.CLEAN.value)
            ),
            why_saved=Exists(ImpactAssessment.objects.filter(case=OuterRef("pk"), saved=True)),
        )
        .values("id", "open_actions", "clean_evidence", "why_saved")
    }
    return {
        case.id: state.CaseFacts(
            owner_set=case.owner_id is not None,
            reason_given=case.dismissed_reason_id is not None,
            why_saved=counted[case.id]["why_saved"],
            open_action_count=counted[case.id]["open_actions"],
            clean_evidence_count=counted[case.id]["clean_evidence"],
            signoff_requester=case.signoff_requested_by_id,
            actor=actor,
            close_reason_kind=_close_reason_kind(case),
        )
        for case in cases
    }


def case_facts(case: ChangeCase, *, actor: uuid.UUID | None) -> state.CaseFacts:
    """The guards' facts for one case, in one query."""
    return case_facts_for([case], actor=actor)[case.id]


# ---------------------------------------------------------------------------------------
# The one way a case changes category
# ---------------------------------------------------------------------------------------
def transition(
    case: ChangeCase,
    to_status: CaseStatusCategory,
    *,
    actor: Actor,
    user: Any,
    note: str = "",
    step_up_assertion_id: uuid.UUID | None = None,
    audit: dict[str, str] | None = None,
) -> CaseTransition:
    """Move `case` to `to_status` if the state machine allows it, or raise its refusal.

    The caller sets what its move changes on the case first (the owner, a reason, the
    sign-off names); this saves those fields with the new category and a raised
    `version`, and writes the `case_transition` row and the `record()` row, all in one
    transaction (CAS-08). A refusal writes nothing. The note is tenant content, so it is
    kept on the ledger row and never in the audit values (R2_CROSS_CUTTING (m)); `audit`
    adds the ids and keys the move names (an owner, a reason's key) to the audit row's after.
    A move made with a passkey step-up names the assertion on its audit row (AC-ID3).
    """
    from_status = CaseStatusCategory(case.status)
    state.check_transition(from_status, to_status, case_facts(case, actor=None if user is None else user.id))
    with transaction.atomic():
        case.status = to_status.value
        case.version += 1
        case.save()
        moved = CaseTransition.objects.create(
            tenant_id=case.tenant_id,
            case=case,
            from_status=from_status.value,
            to_status=to_status.value,
            by_user=user,
            note=note,
        )
        record(
            action=MOVED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=case.id,
            subject_title=case.change.title,
            summary=f"{actor.label} moved a case from {from_status.value} to {to_status.value}.",
            tenant_id=case.tenant_id,
            before={"status": from_status.value},
            after={"status": to_status.value, "version": case.version, **(audit or {})},
            step_up_assertion_id=step_up_assertion_id,
        )
    return moved
