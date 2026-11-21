"""The one opener every run the app starts goes through (AGT-06, ADR 0053).

It writes the run row (pinned version, trigger, scope, budget) and its audit row before the
runner is asked anything, and closes the run as failed when the runner cannot start it, so
no run vanishes or reads as running. It names no library model: `tasks.py` hands it a
`Pinned` of keys and ids (library fence).
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.agents import scope as run_scope
from apps.agents.models import AgentRun, ResearchRequest, RunStatus, RunTrigger, TenantAgent
from apps.identity.models import User
from apps.shared import tenancy
from apps.shared.adapters.agent_runner import RunHandle, get_agent_runner
from apps.shared.audit import Actor, batched, record

logger = logging.getLogger(__name__)

SUBJECT_TYPE = "agent_run"
# What a run that the runner would not start says, for the people who operate the agents.
START_FAILED = "The runner could not start this run."
# What a run that never reported its end says once the beat closes it.
OVERDUE = "The run did not report back in time, so it was closed as failed."


@dataclasses.dataclass(frozen=True)
class Pinned:
    """The definition and version a run pins: keys and ids only (rule n)."""

    agent_id: uuid.UUID
    key: str
    version_id: uuid.UUID | None
    version_no: int
    model: str


def schedule_of(tenant_agent: TenantAgent | None) -> dict[str, Any]:
    """What the audit row of a bank's run carries of the agent's schedule, which the beat
    moved just before: the agent and its next run, an id and a timestamp."""
    if tenant_agent is None:
        return {}
    upcoming = tenant_agent.next_run_at
    return {"tenantAgent": str(tenant_agent.id), "nextRunAt": upcoming.isoformat() if upcoming else None}


@batched()
def open_run(
    *,
    pinned: Pinned,
    trigger: RunTrigger,
    actor: Actor,
    tenant_agent: TenantAgent | None = None,
    requested_by: User | None = None,
    budget_limit: Decimal | None = None,
    scope: dict[str, Any] | None = None,
    research_request: ResearchRequest | None = None,
    hand_over: bool = True,
) -> AgentRun:
    """Record the run, then hand it to the runner, in the caller's transaction.
    `hand_over=False` records a run the caller runs itself, the library baseline's command
    (D-118)."""
    run = AgentRun.objects.create(
        agent_id=pinned.agent_id,
        agent_version_id=pinned.version_id,
        tenant_agent=tenant_agent,
        trigger=trigger.value,
        requested_by=requested_by,
        model=pinned.model,
        pipeline_version=str(pinned.version_no),
        budget_limit=budget_limit,
        scope=scope or {},
        research_request=research_request,
    )
    if tenant_agent is not None:
        run_scope.snapshot(run)
    record(
        action="agent_run.opened",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=run.id,
        subject_title=pinned.key,
        summary=f"{pinned.key} opened a run.",
        tenant_id=run.tenant_id,
        after={
            "agent": pinned.key,
            "agentVersion": pinned.version_no,
            "trigger": run.trigger,
            "budgetLimit": None if budget_limit is None else str(budget_limit),
            "scope": run.scope,
            **schedule_of(tenant_agent),
            **({"researchRequest": str(research_request.id)} if research_request is not None else {}),
        },
    )
    if hand_over:
        _hand_over(run, pinned, actor)
    return run


def _hand_over(run: AgentRun, pinned: Pinned, actor: Actor) -> None:
    """Start the recorded run through the runner. Whatever the runner raises, the run is
    closed as failed with a fixed sentence, so no run is left reading as running."""
    try:
        handle = get_agent_runner().start(run_id=run.id, definition_key=pinned.key, definition_version=pinned.version_no)
    except Exception:  # compliance: allow-broad-except the runner is an external executor; any failure to start closes the recorded run as failed
        logger.warning("agent run not started", extra={"run_id": str(run.id), "agent": pinned.key})
        run.status = RunStatus.FAILED.value
        run.error = START_FAILED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        record(
            action="agent_run.start_failed",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=run.id,
            subject_title=pinned.key,
            summary=f"The runner could not start {pinned.key}'s run.",
            tenant_id=run.tenant_id,
            before={"status": RunStatus.RUNNING.value},
            after={"status": run.status},
        )
        return
    run.external_session_id = handle.external_id
    run.save(update_fields=["external_session_id"])
    record(
        action="agent_run.started",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=run.id,
        subject_title=pinned.key,
        summary=f"The runner started {pinned.key}'s run.",
        tenant_id=run.tenant_id,
        after={"externalSessionId": handle.external_id},
    )


def take_slot(tenant_agent: TenantAgent, upcoming: datetime.datetime | None) -> None:
    """Move a bank agent's next run on before its run opens, so a slot is taken once
    whatever happens to the run."""
    tenant_agent.next_run_at = upcoming
    tenant_agent.save(update_fields=["next_run_at", "updated_at"])


def close_overdue(now: datetime.datetime) -> int:
    """Close as failed every run of the caller's zone still running `AGENT_RUN_MAX_MINUTES`
    after it started, asking the runner to stop it first, and say how many. A run whose
    runner died or never reports would otherwise read as running for ever and, for a bank's
    own agent, hold its budget limit against the cap (defect 4 of the agent review,
    2026-11-21). Each beat calls it in its own zone before it opens anything; a run another
    worker holds is left for the next beat."""
    cutoff = now - datetime.timedelta(minutes=settings.AGENT_RUN_MAX_MINUTES)
    zone = tenancy.active_tenant_id()
    overdue = (
        AgentRun.objects.select_for_update(of=("self",), skip_locked=True)
        .select_related("agent")
        .filter(Q(tenant__isnull=True) if zone is None else Q(tenant_id=zone), status=RunStatus.RUNNING.value, started_at__lt=cutoff)
        .order_by("started_at", "id")
    )
    closed = 0
    for run in overdue:
        try:
            get_agent_runner().interrupt(
                RunHandle(run_id=run.id, external_id=run.external_session_id, status=RunStatus.RUNNING, started_at=run.started_at)
            )
        except Exception:  # compliance: allow-broad-except the runner is an external executor; a run it cannot stop is still closed here
            logger.warning("overdue agent run not stopped by the runner", extra={"run_id": str(run.id), "agent": run.agent.key})
        run.status = RunStatus.FAILED.value
        run.error = OVERDUE
        run.finished_at = now
        run.save(update_fields=["status", "error", "finished_at"])
        record(
            action="agent_run.overdue",
            actor=Actor.system("agent scheduler"),
            subject_type=SUBJECT_TYPE,
            subject_id=run.id,
            subject_title=run.agent.key,
            summary=f"{run.agent.key}'s run did not report back in time and was closed as failed.",
            tenant_id=run.tenant_id,
            before={"status": RunStatus.RUNNING.value},
            after={"status": run.status, "maxMinutes": settings.AGENT_RUN_MAX_MINUTES},
        )
        closed += 1
    return closed
