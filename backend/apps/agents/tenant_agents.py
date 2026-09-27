"""A bank's own agents (AGT-04, ADR 0053): added from a tenant-scoped definition, switched on
and off, given a cadence and a scope, and only ever inside the bank's own zone.

Declared ahead of its logic: listing, adding and changing answer 501 `not_built` behind
their routes' real gates until `c11-tenant-agents-budget-scope` fills them. What already
holds is the order they will keep: a record is loaded under row-level security first, so
another bank's agent is not found before anything else is said, and one of bleqq's agents
is refused by the fence before any write is attempted.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from django.core.exceptions import ValidationError

from apps.agents.models import Agent, TenantAgent
from apps.agents.platform import refuse_platform_agent
from apps.agents.schemas import TenantAgentInput, TenantAgentUpdate
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def own_agent(tenant_agent_id: uuid.UUID) -> TenantAgent:
    """The caller's bank's own agent, read under row-level security: another bank's agent
    and one that does not exist are the same 404. It is fenced before it is returned, so
    every control that starts here refuses one of bleqq's agents."""
    agent = TenantAgent.objects.select_related("agent").filter(pk=tenant_agent_id).first()  # ordering: pk lookup, at most one row
    if agent is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    refuse_platform_agent(agent.agent)
    return agent


def list_tenant_agents(*, tenant: Tenant, limit: int, offset: int) -> NoReturn:
    """`GET /agents`. Built by `c11-tenant-agents-budget-scope`."""
    raise ProblemError(status=501, code="not_built", detail="Listing the bank's own agents is not built yet.")


def create_tenant_agent(*, who: Principal, tenant: Tenant, body: TenantAgentInput) -> NoReturn:
    """`POST /agents`. The definition is named by key and fenced now; adding the row is
    built by `c11-tenant-agents-budget-scope`."""
    definition = Agent.objects.filter(key=body.agent).first()  # ordering: unique key, at most one row
    if definition is None:
        raise ValidationError("No agent definition has that key.", code="unknown_key")
    refuse_platform_agent(definition)
    raise ProblemError(status=501, code="not_built", detail="Adding an agent of the bank's own is not built yet.")


def update_tenant_agent(*, who: Principal, tenant: Tenant, tenant_agent_id: uuid.UUID, body: TenantAgentUpdate) -> NoReturn:
    """`PATCH /agents/{tenantAgentId}`. Built by `c11-tenant-agents-budget-scope`."""
    own_agent(tenant_agent_id)
    raise ProblemError(status=501, code="not_built", detail="Changing one of the bank's agents is not built yet.")
