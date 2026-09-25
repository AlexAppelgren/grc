"""Removing a member who owns open work (TEN-05, TEN-03, COL-04, CAS-02, CAS-04, REG-07;
TEN-S5, TEN-S9, TEN-S3).

`owned_work()` is the one read of what a person holds, by kind, straight off the ownership
columns: the register entries they are the first-line owner or the compliance contact of,
the legal entities' rows, the gaps not closed, the open duty occurrences, the active internal
items, the cases not closed or dismissed and the actions neither done nor removed. The
preview counts it, the plain removal refuses while any of it is left, and the removal moves
it; My work reads the same service (D-23).

The removal names one new owner per kind, a person or a team. Every row moves, the member's
own participations end with a stamp and their team memberships end, and the membership is
deactivated through `members_logic.deactivate_member()`, all in one transaction under the
removal's step-up: one audit event per item and one for the removal. What a team owns or
takes part in is never touched, which is how ownership survives a person leaving (TEN-03).
A case and an action always have a person as owner, so they pass to a person and never to a
team; a case passes only to someone who may work it, and a team named beside its owner stays
(`c9-owner-team-and-reassign`).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Model, Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.cases.models import Action, ChangeCase
from apps.collab.models import Participant
from apps.identity import members_logic
from apps.identity.models import Membership
from apps.library.reading import obligation_headings
from apps.register.duties import OPEN as OPEN_DUTY
from apps.register.models import DutyOccurrence, Gap, TenantObligation, TenantObligationScope
from apps.shared import permissions as perms
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import Tenant
from apps.taxonomy.models import GapCategory, Team
from apps.tenants.models import InternalItem, TeamMember
from apps.tenants.schemas import TenantMemberRemoveBody, TenantRemovalOwner

PARTICIPATION = "participation"
TEAM_MEMBERSHIP = "team_membership"
# The kinds whose owner is always a person: the database requires one on a worked case and
# on every action, so a team can stand beside the owner of a case but never replace it.
PERSON_ONLY = frozenset({"case", "action"})
CLOSED_CASE = (CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value)


def owned_work(tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, QuerySet[Any]]:
    """What `user_id` owns in the bank, by the kind a removal moves to a new owner."""
    return {
        "register_entry": TenantObligation.objects.filter(
            Q(first_line_owner_id=user_id) | Q(compliance_contact_id=user_id), tenant_id=tenant_id
        ),
        "register_entity": TenantObligationScope.objects.filter(tenant_id=tenant_id, owner_id=user_id).select_related("tenant_obligation"),
        "gap": Gap.objects.filter(tenant_id=tenant_id, owner_id=user_id).exclude(status__kind=GapCategory.CLOSED.value),
        "duty_occurrence": DutyOccurrence.objects.filter(tenant_id=tenant_id, owner_id=user_id, status__in=OPEN_DUTY).select_related("recurring_duty"),
        "internal_item": InternalItem.objects.filter(tenant_id=tenant_id, owner_user_id=user_id, active=True),
        "case": ChangeCase.objects.filter(tenant_id=tenant_id, owner_id=user_id)
        .exclude(status__in=CLOSED_CASE)
        .select_related("change"),
        "action": Action.objects.filter(tenant_id=tenant_id, owner_id=user_id, done_at__isnull=True, removed_at__isnull=True),
    }


def _ending(tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, QuerySet[Any]]:
    """What a removal ends rather than moves: the person's own participations and teams."""
    return {
        PARTICIPATION: Participant.objects.filter(tenant_id=tenant_id, user_id=user_id, removed_at__isnull=True),
        TEAM_MEMBERSHIP: TeamMember.objects.filter(tenant_id=tenant_id, user_id=user_id),
    }


def open_work_counts(tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """One `{kind, count}` per kind the person holds, in the contract's kind order."""
    kinds = {**owned_work(tenant_id, user_id), **_ending(tenant_id, user_id)}
    counts = [{"kind": kind, "count": rows.count()} for kind, rows in kinds.items()]
    return [row for row in counts if row["count"]]


def reassignment_required(counts: list[dict[str, Any]]) -> ProblemError:
    return ProblemError(
        status=422,
        code="reassignment_required",
        detail="This member still holds work. Name a new owner for each kind before removing them.",
        errors=[{"field": row["kind"], "count": row["count"], "message": "Needs a new owner or ends with the removal."} for row in counts],
    )


def open_work(*, tenant: Tenant, user_id: uuid.UUID) -> dict[str, Any]:
    """`GET /tenant/members/{userId}/open-work`: counts only, and nothing is written."""
    membership = members_logic.membership_of(tenant.id, user_id)
    return {
        "member": {"id": membership.user_id, "name": membership.user.name},
        "items": open_work_counts(tenant.id, user_id),
        "teams": members_logic.team_keys(tenant.id, [user_id])[user_id],
    }


# ---------------------------------------------------------------------------------------
# The removal
# ---------------------------------------------------------------------------------------
Target = tuple[uuid.UUID | None, Team | None]


def _targets(tenant: Tenant, user_id: uuid.UUID, owners: list[TenantRemovalOwner]) -> dict[str, Target]:
    """Each named kind's new owner, checked: another active member of the bank, or an active
    team of it. Another bank's person or team is the same answer as one that never existed."""
    kinds = [owner.kind for owner in owners]
    if len(set(kinds)) != len(kinds):
        raise ValidationError("Name each kind of work once.", code="validation_error")
    people = {owner.user_id for owner in owners if owner.user_id is not None}
    active = set(
        Membership.objects.filter(tenant=tenant, user_id__in=people, deactivated_at__isnull=True)
        .exclude(user_id=user_id)
        .values_list("user_id", flat=True)
    )
    if people - active:
        raise ValidationError("A new owner must be another current member of this bank.", code="unknown_member")
    if any(owner.team_key is not None for owner in owners if owner.kind in PERSON_ONLY):
        raise ValidationError("Cases and actions pass to a person, never to a team.", code="validation_error")
    case_owner = next((owner.user_id for owner in owners if owner.kind == "case"), None)
    if case_owner is not None and not Membership.objects.filter(
        tenant=tenant, user_id=case_owner, roles__permissions__contains=[perms.CASES_WORK]
    ).exists():
        raise ValidationError("A case's new owner must be a member who works cases.", code="unknown_member")
    keys = {owner.team_key for owner in owners if owner.team_key is not None}
    teams = {team.key: team for team in Team.objects.filter(tenant=tenant, key__in=keys, active=True)}
    if keys - set(teams):
        raise ValidationError("That is not one of this bank's teams.", code="unknown_key")
    return {owner.kind: (owner.user_id, teams.get(owner.team_key or "")) for owner in owners}


# The owner columns of each kind, as the audit shows them, and its audit subject.
_OWNER_FIELDS = {
    "register_entry": ("first_line_owner", "compliance_contact", "owner_team"),
    "register_entity": ("owner", "owner_team"),
    "gap": ("owner", "owner_team"),
    "duty_occurrence": ("owner", "owner_team"),
    "internal_item": ("owner_user", "owner_team"),
    "case": ("owner", "owner_team"),
    "action": ("owner",),
}
_SUBJECT_TYPE = {
    "register_entry": "tenant_obligation",
    "register_entity": "tenant_obligation_scope",
    "gap": "gap",
    "duty_occurrence": "duty_occurrence",
    "internal_item": "internal_item",
    "case": "change_case",
    "action": "action",
}


def _owner_ids(kind: str, row: Model) -> dict[str, str | None]:
    """The owner columns of `row` for the audit, as camelCase ids."""
    out = {}
    for field in _OWNER_FIELDS[kind]:
        value = getattr(row, f"{field}_id")
        head, *rest = field.split("_")
        out[head + "".join(part.title() for part in rest) + "Id"] = None if value is None else str(value)
    return out


def _new_owner(kind: str, row: Model, user_id: uuid.UUID, target: Target) -> dict[str, Any]:
    """The columns that hand `row` to its new owner. A row owned by a person or a team, never
    both, passes to exactly one of them. On a register entry, the person columns the member
    held pass to the new person; to a team, the entry's owner becomes the team and those
    person columns are cleared, because a compliance contact is always a person (D-1xx,
    c8-ten-reassignment)."""
    person, team = target
    if kind == "register_entry":
        held = [field for field in ("first_line_owner", "compliance_contact") if getattr(row, f"{field}_id") == user_id]
        if team is not None:
            return {"owner_team": team, **{f"{field}_id": None for field in held}}
        return {f"{field}_id": person for field in held}
    if kind in PERSON_ONLY:
        # The team beside a case's owner is the team's and stays (TEN-S3).
        return {"owner_id": person}
    person_field = "owner_user" if kind == "internal_item" else "owner"
    return {f"{person_field}_id": person, "owner_team": team}


def _title(kind: str, row: Any, headings: dict[uuid.UUID, Any]) -> str:
    if kind in ("gap", "internal_item"):
        return str(row)
    if kind == "case":
        return row.change.title
    if kind == "action":
        return row.title
    if kind == "duty_occurrence":
        return row.recurring_duty.title
    obligation_id = row.obligation_id if kind == "register_entry" else row.tenant_obligation.obligation_id
    heading = headings.get(obligation_id)
    return "" if heading is None else f"{heading.instrument_short_name}, {heading.reference_label}"


def remove_member(
    *,
    tenant: Tenant,
    actor: Actor,
    user_id: uuid.UUID,
    body: TenantMemberRemoveBody,
    step_up_assertion_id: uuid.UUID,
    request: HttpRequest | None,
) -> None:
    """`POST /tenant/members/{userId}/remove`. Every check is made before the first write,
    and the writes run in one savepoint, so a refusal anywhere leaves nothing changed."""
    membership = (
        Membership.objects.select_for_update(of=("self",))
        .select_related("user")
        .filter(tenant=tenant, user_id=user_id, deactivated_at__isnull=True)
        .first()
    )  # ordering: unique (tenant, user), at most one row
    if membership is None:
        raise ValidationError("Not found.", code="not_found")
    targets = _targets(tenant, user_id, body.owners)
    owned = owned_work(tenant.id, user_id)
    missing = [row for row in open_work_counts(tenant.id, user_id) if row["kind"] in owned and row["kind"] not in targets]
    if missing:
        raise reassignment_required(missing)

    obligation_ids = list(owned["register_entry"].values_list("obligation_id", flat=True))
    obligation_ids += owned["register_entity"].values_list("tenant_obligation__obligation_id", flat=True)
    headings = obligation_headings(obligation_ids, [])
    with transaction.atomic():
        for kind, rows in owned.items():
            if kind not in targets:
                continue
            for row in rows.select_for_update(of=("self",)).order_by("id"):
                before = _owner_ids(kind, row)
                values = _new_owner(kind, row, user_id, targets[kind])
                if hasattr(row, "version"):
                    values["version"] = F("version") + 1
                type(row).objects.filter(pk=row.pk).update(**values)
                row.refresh_from_db()
                record(
                    action=f"{kind}.reassigned",
                    subject_type=_SUBJECT_TYPE[kind],
                    subject_id=row.pk,
                    subject_title=_title(kind, row, headings),
                    summary=f"Reassigned on the removal of {membership.user.name}.",
                    before=before,
                    after=_owner_ids(kind, row),
                    actor=actor,
                    tenant_id=tenant.id,
                    step_up_assertion_id=step_up_assertion_id,
                )
        _end_participations(tenant, membership, actor, step_up_assertion_id)
        _end_team_memberships(tenant, membership, actor, step_up_assertion_id)
        members_logic.deactivate_member(tenant=tenant, actor=actor, user_id=user_id, request=request, step_up_assertion_id=step_up_assertion_id)


def _end_participations(tenant: Tenant, membership: Membership, actor: Actor, step_up_assertion_id: uuid.UUID) -> None:
    """The member's own participations are stamped removed, never deleted (COL-04); a team's
    participation is the team's and is left alone."""
    now = timezone.now()
    for row in _ending(tenant.id, membership.user_id)[PARTICIPATION].select_for_update(of=("self",)).order_by("id"):
        row.removed_at, row.removed_by_id = now, actor.id
        row.save(update_fields=["removed_at", "removed_by"])
        record(
            action="participant.removed",
            subject_type="participant",
            subject_id=row.id,
            subject_title=membership.user.name,
            summary="Participation ended with the member's removal.",
            after={"participantId": str(row.id), "tenantObligationId": _str(row.tenant_obligation_id), "caseId": _str(row.case_id)},
            actor=actor,
            tenant_id=tenant.id,
            step_up_assertion_id=step_up_assertion_id,
        )


def _end_team_memberships(tenant: Tenant, membership: Membership, actor: Actor, step_up_assertion_id: uuid.UUID) -> None:
    """The member leaves every team; what each team owns stays the team's (TEN-S3)."""
    for row in _ending(tenant.id, membership.user_id)[TEAM_MEMBERSHIP].select_related("team").order_by("id"):
        row.delete()
        record(
            action="team_member.removed",
            subject_type="team",
            subject_id=row.team_id,
            subject_title=row.team.key,
            before={"userId": str(membership.user_id)},
            summary=f"{membership.user.name} left the team with their removal.",
            after={"userId": None},
            actor=actor,
            tenant_id=tenant.id,
            step_up_assertion_id=step_up_assertion_id,
        )


def _str(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)
