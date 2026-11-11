"""Runner events (AGT-06): the one door through which what a runner reports reaches a run.

The app is the scheduler of record; a runner writes no row and may only say a `RunnerEvent`.
`apply_event` validates it at this boundary (its content came from a model and a network)
and applies it in one transaction through `record()`. The zone is the run's, never the
event's: anything else is refused, so one bank's worker cannot move a platform run or
another bank's.

The cap's second point (AGT-04): an event leaving a bank's run open past the monthly cap
stops the run and pauses the agent (`budget_cap`), notifying `agents.manage` holders, under
the scheduler's spend lock. AI switched off since the start stops the run (`feature_off`)
and pauses nothing.

Findings for an approved scope item (OWN-02, ADR 0059) go through `apply_finding` to
`proposals.tenant_agent`, the only way a tenant run files anything. A finished run takes no
more events; cost and token counts only grow; the error text is never logged or audited.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from pydantic import ValidationError as SchemaError

from apps.agents import budget, control, tenant_agents
from apps.agents.models import AgentRun, ResearchRequestKind, RunStatus
from apps.agents.tenant_agents import lock_tenant
from apps.agents.tasks import _notify_cap as notify_cap  # the scheduler's own notice, never a copy
from apps.agents.schemas import AgentRunFinish, AgentRunStats
from apps.proposals import tenant_agent
from apps.proposals.models import Proposal
from apps.shared import ai, tenancy
from apps.shared.adapters.agent_runner import RunnerEvent
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

ACTOR = Actor.system("agent_runner")
# The columns' own bounds: `cost` is numeric(10, 4) and the token counts are bigint.
COST_PLACES = 4
COST_CEILING = Decimal("1000000")
TOKENS_CEILING = 2**63 - 1
# The longest error a run keeps, the same as a run closed through the API may carry.
ERROR_MAX = next(
    rule.max_length
    for rule in AgentRunFinish.model_fields["error"].metadata
    if hasattr(rule, "max_length")
)


def _open_run(run_id: uuid.UUID) -> AgentRun:
    """The running run `run_id` of the caller's zone, locked for the caller's transaction."""
    # Read, then lock: a platform run is found from a bank's zone and refused by name.
    zones = list(AgentRun.objects.filter(pk=run_id).values_list("tenant_id", flat=True))
    if not zones:
        raise ValidationError("No run has that id.", code="not_found")
    if zones[0] != tenancy.active_tenant_id():
        raise ValidationError(
            "That run belongs to another zone than the one applying its event.",
            code="wrong_zone",
        )
    run = (
        AgentRun.objects.select_for_update(of=("self",))
        .select_related("agent", "research_request")
        .get(pk=run_id)
    )
    if run.status != RunStatus.RUNNING.value:
        raise ValidationError(
            "That run has finished, so it takes no more events.", code="run_finished"
        )
    return run


def apply_finding(run_id: uuid.UUID, finding: tenant_agent.Finding) -> Proposal:
    """Apply one finding of a bank's own agent (OWN-02, ADR 0059) and return the proposal it
    filed. Only a running scope-item research run of the bank's own agent qualifies; anything
    else is `not_own_record` and stores nothing."""
    with transaction.atomic():
        run = _open_run(run_id)
        request = run.research_request
        if run.tenant_id is None or request is None or request.kind != ResearchRequestKind.SCOPE_ITEM.value:
            raise ValidationError(
                "Only a bank's own research of a scope item files proposals through the runner.",
                code="not_own_record",
            )
        return tenant_agent.file_finding(run, finding)


def apply_event(event: RunnerEvent) -> AgentRun:
    """Apply one runner event to its run, in the caller's zone, and return the run."""
    with transaction.atomic():
        run = _open_run(event.run_id)
        status, stats = _validated(run, event)
        before = _state(run)
        run.status = status.value
        run.stats = stats
        run.cost, run.tokens_in, run.tokens_out = event.cost, event.tokens_in, event.tokens_out
        run.error = event.error
        if status is not RunStatus.RUNNING:
            run.finished_at = timezone.now()
        if status is RunStatus.INTERRUPTED:
            run.interrupted_at = run.finished_at
        run.save(
            update_fields=[
                "status",
                "stats",
                "cost",
                "tokens_in",
                "tokens_out",
                "error",
                "finished_at",
                "interrupted_at",
            ]
        )
        record(
            action="agent_run.runner_event",
            actor=ACTOR,
            subject_type="agent_run",
            subject_id=run.id,
            subject_title=run.agent.key,
            summary=f"The runner reported {run.agent.key}'s run as {run.status}.",
            tenant_id=run.tenant_id,
            before=before,
            after=_state(run),
        )
        if run.status == RunStatus.RUNNING.value:
            _hold_to_the_cap(run)
    return run


def _hold_to_the_cap(run: AgentRun) -> None:
    """Stop an open run of a bank's own agent whose bank has switched its AI off, or whose
    cost has taken the month's spend past the bank's cap, pausing the agent for the cap.
    Reaching the cap is not passing it."""
    tenant_agent = run.tenant_agent
    if tenant_agent is None:
        return
    try:
        ai.ensure_enabled()
    except ProblemError as off:
        control.stop(run, by=None, reason=off.code)
        return
    tenant = Tenant.objects.get(pk=tenant_agent.tenant_id)
    lock_tenant(tenant, budget.SPEND_LOCK)
    cap = budget.cap_of(tenant)
    if cap is not None and budget.spend(tenant) <= cap:
        return
    control.stop(run, by=None, reason=budget.CAP_REASON)
    tenant_agents.pause(tenant_agent, budget.CAP_REASON)
    notify_cap(tenant_agent)


def _validated(run: AgentRun, event: RunnerEvent) -> tuple[RunStatus, dict[str, int]]:
    """The event's status and counters, or `invalid_runner_event` for anything a runner may
    not say."""
    try:
        status = RunStatus(event.status)
        stats = AgentRunStats.model_validate(event.stats).model_dump(mode="json", by_alias=True)
    except (ValueError, SchemaError):
        raise ValidationError(
            "The runner reported a status or counters a run does not have.",
            code="invalid_runner_event",
        ) from None
    if set(event.stats) - set(stats):
        raise ValidationError(
            "The runner reported a counter a run does not keep.", code="invalid_runner_event"
        )
    if event.cost is not None and not (
        event.cost.is_finite()
        and Decimal(0) <= event.cost < COST_CEILING
        and event.cost == event.cost.quantize(Decimal(1).scaleb(-COST_PLACES))
    ):
        raise ValidationError(
            "The runner reported a cost a run cannot have.", code="invalid_runner_event"
        )
    for tokens in (event.tokens_in, event.tokens_out):
        if tokens is not None and not 0 <= tokens <= TOKENS_CEILING:
            raise ValidationError(
                "The runner reported a token count a run cannot have.", code="invalid_runner_event"
            )
    spent: tuple[tuple[Decimal | int | None, Decimal | int | None], ...] = (
        (event.cost, run.cost),
        (event.tokens_in, run.tokens_in),
        (event.tokens_out, run.tokens_out),
    )
    for reported, stored in spent:
        if stored is not None and (reported is None or reported < stored):
            raise ValidationError(
                "The runner reported less spent than it already had.", code="invalid_runner_event"
            )
    if len(event.error) > ERROR_MAX:
        raise ValidationError(
            f"The runner reported an error longer than {ERROR_MAX} characters.",
            code="invalid_runner_event",
        )
    return status, stats


def _state(run: AgentRun) -> dict[str, object]:
    """What an audit row keeps of a run: its status and what it spent, never its error."""
    return {
        "status": run.status,
        "cost": None if run.cost is None else str(run.cost),
        "tokensIn": run.tokens_in,
        "tokensOut": run.tokens_out,
    }
