"""The bank's teams and who is in them (TEN-03). A team is a row of the bank's `team` list,
so creating, renaming, retiring and putting one in a department are the `/vocab/team`
routes (`department_id` checks the department they name), and putting a person in
a team is the member's own route (`identity.members_logic.set_member_teams`); this module
reads. Only a current member counts as in a team: a deactivated member's rows stay until
their removal ends them, and are never counted or listed here.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Count, Q, QuerySet

from apps.identity.models import Membership, User
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.vocabulary import label_for
from apps.taxonomy.models import Team
from apps.tenants.models import DEPARTMENT_KINDS, OrgUnit, TeamMember


def team_of(tenant: Tenant, key: str) -> Team:
    """The team, active or retired, in the caller's bank and under its row-level security, or 404."""
    team = Team.objects.filter(tenant=tenant, key=key).first()  # ordering: unique (tenant, key), at most one row
    if team is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return team


def department_id(tenant_id: uuid.UUID, value: Any) -> uuid.UUID | None:
    """The department a team is put in, from `extra.orgUnitId` on the team list's create and
    edit (TEN-02, D-21): an active business area, business unit or function of the caller's
    bank. A unit the bank does not have answers 404, like reaching for it by URL; a group, a
    legal entity or a deactivated department 422. None takes the team out of its department."""
    if value is None:
        return None
    try:
        unit_id = uuid.UUID(str(value))
    except ValueError as exc:
        raise ValidationError("orgUnitId: Choose a department of your organisation.", code="validation_error") from exc
    unit = OrgUnit.objects.filter(tenant_id=tenant_id, pk=unit_id).first()  # ordering: pk lookup, at most one row
    if unit is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    if unit.kind not in DEPARTMENT_KINDS or not unit.active:
        raise ValidationError("orgUnitId: A team sits in an active department, never in a group or a legal entity.", code="validation_error")
    return unit.pk


def _current_members(tenant: Tenant) -> QuerySet[Membership]:
    return Membership.objects.filter(tenant=tenant, deactivated_at__isnull=True)


def list_teams(*, tenant: Tenant, order: list[str], limit: int, offset: int) -> dict[str, Any]:
    """`GET /tenant/teams`: active and retired, in the list's order, each with its current members counted."""
    current = TeamMember.objects.filter(tenant=tenant, user_id__in=_current_members(tenant).values("user_id"))
    queryset = (
        Team.objects.filter(tenant=tenant)
        .prefetch_related("labels")
        .annotate(member_count=Count("members", filter=Q(members__in=current)))
        .order_by("sort_order", "key")
    )
    items = [
        {
            "key": team.key,
            "label": label_for(team, order),
            "org_unit_id": team.org_unit_id,
            "email": team.email,
            "member_count": team.member_count,
            "active": team.active,
        }
        for team in queryset[offset : offset + limit]
    ]
    return {"items": items, "total": queryset.count()}


def list_team_members(*, tenant: Tenant, key: str, limit: int, offset: int) -> dict[str, Any]:
    """`GET /tenant/teams/{key}/members`: the team's current members by name, ids and names only."""
    team = team_of(tenant, key)
    queryset = User.objects.filter(
        id__in=TeamMember.objects.filter(tenant=tenant, team=team).values("user_id"),
    ).filter(id__in=_current_members(tenant).values("user_id")).order_by("name", "id")
    items = [{"id": person.id, "name": person.name} for person in queryset[offset : offset + limit]]
    return {"items": items, "total": queryset.count()}
