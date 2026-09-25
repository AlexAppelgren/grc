"""bleqq's own agents in the console (AGT-03, ADR 0053): their settings, their runs and the
fence that keeps a bank away from them.

A platform agent's cadence, the jurisdictions it sweeps and its budget live on its `agent`
row and are the same for every bank; no tenant column sits beside them and no tenant path
writes them. `refuse_platform_agent` is the fence every tenant control calls first. The
settings and the run list answer 501 `not_built` behind their routes' real gates until
`c11-platform-agent-settings` and `c11-platform-runs` fill them.
"""

from __future__ import annotations

from typing import NoReturn

from apps.agents.models import Agent, AgentScopeKind
from apps.agents.schemas import PlatformAgentSettingsInput
from apps.shared import permissions as perms
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError


def refuse_platform_agent(agent: Agent) -> None:
    """A bank steers only a definition it may add as its own: one of bleqq's agents, or a
    tenant definition not released for banks to configure, is the console's, so the 403
    names the permission that reaches it. The database refuses the row as well (agents
    0005); this is the answer a person reads."""
    if agent.scope != AgentScopeKind.TENANT.value or not agent.tenant_configurable:
        raise ProblemError(
            status=403,
            code="permission_denied",
            detail="Only bleqq changes its own agents.",
            required_permission=perms.AGENT_DEFINITIONS_MANAGE,
        )


def get_settings(*, agent_key: str) -> NoReturn:
    """`GET /agent-definitions/{agentKey}/settings`. Built by `c11-platform-agent-settings`."""
    raise ProblemError(status=501, code="not_built", detail="Reading a platform agent's settings is not built yet.")


def update_settings(*, who: Principal, agent_key: str, body: PlatformAgentSettingsInput) -> NoReturn:
    """`PUT /agent-definitions/{agentKey}/settings`. Built by `c11-platform-agent-settings`."""
    raise ProblemError(status=501, code="not_built", detail="Changing a platform agent's settings is not built yet.")


def list_runs(*, limit: int, offset: int) -> NoReturn:
    """`GET /console/agent-runs`. Built by `c11-platform-runs`."""
    raise ProblemError(status=501, code="not_built", detail="The console's platform run list is not built yet.")
