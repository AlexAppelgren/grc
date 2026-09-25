"""Run now, pause, resume and interrupt a bank's own agent (AGT-04). Each loads its record
under row-level security and passes the platform fence first, then answers 501
`not_built` until `c11-tenant-controls-cap` fills it."""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.agents.models import AgentRun
from apps.agents.platform import refuse_platform_agent
from apps.agents.tenant_agents import own_agent
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def run_now(*, who: Principal, tenant: Tenant, tenant_agent_id: uuid.UUID) -> NoReturn:
    """`POST /agents/{tenantAgentId}/runs`. Built by `c11-tenant-controls-cap`."""
    own_agent(tenant_agent_id)
    raise ProblemError(status=501, code="not_built", detail="Running an agent now is not built yet.")


def pause(*, who: Principal, tenant: Tenant, tenant_agent_id: uuid.UUID) -> NoReturn:
    """`POST /agents/{tenantAgentId}/pause`. Built by `c11-tenant-controls-cap`."""
    own_agent(tenant_agent_id)
    raise ProblemError(status=501, code="not_built", detail="Pausing an agent is not built yet.")


def resume(*, who: Principal, tenant: Tenant, tenant_agent_id: uuid.UUID) -> NoReturn:
    """`DELETE /agents/{tenantAgentId}/pause`. Built by `c11-tenant-controls-cap`."""
    own_agent(tenant_agent_id)
    raise ProblemError(status=501, code="not_built", detail="Resuming an agent is not built yet.")


def interrupt(*, who: Principal, tenant: Tenant, run_id: uuid.UUID) -> NoReturn:
    """`POST /agent-runs/{runId}/interrupt`. A bank reads bleqq's library runs beside its
    own, so a library run is found and then fenced; another bank's run is not found.
    Built by `c11-tenant-controls-cap`."""
    run = AgentRun.objects.select_related("agent").filter(pk=run_id).first()  # ordering: pk lookup, at most one row
    if run is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    if run.tenant_id is None:
        refuse_platform_agent(run.agent)
    raise ProblemError(status=501, code="not_built", detail="Stopping a run is not built yet.")
