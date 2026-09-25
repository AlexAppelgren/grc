"""Run now, pause, resume and interrupt a bank's own agent (AGT-04, AGT-06, ADR 0053).

Each control loads its record under row-level security first, so another bank's agent or
run is not found, then passes the platform fence, so one of bleqq's agents or runs is
refused naming `agent_definitions.manage`. Each writes its audit row through `record()` in
the request's transaction.

- **Run now** opens through the scheduler of record (`tasks.open_tenant_run`), which checks
  the AI switch and the cap and writes the run row before the runner is asked. A paused or
  switched-off agent is refused here first, each with its own code.
- **Pause** and **resume** change the agent's schedule and never touch a run already open.
- **Interrupt** (`stop`) asks the runner to stop the run and records it as interrupted, with
  when and by whom. The cap's second point stops a run through the same function with no
  person (`runner_events.py`).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.agents import tasks, tenant_agents
from apps.agents.models import AgentRun, RunStatus, RunTrigger
from apps.agents.platform import refuse_platform_agent, refuse_platform_run
from apps.agents.runs_read import _item as run_item
from apps.agents.schemas import AgentRunListItem
from apps.identity.models import User
from apps.shared.adapters.agent_runner import RunHandle, get_agent_runner
from apps.shared.audit import Actor, ActorType, record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

# The pause reason a person's pause carries: a key, beside the cap's `budget_cap`.
PAUSED_BY_PERSON = "person"


def _person(who: Principal) -> User:
    return User.objects.get(pk=who.subject_id)


def run_now(
    *, who: Principal, tenant: Tenant, tenant_agent_id: uuid.UUID
) -> tuple[int, AgentRunListItem]:
    """`POST /agents/{tenantAgentId}/runs`: one run now, outside the cadence."""
    with transaction.atomic():
        agent = tenant_agents.own_agent(tenant_agent_id)
        if not agent.enabled:
            raise ProblemError(
                status=409,
                code="agent_disabled",
                detail="The agent is switched off. Switch it on first.",
            )
        if agent.paused_at is not None:
            raise ProblemError(
                status=409, code="agent_paused", detail="The agent is paused. Resume it first."
            )
        run = tasks.open_tenant_run(agent, trigger=RunTrigger.MANUAL, requested_by=_person(who))
    if run is None:  # pragma: no cover - only a scheduled run is skipped without an answer
        raise AssertionError("a run a person asked for either opens or is refused")
    return 202, run_item(run)


def pause(*, who: Principal, tenant: Tenant, tenant_agent_id: uuid.UUID) -> dict[str, Any]:
    """`POST /agents/{tenantAgentId}/pause`. Pausing a paused agent changes nothing."""
    with transaction.atomic():
        agent = tenant_agents.own_agent(tenant_agent_id)
        tenant_agents.pause(agent, PAUSED_BY_PERSON, by=_person(who))
        return tenant_agents._out(agent)


def resume(*, who: Principal, tenant: Tenant, tenant_agent_id: uuid.UUID) -> dict[str, Any]:
    """`DELETE /agents/{tenantAgentId}/pause`: clear the pause and schedule the next run.
    Resuming an agent that is not paused changes nothing and records nothing."""
    with transaction.atomic():
        agent = tenant_agents.own_agent(tenant_agent_id)
        if agent.paused_at is None:
            return tenant_agents._out(agent)
        user = _person(who)
        before = {**tenant_agents._state(agent), "pauseReason": agent.pause_reason}
        agent.paused_at = None
        agent.paused_by = None
        agent.pause_reason = ""
        agent.next_run_at = tenant_agents.next_run_at(agent, tenant)
        agent.updated_by = user
        agent.save(
            update_fields=[
                "paused_at",
                "paused_by",
                "pause_reason",
                "next_run_at",
                "updated_by",
                "updated_at",
            ]
        )
        record(
            action="agents.tenant_agent_resumed",
            actor=Actor(kind=ActorType.USER, id=user.id, label=user.name),
            subject_type="tenant_agent",
            subject_id=agent.id,
            subject_title=agent.agent.key,
            summary=f"Resumed the agent {agent.agent.key}.",
            tenant_id=tenant.id,
            before=before,
            after=tenant_agents._state(agent),
        )
        return tenant_agents._out(agent)


def interrupt(*, who: Principal, tenant: Tenant, run_id: uuid.UUID) -> AgentRunListItem:
    """`POST /agent-runs/{runId}/interrupt`. Row-level security lets a bank read a library
    run, so one is found and then fenced; another bank's run is not found."""
    with transaction.atomic():
        # Read, then lock: a library run is readable from a bank's zone but never lockable
        # there, so it is found and refused by name before the lock is asked for.
        found = (
            AgentRun.objects.select_related("agent").filter(pk=run_id).first()
        )  # ordering: pk lookup
        if found is None:
            raise ProblemError(status=404, code="not_found", detail="Not found.")
        refuse_platform_run(found)
        refuse_platform_agent(found.agent)
        run = (
            AgentRun.objects.select_for_update(of=("self",)).select_related("agent").get(pk=run_id)
        )
        if run.status != RunStatus.RUNNING.value:
            raise ProblemError(
                status=409,
                code="run_finished",
                detail="The run had already finished, so nothing was stopped.",
            )
        stop(run, by=_person(who), reason=PAUSED_BY_PERSON)
    return run_item(run)


def stop(run: AgentRun, *, by: User | None, reason: str) -> None:
    """Ask the runner to stop an open run of a bank's own agent, locked by the caller, and
    record it as interrupted. `by` is the person, or None when the cap stopped it; `reason`
    is a key."""
    get_agent_runner().interrupt(
        RunHandle(
            run_id=run.id,
            external_id=run.external_session_id,
            status=RunStatus.RUNNING,
            started_at=run.started_at,
        )
    )
    run.status = RunStatus.INTERRUPTED.value
    run.finished_at = run.interrupted_at = timezone.now()
    run.interrupted_by = by
    run.save(update_fields=["status", "finished_at", "interrupted_at", "interrupted_by"])
    record(
        action="agent_run.interrupted",
        actor=Actor.system("agent_runner")
        if by is None
        else Actor(kind=ActorType.USER, id=by.id, label=by.name),
        subject_type="agent_run",
        subject_id=run.id,
        subject_title=run.agent.key,
        summary=f"Stopped a run of {run.agent.key}.",
        tenant_id=run.tenant_id,
        before={"status": RunStatus.RUNNING.value},
        after={"status": run.status, "reason": reason},
    )
