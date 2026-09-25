"""The run log as a person reads it (AGT-01, AGT-04, ruling 9): `GET /agent-runs`, with the
chunk 11 filters and fields.

Row-level security decides what may be seen: a bank's session reads the library's runs and
its own, a console session the library's, and no session another bank's. `tenantAgentId`
narrows to one of the bank's agents and `mine` to the runs the caller asked for; neither
can widen what security already allows.
"""

from __future__ import annotations

from apps.agents import runs
from apps.agents.models import AgentRun
from apps.agents.schemas import AgentRunListItem, AgentRunListPage, TenantRunQuery
from apps.shared.authentication import Principal
from apps.taxonomy.schemas import PersonRef


def list_runs(*, who: Principal, query: TenantRunQuery) -> AgentRunListPage:
    """The runs this caller may see, oldest first, one page at a time."""
    queryset = AgentRun.objects.select_related("agent", "agent_version", "requested_by").order_by("started_at", "id")
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
            "agent_version": run.agent_version.version_no if run.agent_version is not None else None,
            "trigger": run.trigger,
            "requested_by": PersonRef(id=requester.id, name=requester.name) if requester is not None else None,
            "cost": run.cost,
            "interrupted_at": run.interrupted_at,
        }
    )
