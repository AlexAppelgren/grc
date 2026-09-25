"""The bank's one monthly cap on its own agents (AGT-04, ruling 3). bleqq's agents run at
bleqq's cost and no figure here includes them. Answers 501 `not_built` until
`c11-tenant-agents-budget-scope` fills it."""

from __future__ import annotations

from typing import NoReturn

from apps.agents.schemas import AgentBudgetInput
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def get_budget(*, tenant: Tenant) -> NoReturn:
    """`GET /tenant/agent-budget`. Built by `c11-tenant-agents-budget-scope`."""
    raise ProblemError(status=501, code="not_built", detail="Reading the agent budget is not built yet.")


def put_budget(*, who: Principal, tenant: Tenant, body: AgentBudgetInput) -> NoReturn:
    """`PUT /tenant/agent-budget`. Built by `c11-tenant-agents-budget-scope`."""
    raise ProblemError(status=501, code="not_built", detail="Setting the agent budget is not built yet.")
