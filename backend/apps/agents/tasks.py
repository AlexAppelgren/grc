"""The app is the scheduler of record (AGT-03, AGT-04, AGT-06, D-61, ADR 0053).

Every run opens through `opener.open_run` (`open_platform_run` or `open_tenant_run`), which
records the run and its audit row before the runner is asked, and closes it as failed when
the runner cannot start it. This module reads and decides; the opener writes.

- bleqq's beat (`run_platform_agents`) is no `@tenant_task`: it reads no tenant row, setting
  or `scope.py`. Its scope is the agent's `platform_scope`, else every covered jurisdiction.
  An agent is due once per UTC calendar period of its cadence, and a beat starts at most
  `AGENT_RUNS_PER_BEAT`, longest-waiting first.
- A bank's beat (`schedule_tenant_agents`) hands each bank to `run_due_tenant_agents`, which
  starts its agents that are on, not paused and due, moving `next_run_at` first.

Before a bank's run (never bleqq's, D-61): AI off (`apps.shared.ai.ensure_enabled`) skips a
scheduled run with one audit row, or answers 422 `feature_off`; the cap (month's spend plus
`AGENT_RUN_BUDGET_LIMIT`) pauses the agent with `budget_cap` and notifies `agents.manage`,
or answers 422 `budget_cap_reached` to a person. A bank's run gets keys only (rule n).
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.agents import budget, definitions, opener
from apps.agents.models import (
    Agent,
    AgentCadence,
    AgentRun,
    AgentScopeKind,
    AgentVersion,
    ResearchRequest,
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
from apps.shared.audit import Actor, ActorType, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant, TenantStatus

SCHEDULER = Actor.system("agent scheduler")


# --- What a run pins; `opener.open_run` records it ---
def _pinned(agent: Agent) -> opener.Pinned:
    """The version a run of `agent` pins: its newest one still published (AGT-06). Every
    version retired raises 409 `no_published_version`."""
    version_id = definitions.version_to_run(agent.id)
    version = None if version_id is None else AgentVersion.objects.get(pk=version_id)
    return opener.Pinned(
        agent_id=agent.id,
        key=agent.key,
        version_id=version_id,
        version_no=agent.current_version if version is None else version.version_number,
        model="" if version is None else version.model,
    )


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


# --- bleqq's agents: no tenant, no tenant setting, no scope.py ---
def _covered(agent: Agent) -> list[str]:
    """The jurisdiction keys a platform run sweeps: the agent's own, or every one the
    library covers. Library rows only; no bank's market reaches it."""
    named = (agent.platform_scope or {}).get("jurisdictions") or []
    if named:
        return list(named)
    return list(Jurisdiction.objects.filter(active=True).order_by("sort_order", "key").values_list("key", flat=True))


def open_platform_run(agent: Agent) -> AgentRun:
    """Open a scheduled run of one of bleqq's agents, in no tenant's zone."""
    return opener.open_run(
        pinned=_pinned(agent),
        trigger=RunTrigger.SCHEDULE,
        actor=SCHEDULER,
        scope={"jurisdictions": _covered(agent)},
    )


def open_baseline_run(agent_key: str, *, actor: Actor) -> AgentRun:
    """Open a run of one of bleqq's agents whose runner is the calling command, in no
    tenant's zone: the library baseline's filing (D-118, ADR 0065); handed to no runner."""
    agent = Agent.objects.get(key=agent_key, scope=AgentScopeKind.PLATFORM.value)
    return opener.open_run(pinned=_pinned(agent), trigger=RunTrigger.MANUAL, actor=actor, hand_over=False)


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


# --- A bank's own agents ---
def run_budget_limit() -> Decimal:
    return Decimal(settings.AGENT_RUN_BUDGET_LIMIT).quantize(budget.ZERO)


def fits_the_cap(tenant: Tenant, limit: Decimal, *, lock: bool = True) -> bool:
    """Whether a run may start under the cap: `budget.held` plus this run's limit. The bank's
    spend is serialized for the rest of the transaction; `lock=False` is a first look before
    slow work, never the decision."""
    if lock:
        lock_tenant(tenant, budget.SPEND_LOCK)
    cap = budget.cap_of(tenant)
    return cap is not None and budget.held(tenant) + limit <= cap


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
    """Open a run of one of the bank's own agents, in the bank's zone, or say why not. A
    scheduled run stopped by the AI switch or cap returns None after auditing (and for the cap
    pausing and notifying); any other trigger gets 422 `feature_off` or `budget_cap_reached`
    and nothing is written.
    """
    scheduled = trigger is RunTrigger.SCHEDULE
    agent = tenant_agent.agent
    tenant = Tenant.objects.get(pk=tenant_agent.tenant_id)
    try:
        ai.ensure_enabled()
        pinned = _pinned(agent)
    except ProblemError as refused:
        if not scheduled:
            if refused.code == "feature_off":
                raise ValidationError(refused.detail, code="feature_off") from None
            raise
        _skipped(agent=agent, reason=refused.code, tenant_id=tenant.id, after=opener.schedule_of(tenant_agent))
        return None
    limit = run_budget_limit()
    if not fits_the_cap(tenant, limit):
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
    return opener.open_run(
        pinned=pinned,
        trigger=trigger,
        actor=actor,
        tenant_agent=tenant_agent,
        requested_by=requested_by,
        budget_limit=limit,
    )


def open_request_run(research_request: ResearchRequest, *, requested_by: User, agent_key: str = "") -> AgentRun:
    """The run a research request asks for (AGT-05): a bank's own agent in its zone under the
    run budget, or the console's re-tag as bleqq's `agent_key` in no tenant's zone. Refusals
    are `requests.py`'s."""
    tenant_agent = research_request.tenant_agent
    if tenant_agent is not None:
        agent, limit, scope = tenant_agent.agent, run_budget_limit(), None
    else:
        agent = Agent.objects.get(key=agent_key, scope=AgentScopeKind.PLATFORM.value)
        limit, scope = None, {"jurisdictions": _covered(agent)}
    return opener.open_run(
        pinned=_pinned(agent),
        trigger=RunTrigger.REQUEST,
        actor=Actor(kind=ActorType.USER, id=requested_by.id, label=requested_by.name),
        tenant_agent=tenant_agent,
        requested_by=requested_by,
        budget_limit=limit,
        scope=scope,
        research_request=research_request,
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
        opener.take_slot(tenant_agent, next_run_at(tenant_agent, tenant))
        open_tenant_run(tenant_agent, trigger=RunTrigger.SCHEDULE)
