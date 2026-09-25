"""bleqq's own agents in the console (AGT-03, ADR 0053): their settings, their runs and the
fence that keeps a bank away from them.

A platform agent's cadence, the jurisdictions it sweeps and its budget live on its `agent`
row and are the same for every bank; no tenant column sits beside them and no tenant path
writes them. `refuse_platform_agent` is the fence every tenant control calls first.

The console changes a platform agent's settings, platform configuration (D-102, ADR 0059),
through `seeds/console.py`, the one door the library fence opens to an agent row, and reads bleqq's runs: a platform surface that
carries platform facts, so no bank's run, name or figure is on it.
"""

from __future__ import annotations

from typing import Any, cast

from django.db import transaction
from django.db.models import Count, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce

from apps.agents import definitions, runs
from apps.agents.models import Agent, AgentRun, AgentScopeKind
from apps.agents.schemas import (
    AgentRunListItem,
    AgentRunListPage,
    Cadence,
    PlatformAgentSettings,
    PlatformAgentSettingsInput,
)
from apps.agents.seeds import console
from apps.shared import permissions as perms
from apps.shared.audit import record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.taxonomy.schemas import PersonRef
from apps.watch.keys import resolve_keys


def _refused() -> ProblemError:
    return ProblemError(
        status=403,
        code="permission_denied",
        detail="Only bleqq changes its own agents.",
        required_permission=perms.AGENT_DEFINITIONS_MANAGE,
    )


def refuse_platform_agent(agent: Agent) -> None:
    """A bank steers only a definition it may add as its own: one of bleqq's agents, or a
    tenant definition not released for banks to configure, is the console's, so the 403
    names the permission that reaches it. The database refuses the row as well (agents
    0005); this is the answer a person reads."""
    if agent.scope != AgentScopeKind.TENANT.value or not agent.tenant_configurable:
        raise _refused()


def refuse_platform_run(run: AgentRun) -> None:
    """A library run (no tenant) is bleqq's whatever definition it ran: a bank reads it in
    its run log and never steers it."""
    if run.tenant_id is None:
        raise _refused()


def _platform_agent(agent_key: str, *, lock: bool = False) -> Agent:
    """One of bleqq's own agents by key. A definition a bank adds for itself has no platform
    settings, so it is not found here, as a key no definition has is not."""
    queryset = Agent.objects.select_for_update() if lock else Agent.objects.all()
    agent = queryset.filter(key=agent_key, scope=AgentScopeKind.PLATFORM.value).first()  # ordering: key is unique
    if agent is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return agent


def _settings(agent: Agent) -> PlatformAgentSettings:
    scope = agent.platform_scope or {}
    return PlatformAgentSettings(
        agent_key=agent.key,
        cadence=cast(Cadence, agent.default_cadence),
        jurisdictions=list(scope.get("jurisdictions", [])),
        monthly_budget=agent.platform_monthly_budget,
    )


def get_settings(*, agent_key: str) -> PlatformAgentSettings:
    """`GET /agent-definitions/{agentKey}/settings`: what one of bleqq's agents runs with."""
    return _settings(_platform_agent(agent_key))


def update_settings(*, who: Principal, agent_key: str, body: PlatformAgentSettingsInput) -> PlatformAgentSettings:
    """`PUT /agent-definitions/{agentKey}/settings`: the whole setting, for every bank at once.

    The jurisdictions are checked against the live list (422 `unknown_key` with the valid
    keys; a retired one is not valid) before anything is written. Nothing here reads a
    bank's row: the setting is the platform's alone."""
    actor, _ = definitions.platform_person(who)
    jurisdictions = list(dict.fromkeys(row.key for row in resolve_keys("jurisdiction", body.jurisdictions)))
    with transaction.atomic():
        agent = _platform_agent(agent_key, lock=True)
        before = _settings(agent).model_dump(mode="json", by_alias=True, exclude={"agent_key"})
        console.set_platform_settings(
            agent, cadence=body.cadence, jurisdictions=jurisdictions, monthly_budget=body.monthly_budget
        )
        after = _settings(agent)
        record(
            action="agent.settings_changed",
            actor=actor,
            subject_type="agent",
            subject_id=agent.id,
            subject_title=agent.key,
            summary=f"Settings of agent {agent.key} changed for every bank.",
            tenant_id=None,
            before=before,
            after=after.model_dump(mode="json", by_alias=True, exclude={"agent_key"}),
            step_up_assertion_id=who.step_up_assertion_id,
        )
    return after


def _counted(queryset: QuerySet[Any], column: str, run: str = "agent_run_id") -> Coalesce:
    """How many distinct `column` values of the rows of `queryset` whose `run` names the
    outer run, as a subquery, so a page of runs is counted in the page's own query rather
    than once per run."""
    counts = queryset.filter(**{run: OuterRef("pk")}).order_by().values(run).annotate(n=Count(column, distinct=True))
    return Coalesce(Subquery(counts.values("n")[:1]), 0)


def list_runs(*, limit: int, offset: int) -> AgentRunListPage:
    """`GET /console/agent-runs`: bleqq's own runs, newest first, one page at a time.

    What each run filed is counted from the rows it filed, the source checks of the
    coverage log included (H41), over what the run reported of itself. A bank's run is
    never here, and no row carries a bank."""
    from apps.proposals.models import Proposal
    from apps.watch.models import RegulatoryChange, SourceCheck, SourceCheckKind

    platform = AgentRun.objects.filter(tenant__isnull=True)
    page = (
        platform.select_related("agent", "agent_version", "requested_by")
        .annotate(
            counted_sources=_counted(SourceCheck.objects.filter(kind=SourceCheckKind.SWEEP.value), "source"),
            counted_rechecks=_counted(SourceCheck.objects.filter(kind=SourceCheckKind.RECHECK.value), "subject_id"),
            counted_changes=_counted(RegulatoryChange.objects.all(), "id"),
            counted_proposals=_counted(Proposal.objects.all(), "id"),
        )
        .order_by("-started_at", "-id")[offset : offset + limit]
    )
    return AgentRunListPage(items=[_run(run) for run in page], total=platform.count())


def _run(run: Any) -> AgentRunListItem:
    row = runs.row(run).model_dump()
    requester = run.requested_by
    return AgentRunListItem.model_validate(
        {
            **row,
            "stats": {
                **row["stats"],
                "sources_checked": run.counted_sources,
                "records_rechecked": run.counted_rechecks,
                "changes_registered": run.counted_changes,
                "proposals_submitted": run.counted_proposals,
            },
            "tenant_agent_id": None,
            "agent_version": run.agent_version.version_no if run.agent_version is not None else None,
            "trigger": run.trigger,
            "requested_by": PersonRef(id=requester.id, name=requester.name) if requester is not None else None,
            "cost": run.cost,
            "interrupted_at": run.interrupted_at,
        }
    )
