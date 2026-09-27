"""Actions with an owner and a due date, locked while the case waits for sign-off (CAS-04,
CAS-08).

An action is added only while a case is worked: in `assessing`, where the first one moves
the case to `implementing` through `logic.transition()` and so needs the assessment's why
saved (R2_CROSS_CUTTING (j)), or in `implementing`. From the sign-off category on, every
write is refused with `actions_locked`: what a second person signs off is what was done.
The lock reads the category, never a sub-status.

Each action is its own versioned record: an edit, a completion, a reopening and a removal
name the action's `version` in `If-Match`, and adding one names the case's. Every write
locks the case row first, so two writes to one case's actions queue behind each other and
behind its move to sign-off. A removal sets `removed_at` and `removed_by` and keeps the row
for the case file (rule l). An owner is an active member of the bank; the case's owner when
none is named.

An audit row carries ids, dates and done, never the title a person typed (rule m).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.cases import logic
from apps.cases.models import Action, ChangeCase
from apps.cases.schemas import CasesAction, CasesActionBody, CasesActionPage, CasesActionPatch
from apps.identity.models import Membership, UserStatus
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import Tenant
from apps.shared.schemas import PageQuery
from apps.taxonomy.schemas import PersonRef

SUBJECT_TYPE = "action"
ADDED = "case.action_added"
CHANGED = "case.action_changed"
REMOVED = "case.action_removed"

C = CaseStatusCategory
# Where a sign-off has been asked for or given, the actions are what it covers.
LOCKED = (C.SIGNOFF, C.CLOSED)
WORKED = (C.ASSESSING, C.IMPLEMENTING)


def list_actions(*, tenant: Tenant, change_id: uuid.UUID, page: PageQuery) -> CasesActionPage:
    """One page of the case's live actions, earliest due date first."""
    case = logic.load_case(tenant, change_id)
    live = Action.objects.select_related("owner", "done_by").filter(case=case, removed_at__isnull=True)
    rows = live[page.offset : page.offset + page.limit]
    return CasesActionPage(items=[_out(row, change_id) for row in rows], total=live.count())


def add_action(
    *, tenant: Tenant, actor: Actor, user: Any, change_id: uuid.UUID, expected_version: int | None, body: CasesActionBody
) -> tuple[int, CasesAction]:
    """A new action on the case, under the case's `If-Match`. The first moves an assessing
    case to implementing."""
    case = logic.load_case(tenant, change_id, for_update=True)
    _check_open_to_work(case)
    logic.check_version(case, expected_version)
    live = Action.objects.filter(case=case, removed_at__isnull=True).count()
    if live >= settings.CASE_ACTIONS_MAX:
        raise ProblemError(
            status=409,
            code="too_many_actions",
            detail=f"A case holds at most {settings.CASE_ACTIONS_MAX} actions. Remove one that is no longer needed first.",
        )
    owner_id = _member(tenant, body.owner_id or case.owner_id)
    if case.status == C.ASSESSING.value:
        logic.transition(case, C.IMPLEMENTING, actor=actor, user=user)
    row = Action.objects.create(
        tenant=tenant, case=case, title=body.title, owner_id=owner_id, due_date=body.due_date, created_by=user
    )
    _record(ADDED, row, actor, before={}, summary=f"{actor.label} added an action to a case.")
    return 201, _out(row, change_id)


def update_action(
    *, tenant: Tenant, actor: Actor, user: Any, action_id: uuid.UUID, expected_version: int | None, body: CasesActionPatch
) -> CasesAction:
    """Edit, complete or reopen an action, under the action's own `If-Match`."""
    row = _locked_action(tenant, action_id, expected_version)
    before = _values(row)
    if body.title is not None:
        row.title = body.title
    if body.owner_id is not None:
        row.owner_id = _member(tenant, body.owner_id)
    if body.due_date is not None:
        row.due_date = body.due_date
    if body.done is True and row.done_at is None:
        row.done_at, row.done_by = timezone.now(), user
    elif body.done is False:
        row.done_at, row.done_by = None, None
    row.version += 1
    row.save()
    _record(CHANGED, row, actor, before=before, summary=f"{actor.label} changed an action on a case.")
    return _out(row, row.case.change_id)


def delete_action(*, tenant: Tenant, actor: Actor, user: Any, action_id: uuid.UUID, expected_version: int | None) -> None:
    """Remove an action: `removed_at` and `removed_by` are set, and the row stays."""
    row = _locked_action(tenant, action_id, expected_version)
    before = _values(row)
    row.removed_at, row.removed_by = timezone.now(), user
    row.version += 1
    row.save()
    _record(REMOVED, row, actor, before=before, summary=f"{actor.label} removed an action from a case.")


# ---------------------------------------------------------------------------------------
# What the writes share
# ---------------------------------------------------------------------------------------
def _check_open_to_work(case: ChangeCase) -> None:
    """Actions change only while the case is worked; from sign-off on they are locked."""
    category = C(case.status)
    if category in LOCKED:
        raise ProblemError(
            status=409,
            code="actions_locked",
            detail="The actions are locked while the case waits for sign-off. Send it back to change them.",
        )
    if category not in WORKED:
        raise ValidationError("Start the assessment before planning actions.", code="invalid_transition")


def _locked_action(tenant: Tenant, action_id: uuid.UUID, expected_version: int | None) -> Action:
    """The live action, read again under its case's row lock, then the lock and the
    version checked. Another bank's action, and a removed one, answer 404 first."""
    action = logic.load_action(tenant, action_id)
    case = logic.load_case(tenant, action.case.change_id, for_update=True)
    row = (
        Action.objects.select_for_update(of=("self",))
        .filter(pk=action.pk, removed_at__isnull=True)
        .first()  # ordering: pk lookup, at most one row
    )
    if row is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    row.case = case
    _check_open_to_work(case)
    if expected_version is None or expected_version != row.version:
        raise logic.StaleWrite(row.version)
    return row


def _member(tenant: Tenant, user_id: uuid.UUID | None) -> uuid.UUID:
    """`user_id` when it names an active member of this bank, else 422 `unknown_member`."""
    if user_id is None or not Membership.objects.filter(
        tenant=tenant, user_id=user_id, deactivated_at__isnull=True, user__status=UserStatus.ACTIVE.value
    ).exists():
        raise ValidationError("Choose an owner who is a member of this company.", code="unknown_member")
    return user_id


def _values(row: Action) -> dict[str, Any]:
    """What an audit row may say about an action: ids, the date and whether it is done."""
    return {
        "ownerId": str(row.owner_id),
        "dueDate": row.due_date.isoformat(),
        "done": row.done_at is not None,
        "removed": row.removed_at is not None,
        "version": row.version,
    }


def _record(action: str, row: Action, actor: Actor, *, before: dict[str, Any], summary: str) -> None:
    record(
        action=action,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=row.title,
        summary=summary,
        tenant_id=row.tenant_id,
        before=before,
        after={**_values(row), "caseId": str(row.case_id)},
    )


def _person(user: Any) -> PersonRef | None:
    return None if user is None else PersonRef(id=user.id, name=user.name)


def _out(row: Action, change_id: uuid.UUID) -> CasesAction:
    return CasesAction(
        id=row.id,
        change_id=change_id,
        title=row.title,
        owner=PersonRef(id=row.owner.id, name=row.owner.name),
        due_date=row.due_date,
        done=row.done_at is not None,
        done_at=row.done_at,
        done_by=_person(row.done_by),
        created_at=row.created_at,
        version=row.version,
    )
