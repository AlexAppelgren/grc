"""The bank's teams and who is in them (TEN-03). A team is a row of the bank's `team` list,
so creating, renaming and retiring one are the `/vocab/team` routes; this module reads.
Declared ahead of its logic (chunk 8 plan rule 3): each function loads the record its route
names in the caller's bank, then answers 501 `not_built` until the teams package fills it.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy.models import Team


def team_of(tenant: Tenant, key: str) -> Team:
    """The team, active or retired, in the caller's bank and under its row-level security, or 404."""
    team = Team.objects.filter(tenant=tenant, key=key).first()  # ordering: unique (tenant, key), at most one row
    if team is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return team


def list_teams(*, tenant: Tenant, order: list[str], limit: int, offset: int) -> NoReturn:
    """`GET /tenant/teams`."""
    raise ProblemError(status=501, code="not_built", detail="Listing teams is not built yet.")


def list_team_members(*, tenant: Tenant, key: str, limit: int, offset: int) -> NoReturn:
    """`GET /tenant/teams/{key}/members`."""
    team_of(tenant, key)
    raise ProblemError(status=501, code="not_built", detail="Listing a team's members is not built yet.")
