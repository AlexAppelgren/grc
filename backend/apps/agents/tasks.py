"""The app is the scheduler of record (AGT-03, AGT-04, AGT-06, D-61, ADR 0053).

Every run the app starts opens through one opener: `open_platform_run` for one of bleqq's
agents and `open_tenant_run` for one a bank added for itself, both ending in `_open`, which
writes the run row (the version it pins, what started it, the scope it looks at and the
most it may spend) and its audit row before the runner is asked anything. A runner that
cannot start a run leaves it recorded as failed, never as a row that vanished or one still
running.

Two beats, because the two kinds of agent live in two zones:

- **bleqq's beat** (`run_platform_agents`) is not a `@tenant_task`. A platform run has no
  tenant, activates none and reads no tenant row or setting: not a bank's AI switch, not
  its cap, not a pause, and never `scope.py`, which reads a bank's markets. Its scope is
  the agent's own `platform_scope`, or every jurisdiction the library covers. An agent is
  due once per calendar period of its cadence (the UTC day, week from Monday, or month),
  and one beat starts at most `AGENT_RUNS_PER_BEAT`, the longest-waiting first, so one
  beat never starts the whole library at once.
- **A bank's beat** (`schedule_tenant_agents`) hands each active bank to
  `run_due_tenant_agents`, a `@tenant_task`, which starts the bank's own agents that are
  on, not paused and due, and moves each one's `next_run_at` on first, so a slot is taken
  once whatever happens to the run.

Before a bank's run opens, two of the bank's own settings are read, and nothing of
bleqq's reads them (D-61):

- **AI off.** The one reader of the switch, `apps.shared.ai.ensure_enabled`, is asked. A
  scheduled run is skipped with one audit row and no run row; run now answers 422
  `feature_off`.
- **The cap.** The month's spend plus the run's `budget_limit` (`AGENT_RUN_BUDGET_LIMIT`)
  must fit under the bank's monthly cap. A scheduled run that would not fit is not started:
  the agent is paused with the reason `budget_cap`, which audits, and the people holding
  `agents.manage` are notified, because nobody is watching a schedule. Run now answers 422
  `budget_cap_reached` to the person who asked, and pauses nothing.

A bank's run is given keys only (R2_CROSS_CUTTING rule n): the definition key, its version
number and the run id reach the runner, and the scope stored on the run is keys only.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from decimal import Decimal
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.agents import budget, definitions
from apps.agents import scope as run_scope
from apps.agents.models import (
    Agent,
    AgentCadence,
    AgentRun,
    AgentScopeKind,
    AgentVersion,
    RunStatus,
    RunTrigger,
    TenantAgent,
)
from apps.agents.tenant_agents import lock_tenant, next_run_at, pause
from apps.collab.logic import notify
from apps.collab.models import NotificationKind
from apps.identity.models import Membership, User, UserStatus
from apps.library.models import Jurisdiction
from apps.shared import ai, tenancy
from apps.shared import permissions as perms
from apps.shared.adapters.agent_runner import get_agent_runner
from apps.shared.audit import Actor, ActorType, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant, TenantStatus

logger = logging.getLogger(__name__)

SUBJECT_TYPE = "agent_run"
SCHEDULER = Actor.system("agent scheduler")
# What a run that the runner would not start says, for the people who operate the agents.
START_FAILED = "The runner could not start this run."


# ---------------------------------------------------------------------------------------
# The one opener
# ---------------------------------------------------------------------------------------
def _open(
    *,
    agent: Agent,
    version: AgentVersion | None,
    trigger: RunTrigger,
    actor: Actor,
    tenant_agent: TenantAgent | None = None,
    requested_by: User | None = None,
    budget_limit: Decimal | None = None,
    scope: dict[str, Any] | None = None,
) -> AgentRun:
    """Record the run, then hand it to the runner. The row and its audit row are written
    before the runner is called, in the caller's transaction."""
    version_no = version.version_no if version is not None else agent.current_version
    run = AgentRun.objects.create(
        agent=agent,
        agent_version=version,
        tenant_agent=tenant_agent,
        trigger=trigger.value,
        requested_by=requested_by,
        model=version.model if version is not None else "",
        pipeline_version=str(version_no),
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
        subject_title=agent.key,
        summary=f"{agent.key} opened a run.",
        tenant_id=run.tenant_id,
        after={
            "agent": agent.key,
            "agentVersion": version_no,
            "trigger": run.trigger,
            "budgetLimit": None if budget_limit is None else str(budget_limit),
            "scope": run.scope,
            **_schedule_of(tenant_agent),
        },
    )
    _hand_over(run, version_no, actor)
    return run


def _hand_over(run: AgentRun, version_no: int, actor: Actor) -> None:
    """Start the recorded run through the runner. Whatever the runner raises, the run is
    closed as failed with a fixed sentence, so no run is left reading as running."""
    try:
        handle = get_agent_runner().start(run_id=run.id, definition_key=run.agent.key, definition_version=version_no)
    except Exception:  # compliance: allow-broad-except the runner is an external executor; any failure to start closes the recorded run as failed
        logger.warning("agent run not started", extra={"run_id": str(run.id), "agent": run.agent.key})
        run.status = RunStatus.FAILED.value
        run.error = START_FAILED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        record(
            action="agent_run.start_failed",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=run.id,
            subject_title=run.agent.key,
            summary=f"The runner could not start {run.agent.key}'s run.",
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
        subject_title=run.agent.key,
        summary=f"The runner started {run.agent.key}'s run.",
        tenant_id=run.tenant_id,
        after={"externalSessionId": handle.external_id},
    )


def _version(agent: Agent) -> AgentVersion | None:
    """The version a run of `agent` pins: its newest one still published (AGT-06). Every
    version retired raises 409 `no_published_version`."""
    version_id = definitions.version_to_run(agent.id)
    return None if version_id is None else AgentVersion.objects.get(pk=version_id)


def _schedule_of(tenant_agent: TenantAgent | None) -> dict[str, Any]:
    """What the audit row of a bank's run carries of the agent's schedule, which the beat
    moved just before: the agent and its next run, an id and a timestamp."""
    if tenant_agent is None:
        return {}
    upcoming = tenant_agent.next_run_at
    return {"tenantAgent": str(tenant_agent.id), "nextRunAt": upcoming.isoformat() if upcoming else None}


def _skipped(*, agent: Agent, reason: str, tenant_id: uuid.UUID | None, after: dict[str, Any]) -> None:
    """A scheduled run that did not open: one audit row naming the reason, a key."""
    record(
        action="agent_run.skipped",
        actor=SCHEDULER,
        subject_type="agent",
        subject_id=agent.id,
        subject_title=agent.key,
        summary=f"A scheduled run of {agent.key} did not start: {reason}.",
        tenant_id=tenant_id,
        after={"agent": agent.key, "reason": reason, **after},
    )


# ---------------------------------------------------------------------------------------
# bleqq's agents: no tenant, no tenant setting, no scope.py
# ---------------------------------------------------------------------------------------
def _covered(agent: Agent) -> list[str]:
    """The jurisdiction keys a platform run sweeps: the agent's own, or every one the
    library covers. Library rows only; no bank's market reaches it."""
    named = (agent.platform_scope or {}).get("jurisdictions") or []
    if named:
        return list(named)
    return list(Jurisdiction.objects.filter(active=True).order_by("sort_order", "key").values_list("key", flat=True))


def open_platform_run(agent: Agent) -> AgentRun:
    """Open a scheduled run of one of bleqq's agents, in no tenant's zone."""
    return _open(
        agent=agent,
        version=_version(agent),
        trigger=RunTrigger.SCHEDULE,
        actor=SCHEDULER,
        scope={"jurisdictions": _covered(agent)},
    )


def _period_start(cadence: str, now: datetime.datetime) -> datetime.datetime:
    """The start of the UTC calendar period a cadence runs once in."""
    today = now.astimezone(datetime.UTC).date()
    first = {
        AgentCadence.DAILY.value: today,
        AgentCadence.WEEKLY.value: today - datetime.timedelta(days=today.weekday()),
        AgentCadence.MONTHLY.value: today.replace(day=1),
    }[cadence]
    return datetime.datetime.combine(first, datetime.time.min, tzinfo=datetime.UTC)


def _due_platform_agents(now: datetime.datetime) -> list[Agent]:
    """bleqq's active, scheduled agents with no scheduled run in this period, the
    longest-waiting first."""
    agents = (
        Agent.objects.filter(scope=AgentScopeKind.PLATFORM.value, active=True)
        .exclude(default_cadence=AgentCadence.MANUAL.value)
        .annotate(last_run=Max("runs__started_at", filter=Q(runs__trigger=RunTrigger.SCHEDULE.value, runs__tenant__isnull=True)))
        .order_by("last_run", "key")
    )
    return [agent for agent in agents if agent.last_run is None or agent.last_run < _period_start(agent.default_cadence, now)]


def _claim(agent: Agent, now: datetime.datetime) -> bool:
    """Hold this agent for the rest of the transaction, and say whether it is still due:
    two beats that overlap start one run between them."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))", [f"agent_beat:{agent.id}"])
        if not cursor.fetchone()[0]:
            return False
    return not AgentRun.objects.filter(
        agent=agent, tenant__isnull=True, trigger=RunTrigger.SCHEDULE.value, started_at__gte=_period_start(agent.default_cadence, now)
    ).exists()


@shared_task
def run_platform_agents() -> None:
    """bleqq's beat: start each due platform agent, at most `AGENT_RUNS_PER_BEAT` of them.
    Not a `@tenant_task`: it activates no tenant and reads no tenant row."""
    now = timezone.now()
    for agent in _due_platform_agents(now)[: settings.AGENT_RUNS_PER_BEAT]:
        with transaction.atomic():
            if not _claim(agent, now):
                continue
            try:
                open_platform_run(agent)
            except ProblemError as refused:
                _skipped(agent=agent, reason=refused.code, tenant_id=None, after={})


# ---------------------------------------------------------------------------------------
# A bank's own agents
# ---------------------------------------------------------------------------------------
def _run_budget_limit() -> Decimal:
    return Decimal(settings.AGENT_RUN_BUDGET_LIMIT).quantize(budget.ZERO)


def _fits_the_cap(tenant: Tenant, limit: Decimal) -> bool:
    """Whether a run may start under the cap. The bank's spend is serialized for the rest of
    the transaction, so a beat and a run now cannot both take the last of it."""
    lock_tenant(tenant, "agent_spend")
    cap = budget.cap_of(tenant)
    return cap is not None and budget.spend(tenant) + limit <= cap


def _notify_cap(tenant_agent: TenantAgent) -> None:
    """Tell the bank's people who hold `agents.manage` that the cap paused an agent."""
    holders = (
        Membership.objects.filter(
            tenant_id=tenant_agent.tenant_id,
            deactivated_at__isnull=True,
            user__status=UserStatus.ACTIVE.value,
            roles__permissions__contains=[perms.AGENTS_MANAGE],
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    notify(
        tenant_id=tenant_agent.tenant_id,
        kind=NotificationKind.ESCALATION,
        subject_type="tenant_agent",
        subject_id=tenant_agent.id,
        candidates=[(user_id, budget.CAP_REASON) for user_id in holders],
    )


def open_tenant_run(tenant_agent: TenantAgent, *, trigger: RunTrigger, requested_by: User | None = None) -> AgentRun | None:
    """Open a run of one of the bank's own agents, in the bank's zone, or say why not.

    A scheduled run that the AI switch or the cap stops returns None, having written its
    audit row (and, for the cap, the pause and the notification). Any other trigger has a
    person waiting on the answer: AI off is 422 `feature_off` and the cap 422
    `budget_cap_reached`, and nothing is written.
    """
    scheduled = trigger is RunTrigger.SCHEDULE
    agent = tenant_agent.agent
    tenant = Tenant.objects.get(pk=tenant_agent.tenant_id)
    try:
        ai.ensure_enabled()
        version = _version(agent)
    except ProblemError as refused:
        if not scheduled:
            if refused.code == "feature_off":
                raise ValidationError(refused.detail, code="feature_off") from None
            raise
        _skipped(agent=agent, reason=refused.code, tenant_id=tenant.id, after=_schedule_of(tenant_agent))
        return None
    limit = _run_budget_limit()
    if not _fits_the_cap(tenant, limit):
        if not scheduled:
            raise ValidationError(
                "This run could cost more than is left of the bank's monthly cap on its own agents.",
                code="budget_cap_reached",
            )
        pause(tenant_agent, budget.CAP_REASON)
        _notify_cap(tenant_agent)
        return None
    if requested_by is None:
        actor = SCHEDULER
    else:
        actor = Actor(kind=ActorType.USER, id=requested_by.id, label=requested_by.name)
    return _open(
        agent=agent,
        version=version,
        trigger=trigger,
        actor=actor,
        tenant_agent=tenant_agent,
        requested_by=requested_by,
        budget_limit=limit,
    )


@shared_task
def schedule_tenant_agents() -> None:
    """The banks' beat: hand each active bank to its own task. It reads the tenant list
    only; a bank's agents are read inside that bank's zone."""
    for tenant_id in Tenant.objects.filter(status=TenantStatus.ACTIVE.value).values_list("id", flat=True):
        run_due_tenant_agents.delay(str(tenant_id))


@shared_task
@tenancy.tenant_task
def run_due_tenant_agents(tenant_id: uuid.UUID) -> None:
    """Start the bank's own agents that are on, not paused and due, moving each one's next
    run first. Another worker holding one of them skips it rather than waiting."""
    tenant = Tenant.objects.get(pk=tenant_id)
    due = (
        TenantAgent.objects.select_related("agent")
        .select_for_update(of=("self",), skip_locked=True)
        .filter(tenant_id=tenant_id, enabled=True, paused_at__isnull=True, next_run_at__lte=timezone.now())
        .order_by("next_run_at", "id")
    )
    for tenant_agent in due:
        tenant_agent.next_run_at = next_run_at(tenant_agent, tenant)
        tenant_agent.save(update_fields=["next_run_at", "updated_at"])
        open_tenant_run(tenant_agent, trigger=RunTrigger.SCHEDULE)
