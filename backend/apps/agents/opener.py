"""The one opener every run the app starts goes through (AGT-06, ADR 0053).

It writes the run row (the version it pins, what started it, the scope it looks at and the
most it may spend) and its audit row before the runner is asked anything, and closes the
run as failed when the runner cannot start it, so no run vanishes or reads as running.

This module writes and names no library model: the definition and version a run pins
reach it as `Pinned`, keys and ids that `tasks.py` read, because the library fence refuses a
module that both names a library record and calls a write
(apps/shared/tests_library_fence.py). What it writes is a run (`agent_run`), in no tenant's
zone for one of bleqq's agents and in the bank's for one of its own, and a bank agent's
next run.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import uuid
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.agents import scope as run_scope
from apps.agents.models import AgentRun, RunStatus, RunTrigger, TenantAgent
from apps.identity.models import User
from apps.shared.adapters.agent_runner import get_agent_runner
from apps.shared.audit import Actor, record

logger = logging.getLogger(__name__)

SUBJECT_TYPE = "agent_run"
# What a run that the runner would not start says, for the people who operate the agents.
START_FAILED = "The runner could not start this run."


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


def open_run(
    *,
    pinned: Pinned,
    trigger: RunTrigger,
    actor: Actor,
    tenant_agent: TenantAgent | None = None,
    requested_by: User | None = None,
    budget_limit: Decimal | None = None,
    scope: dict[str, Any] | None = None,
) -> AgentRun:
    """Record the run, then hand it to the runner. The row and its audit row are written
    before the runner is called, in the caller's transaction."""
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
        },
    )
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
