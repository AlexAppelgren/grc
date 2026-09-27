"""Runner events (AGT-06): the one door through which what a runner reports reaches a run.

The app is the scheduler of record and a runner is an executor: it writes no row, and what
it may say is a `RunnerEvent` (apps/shared/adapters/agent_runner.py). `apply_event` applies
one inside one transaction through `record()`. An event is validated at this boundary and
never trusted because it came from our own executor, since what it reports came from a
model and a network. The zone is the run's and never the event's: the worker applying it
stands in the run's zone, a platform run's with no tenant or a bank's own under
`@tenant_task`, and anything else is refused, so one bank's worker cannot move a platform run
that every bank reads, nor another bank's.

A finished run is a finished account and takes no more events. `cost` and the token counts
are totals so far, so they never go down. The error text is stored on the run for the
people who operate the agents, and never logged or written to an audit or outbox row.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from pydantic import ValidationError as SchemaError

from apps.agents.models import AgentRun, RunStatus
from apps.agents.schemas import AgentRunFinish, AgentRunStats
from apps.shared import tenancy
from apps.shared.adapters.agent_runner import RunnerEvent
from apps.shared.audit import Actor, record

ACTOR = Actor.system("agent_runner")
# The columns' own bounds: `cost` is numeric(10, 4) and the token counts are bigint.
COST_PLACES = 4
COST_CEILING = Decimal("1000000")
TOKENS_CEILING = 2**63 - 1
# The longest error a run keeps, the same as a run closed through the API may carry.
ERROR_MAX = next(rule.max_length for rule in AgentRunFinish.model_fields["error"].metadata if hasattr(rule, "max_length"))


def apply_event(event: RunnerEvent) -> AgentRun:
    """Apply one runner event to its run, in the caller's zone, and return the run."""
    with transaction.atomic():
        # Read, then lock: a platform run every bank reads is found from a bank's zone and
        # refused by name, while row-level security hides a bank's run from every other zone.
        zones = list(AgentRun.objects.filter(pk=event.run_id).values_list("tenant_id", flat=True))
        if not zones:
            raise ValidationError("No run has that id.", code="not_found")
        if zones[0] != tenancy.active_tenant_id():
            raise ValidationError("That run belongs to another zone than the one applying its event.", code="wrong_zone")
        run = AgentRun.objects.select_for_update(of=("self",)).select_related("agent").get(pk=event.run_id)
        if run.status != RunStatus.RUNNING.value:
            raise ValidationError("That run has finished, so it takes no more events.", code="run_finished")
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
            update_fields=["status", "stats", "cost", "tokens_in", "tokens_out", "error", "finished_at", "interrupted_at"]
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
    return run


def _validated(run: AgentRun, event: RunnerEvent) -> tuple[RunStatus, dict[str, int]]:
    """The event's status and counters, or `invalid_runner_event` for anything a runner may
    not say."""
    try:
        status = RunStatus(event.status)
        stats = AgentRunStats.model_validate(event.stats).model_dump(mode="json", by_alias=True)
    except (ValueError, SchemaError):
        raise ValidationError("The runner reported a status or counters a run does not have.", code="invalid_runner_event") from None
    if set(event.stats) - set(stats):
        raise ValidationError("The runner reported a counter a run does not keep.", code="invalid_runner_event")
    if event.cost is not None and not (
        event.cost.is_finite()
        and Decimal(0) <= event.cost < COST_CEILING
        and event.cost == event.cost.quantize(Decimal(1).scaleb(-COST_PLACES))
    ):
        raise ValidationError("The runner reported a cost a run cannot have.", code="invalid_runner_event")
    for tokens in (event.tokens_in, event.tokens_out):
        if tokens is not None and not 0 <= tokens <= TOKENS_CEILING:
            raise ValidationError("The runner reported a token count a run cannot have.", code="invalid_runner_event")
    spent: tuple[tuple[Decimal | int | None, Decimal | int | None], ...] = (
        (event.cost, run.cost),
        (event.tokens_in, run.tokens_in),
        (event.tokens_out, run.tokens_out),
    )
    for reported, stored in spent:
        if stored is not None and (reported is None or reported < stored):
            raise ValidationError("The runner reported less spent than it already had.", code="invalid_runner_event")
    if len(event.error) > ERROR_MAX:
        raise ValidationError(f"The runner reported an error longer than {ERROR_MAX} characters.", code="invalid_runner_event")
    return status, stats


def _state(run: AgentRun) -> dict[str, object]:
    """What an audit row keeps of a run: its status and what it spent, never its error."""
    return {
        "status": run.status,
        "cost": None if run.cost is None else str(run.cost),
        "tokensIn": run.tokens_in,
        "tokensOut": run.tokens_out,
    }
