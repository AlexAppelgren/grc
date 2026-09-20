"""Routes of the agents app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

bleqq's agents are platform-owned and platform-run (Alex, 2026-09-19, item 14), and the
gates say so: the two run writes take `ApiKeyAuth` alone, so no session — tenant or
platform — opens or closes a run, and the run log takes `SessionAuth` alone, so no key
reads it. Which key may open a run is the logic's own refusal, in `runs.py:open_run`.

Every write carries `Idempotency-Key`: an agent retries, and a retry must return the run
it already opened rather than a second one (AGT-01).
"""

import uuid
from typing import Any

from django.http import HttpRequest
from ninja import Header, Query, Router

from apps.agents import runs
from apps.agents.schemas import AgentRunFinish, AgentRunInput, AgentRunOut, AgentRunPage
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_scope
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import answers_problems, require_any

router = Router(tags=["Agents"])

KEY = ApiKeyAuth()
SESSION = SessionAuth()
IdempotencyKey = Header(None, alias="Idempotency-Key")


@router.post("/agent-runs", response={201: AgentRunOut}, auth=KEY, operation_id="startAgentRun", by_alias=True)
@requires_scope(perms.SCOPE_AGENT_RUNS_WRITE)
@answers_problems
def start_agent_run(
    request: HttpRequest, body: AgentRunInput, idempotency_key: str | None = IdempotencyKey
) -> Any:
    return runs.open_run()


@router.patch(
    "/agent-runs/{run_id}", response=AgentRunOut, auth=KEY, operation_id="finishAgentRun", by_alias=True
)
@requires_scope(perms.SCOPE_AGENT_RUNS_WRITE)
@answers_problems
def finish_agent_run(
    request: HttpRequest, run_id: uuid.UUID, body: AgentRunFinish, idempotency_key: str | None = IdempotencyKey
) -> Any:
    return runs.finish_run()


@router.get("/agent-runs", response=AgentRunPage, auth=SESSION, operation_id="listAgentRuns", by_alias=True)
@answers_problems
def list_agent_runs(request: HttpRequest, page: Query[PageQuery]) -> Any:
    # Ungated by design: logic-gate (agents.manage in a tenant, or system.health in the console).
    require_any(request, perms.AGENTS_MANAGE, perms.SYSTEM_HEALTH)
    return runs.list_runs()
