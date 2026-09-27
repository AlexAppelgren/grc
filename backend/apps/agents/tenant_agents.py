"""A bank's own agents (AGT-04, ADR 0053): added from a tenant-scoped definition, switched on
and off, given a cadence and a scope, and only ever inside the bank's own zone.

A record is loaded under row-level security first, so another bank's agent is not found
before anything else is said, and one of bleqq's agents is refused by the fence before any
write is attempted. The plan limits are settings until plans exist (R3): the most frequent
cadence (`AGENT_MIN_CADENCE`) and how many agents a bank may add (`AGENTS_PER_TENANT_MAX`),
each 422 `above_plan_limit` past it. An agent is switched on only once the bank has set its
monthly cap, so no agent of a bank's own ever runs uncapped.

The scope is keys only (D-32): jurisdiction and taxonomy term keys, each an active row. A
person holding `agents.manage` sets it; no agent sets its own scope, and nothing here reads
or writes the bank's regulatory scope (D-89). `next_run_at` is computed here, at write time,
from the cadence and the bank's own time zone; the scheduler reads it and does not
recompute it.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.agents.models import Agent, AgentCadence, TenantAgent, TenantAgentBudget
from apps.agents.platform import refuse_platform_agent
from apps.agents.schemas import TenantAgentInput, TenantAgentScope, TenantAgentUpdate
from apps.identity.models import User
from apps.shared.audit import Actor, ActorType, record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy.models import TaxonomyTerm
from apps.taxonomy.tenant_lists_logic import VocabularyProblem
from apps.watch.keys import resolve_keys

SUBJECT_TYPE = "tenant_agent"
# Most frequent first: a cadence ranked before the plan's minimum runs more often than the
# plan allows. `manual` never runs on its own, so it is always within the limit.
_FREQUENCY = (AgentCadence.DAILY.value, AgentCadence.WEEKLY.value, AgentCadence.MONTHLY.value, AgentCadence.MANUAL.value)
_WEEKDAY_CADENCES = (AgentCadence.WEEKLY.value, AgentCadence.MONTHLY.value)
_MONDAY = 1


def own_agent(tenant_agent_id: uuid.UUID) -> TenantAgent:
    """The caller's bank's own agent, read under row-level security: another bank's agent
    and one that does not exist are the same 404. It is fenced before it is returned, so
    every control that starts here refuses one of bleqq's agents."""
    agent = TenantAgent.objects.select_related("agent", "paused_by").filter(pk=tenant_agent_id).first()  # ordering: pk lookup, at most one row
    if agent is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    refuse_platform_agent(agent.agent)
    return agent


def lock_tenant(tenant: Tenant, purpose: str) -> None:
    """Serialize one kind of write per bank for the rest of the transaction, so two requests
    cannot both pass a count or both create the one row a bank may have."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"{purpose}:{tenant.id}"])


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def _out(agent: TenantAgent) -> dict[str, Any]:
    paused_by = agent.paused_by
    return {
        "id": agent.id,
        "agent": agent.agent.key,
        "enabled": agent.enabled,
        "cadence": agent.cadence,
        "run_weekday": agent.run_weekday,
        "run_hour": agent.run_hour,
        "next_run_at": agent.next_run_at,
        "scope": TenantAgentScope.model_validate(agent.scope or {}),
        "paused_at": agent.paused_at,
        "paused_by": None if paused_by is None else {"id": paused_by.id, "name": paused_by.name},
        "updated_at": agent.updated_at,
    }


def list_tenant_agents(*, tenant: Tenant, limit: int, offset: int) -> dict[str, Any]:
    """`GET /agents`: the bank's own agents by definition key. A platform definition can
    never carry a `tenant_agent` row (agents 0005), so bleqq's agents are never here."""
    rows = TenantAgent.objects.filter(tenant=tenant).select_related("agent", "paused_by").order_by("agent__key")
    return {"items": [_out(row) for row in rows[offset : offset + limit]], "total": rows.count()}


# ---------------------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------------------
def _check_cadence(cadence: str) -> None:
    if _FREQUENCY.index(cadence) < _FREQUENCY.index(settings.AGENT_MIN_CADENCE):
        raise ValidationError(
            f"The plan allows a cadence of {settings.AGENT_MIN_CADENCE} at most; {cadence} runs more often.",
            code="above_plan_limit",
        )


def _check_scope(scope: TenantAgentScope) -> dict[str, list[str]]:
    """Keys only, each an active row (AGT-02): an unknown or retired key answers 422
    `unknown_key` with the valid keys, so one refusal teaches the whole list."""
    resolve_keys("jurisdiction", scope.jurisdictions)
    terms = list(dict.fromkeys(scope.terms))
    known = set(TaxonomyTerm.objects.filter(key__in=terms, active=True).values_list("key", flat=True))
    unknown = [key for key in terms if key not in known]
    if unknown:
        valid = list(TaxonomyTerm.objects.filter(active=True).order_by("key").values_list("key", flat=True).distinct())
        raise VocabularyProblem(
            f"Not a taxonomy term key: {', '.join(unknown)}.",
            code="unknown_key",
            extra={"vocabulary": "taxonomy_term", "validKeys": valid},
        )
    return {"jurisdictions": list(scope.jurisdictions), "terms": list(scope.terms)}


def _schedule(agent: TenantAgent) -> None:
    """Keep the run day and hour to what the cadence reads: none for manual, no day for daily,
    and the defaults where the bank named none, so the row shows when it will run."""
    if agent.cadence == AgentCadence.MANUAL.value:
        agent.run_weekday = agent.run_hour = None
        return
    if agent.run_hour is None:
        agent.run_hour = settings.AGENT_DEFAULT_RUN_HOUR
    if agent.cadence in _WEEKDAY_CADENCES:
        agent.run_weekday = agent.run_weekday or _MONDAY
    else:
        agent.run_weekday = None


def next_run_at(agent: TenantAgent, tenant: Tenant) -> datetime.datetime | None:
    """The next scheduled start after now, in UTC: the tenant-local date the cadence names at
    the run hour in the bank's own time zone. Daily: the next such hour. Weekly: the next run
    weekday. Monthly: the first run weekday of the month. None when the agent is off, paused
    or manual, because then no run is scheduled."""
    if not agent.enabled or agent.paused_at is not None or agent.cadence == AgentCadence.MANUAL.value:
        return None
    zone = ZoneInfo(tenant.timezone)
    now = timezone.now()
    today = now.astimezone(zone).date()
    wall = datetime.time(settings.AGENT_DEFAULT_RUN_HOUR if agent.run_hour is None else agent.run_hour)
    weekday = agent.run_weekday or _MONDAY

    def at(day: datetime.date) -> datetime.datetime:
        return datetime.datetime.combine(day, wall, tzinfo=zone).astimezone(datetime.UTC)

    if agent.cadence == AgentCadence.DAILY.value:
        return next(at(day) for day in (today, today + datetime.timedelta(days=1)) if at(day) > now)
    if agent.cadence == AgentCadence.WEEKLY.value:
        ahead = (weekday - today.isoweekday()) % 7
        day = today + datetime.timedelta(days=ahead)
        return at(day) if at(day) > now else at(day + datetime.timedelta(days=7))
    month = today.replace(day=1)
    for _ in range(2):
        first = month + datetime.timedelta(days=(weekday - month.isoweekday()) % 7)
        if at(first) > now:
            return at(first)
        month = (month + datetime.timedelta(days=32)).replace(day=1)
    raise AssertionError("the first run weekday of next month is always ahead")  # pragma: no cover


def _state(agent: TenantAgent) -> dict[str, Any]:
    """What an audit row carries: keys, numbers and a timestamp, never free text."""
    return {
        "agent": agent.agent.key,
        "enabled": agent.enabled,
        "cadence": agent.cadence,
        "runWeekday": agent.run_weekday,
        "runHour": agent.run_hour,
        "scope": agent.scope,
        "nextRunAt": agent.next_run_at.isoformat() if agent.next_run_at else None,
    }


def _person(who: Principal) -> tuple[User, Actor]:
    user = User.objects.get(pk=who.subject_id)
    return user, Actor(kind=ActorType.USER, id=user.id, label=user.name)


# ---------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------
def create_tenant_agent(*, who: Principal, tenant: Tenant, body: TenantAgentInput) -> dict[str, Any]:
    """`POST /agents`: a switched-off agent of the bank's own from a tenant-scoped definition.
    The fence answers first, so one of bleqq's agents writes nothing."""
    definition = Agent.objects.filter(key=body.agent).first()  # ordering: unique key, at most one row
    if definition is None:
        raise ValidationError("No agent definition has that key.", code="unknown_key")
    refuse_platform_agent(definition)
    _check_cadence(body.cadence)
    scope = _check_scope(body.scope)
    lock_tenant(tenant, SUBJECT_TYPE)
    if TenantAgent.objects.filter(tenant=tenant).count() >= settings.AGENTS_PER_TENANT_MAX:
        raise ValidationError(
            f"The plan allows {settings.AGENTS_PER_TENANT_MAX} agents of the bank's own.", code="above_plan_limit"
        )
    user, actor = _person(who)
    agent = TenantAgent(
        tenant=tenant,
        agent=definition,
        enabled=False,
        cadence=body.cadence,
        run_weekday=body.run_weekday,
        run_hour=body.run_hour,
        scope=scope,
        updated_by=user,
    )
    _schedule(agent)
    try:
        with transaction.atomic():
            agent.save()
    except IntegrityError as exc:
        if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) != "tenant_agent_unique":
            raise
        raise ValidationError("The bank has already added this agent.", code="duplicate_key") from exc
    record(
        action="agents.tenant_agent_added",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=agent.id,
        subject_title=definition.key,
        summary=f"Added the agent {definition.key}.",
        tenant_id=tenant.id,
        after=_state(agent),
    )
    return _out(agent)


def update_tenant_agent(*, who: Principal, tenant: Tenant, tenant_agent_id: uuid.UUID, body: TenantAgentUpdate) -> dict[str, Any]:
    """`PATCH /agents/{tenantAgentId}`: what the body sends and nothing else. Switching on
    needs the bank's monthly cap first; switching off is always allowed."""
    agent = own_agent(tenant_agent_id)
    before = _state(agent)
    sent = body.model_fields_set
    if body.cadence is not None:
        _check_cadence(body.cadence)
        agent.cadence = body.cadence
    if body.scope is not None:
        agent.scope = _check_scope(body.scope)
    if "run_weekday" in sent:
        agent.run_weekday = body.run_weekday
    if "run_hour" in sent:
        agent.run_hour = body.run_hour
    if body.enabled is not None:
        if body.enabled and not agent.enabled:
            if not TenantAgentBudget.objects.filter(tenant=tenant).exists():
                raise ValidationError("Set the monthly cap before switching an agent on.", code="budget_cap_required")
        agent.enabled = body.enabled
    _schedule(agent)
    agent.next_run_at = next_run_at(agent, tenant)
    user, actor = _person(who)
    agent.updated_by = user
    agent.save()
    record(
        action="agents.tenant_agent_changed",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=agent.id,
        subject_title=agent.agent.key,
        summary=f"Changed the agent {agent.agent.key}.",
        tenant_id=tenant.id,
        before=before,
        after=_state(agent),
    )
    return _out(agent)


def pause(tenant_agent: TenantAgent, reason: str, *, by: User | None = None) -> TenantAgent:
    """Pause one of the bank's own agents for the scheduler, the controls and the cap: it
    starts no run until someone resumes it, and keeps its settings and history. `reason` is
    a key (`budget_cap`), never text a person typed; `by` is the person, or None when the
    system paused it. Pausing a paused agent changes nothing and records nothing."""
    refuse_platform_agent(tenant_agent.agent)
    if tenant_agent.paused_at is not None:
        return tenant_agent
    before = _state(tenant_agent)
    tenant_agent.paused_at = timezone.now()
    tenant_agent.paused_by = by
    tenant_agent.pause_reason = reason
    tenant_agent.next_run_at = None
    tenant_agent.save(update_fields=["paused_at", "paused_by", "pause_reason", "next_run_at", "updated_at"])
    actor = Actor.system() if by is None else Actor(kind=ActorType.USER, id=by.id, label=by.name)
    record(
        action="agents.tenant_agent_paused",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=tenant_agent.id,
        subject_title=tenant_agent.agent.key,
        summary=f"Paused the agent {tenant_agent.agent.key}.",
        tenant_id=tenant_agent.tenant_id,
        before=before,
        after={**_state(tenant_agent), "pauseReason": reason},
    )
    return tenant_agent
