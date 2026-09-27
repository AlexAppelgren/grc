"""The run log as a person reads it (AGT-01, AGT-04, ruling 9): `GET /agent-runs`, with the
chunk 11 filters and fields.

A caller reads the runs of its own zone and no other: a bank's session its own runs, a
console session the library's. bleqq's runs reach a bank as watch items and proposals,
never as run rows, so no platform cost, token count or model is on a bank's page (the
TODO default on what a bank sees of bleqq's watch). Row-level security already keeps
another bank's runs out; the zone filter narrows a bank's session further, past the library
rows security lets it read. `tenantAgentId` narrows to one of the bank's agents and `mine`
to the runs the caller asked for; neither can widen what the zone allows.
"""

from __future__ import annotations

from apps.agents import runs
from apps.agents.models import AgentRun
from apps.agents.schemas import AgentRunListItem, AgentRunListPage, TenantRunQuery
from apps.shared.authentication import Principal
from apps.taxonomy.schemas import PersonRef


def list_runs(*, who: Principal, query: TenantRunQuery) -> AgentRunListPage:
    """The runs of the caller's own zone, newest first with a stable tiebreak on id, one page
    at a time."""
    queryset = AgentRun.objects.select_related("agent", "agent_version", "requested_by").order_by("-started_at", "-id")
    if who.tenant_id is None:
        queryset = queryset.filter(tenant__isnull=True)
    else:
        queryset = queryset.filter(tenant_id=who.tenant_id)
    if query.tenant_agent_id is not None:
        queryset = queryset.filter(tenant_agent_id=query.tenant_agent_id)
    if query.mine:
        queryset = queryset.filter(requested_by_id=who.subject_id)
    return AgentRunListPage(
        items=[_item(run) for run in queryset[query.offset : query.offset + query.limit]], total=queryset.count()
    )


def _item(run: AgentRun) -> AgentRunListItem:
    requester = run.requested_by
    return AgentRunListItem.model_validate(
        {
            **runs.row(run).model_dump(),
            "tenant_agent_id": run.tenant_agent_id,
            "agent_version": run.agent_version.version_number if run.agent_version is not None else None,
            "trigger": run.trigger,
            "requested_by": PersonRef(id=requester.id, name=requester.name) if requester is not None else None,
            "cost": run.cost,
            "interrupted_at": run.interrupted_at,
        }
    )
