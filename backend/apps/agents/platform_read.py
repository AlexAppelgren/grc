"""What bleqq watches, as any member of a bank reads it (AGT-03): each platform agent's key,
purpose, jurisdictions, cadence, next run and how its last library run ended, and nothing
else (no prompt, tool, budget, run row or cost). Library rows only; a bank's own run of the
same definition is filtered out. `name` is the stable key; the screen renders the words.
"""

from __future__ import annotations

import datetime
from typing import Literal, cast

from django.db.models import Exists, OuterRef
from django.utils.timezone import now as clock

from apps.agents.models import Agent, AgentCadence, AgentRun, AgentScopeKind, AgentVersion, RunStatus
from apps.agents.schemas import Cadence, PlatformWatchItem, PlatformWatchLastRun, PlatformWatchPage

# What each cadence word means as a span (as `watch/sources.py:CADENCE`); `manual` has none.
_SPAN = {
    AgentCadence.DAILY.value: datetime.timedelta(days=1),
    AgentCadence.WEEKLY.value: datetime.timedelta(days=7),
    AgentCadence.MONTHLY.value: datetime.timedelta(days=30),
}


def list_platform_watch(*, limit: int, offset: int) -> PlatformWatchPage:
    """`GET /agents/platform`: bleqq's active agents by key, one page at a time, the same for
    every bank. A definition whose current version is retired is not running and not listed."""
    retired = AgentVersion.objects.filter(
        agent=OuterRef("pk"), version_number=OuterRef("current_version"), retired_at__isnull=False
    )
    queryset = (
        Agent.objects.filter(scope=AgentScopeKind.PLATFORM.value, active=True)
        .exclude(Exists(retired))
        .order_by("key", "id")
    )
    agents = list(queryset[offset : offset + limit])
    last_runs = {
        run.agent_id: run
        for run in AgentRun.objects.filter(agent__in=agents, tenant__isnull=True)
        .order_by("agent_id", "-started_at", "-id")
        .distinct("agent_id")
    }
    now = clock()
    return PlatformWatchPage(
        items=[_item(agent, last_runs.get(agent.id), now) for agent in agents], total=queryset.count()
    )


def _item(agent: Agent, last: AgentRun | None, now: datetime.datetime) -> PlatformWatchItem:
    scope = agent.platform_scope or {}
    return PlatformWatchItem(
        key=agent.key,
        name=agent.key,
        purpose=agent.description,
        jurisdictions=scope.get("jurisdictions", []),
        # The columns hold kinds the schema publishes; the casts state what the choices fix.
        cadence=cast(Cadence, agent.default_cadence),
        next_run_at=_next_run(agent.default_cadence, last, now),
        last_run=(
            PlatformWatchLastRun(finished_at=last.finished_at, status=_status(last.status))
            if last is not None
            else None
        ),
    )


def _status(status: str) -> Literal["running", "succeeded", "failed"]:
    """A run stopped from outside reads to a bank as one that stopped early: `failed`."""
    return "failed" if status == RunStatus.INTERRUPTED.value else cast(Literal["running", "succeeded", "failed"], status)


def _next_run(cadence: str, last: AgentRun | None, now: datetime.datetime) -> datetime.datetime | None:
    """A cadence after the last start; due now when it never ran or is overdue; none for manual."""
    span = _SPAN.get(cadence)
    if span is None:
        return None
    if last is None:
        return now
    return max(last.started_at + span, now)
