"""The in-worker agent runner (D-147, AGT-06, H80): the app's own worker drives a run of one
of bleqq's agents, turn by turn, with the definition's prompt and the tools its published
version names (`runner_tools`).

The opener records the run and `WorkerAgentRunner` queues it here once that commits. Before
every turn the run is read again, so a stop from outside or an overdue close ends it; the
turn limit and the agent's monthly budget are checked; each turn is logged with its cost
(`ai.converse`) and reported as a runner event, which is H80's leg: the run row carries
what it spent while it runs. A tool runs in a transaction of its own and a refusal goes back
to the model as an error result. The run ends when the model ends its turn, closed with the
status and counters it reported through `finishAgentRun`.

A bank's own agents are not driven here yet: `WorkerAgentRunner` refuses to start their runs,
so the opener closes each as failed at once, until the bank-zone leg is built.
"""

from __future__ import annotations

import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from pydantic import ValidationError as SchemaError

from apps.agents import platform, runner_events, runner_tools
from apps.agents.models import AgentRun, RunStatus
from apps.agents.seeds.definition import DEFINITIONS
from apps.shared import ai
from apps.shared.adapters.agent_runner import RunnerEvent
from apps.shared.errors import ProblemError

logger = logging.getLogger(__name__)

TURN_LIMIT = "The run reached the most turns one run may take."
OVER_BUDGET = "The agent has spent its monthly budget."
NO_ANSWER = "The model did not answer."
CUT_SHORT = "The model's turn was cut off before it finished."
NO_TOOLS = "This agent has no tool the runner holds."


def _prompt(run: AgentRun) -> str:
    """The system prompt of the version the run pinned, from the folder the build ships."""
    return (DEFINITIONS / run.agent.key / f"v{run.pipeline_version}" / "prompt.md").read_text(encoding="utf-8")


def _kickoff(run: AgentRun) -> str:
    """The first message: the run's own facts as data, never instructions from anyone."""
    facts = {"agentRunId": str(run.id), "agent": run.agent.key, "version": run.pipeline_version, "trigger": run.trigger, "scope": run.scope}
    return (
        "The run is open; startAgentRun is already done. Its facts, as data:\n"
        f"{json.dumps(facts, ensure_ascii=False)}\n"
        "Do the run's work with your tools, then call finishAgentRun and end your turn."
    )


def _cost(minor: int) -> Decimal:
    return (Decimal(minor) / 100).quantize(Decimal("0.0001"))


class _Ledger:
    """What the run has spent so far, reported as running totals (`RunnerEvent`)."""

    def __init__(self) -> None:
        self.turns = 0
        self.cost_minor = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def add(self, conversed: ai.Conversed) -> None:
        self.turns += 1
        self.cost_minor += conversed.generation.cost_minor
        self.tokens_in += conversed.turn.input_tokens
        self.tokens_out += conversed.turn.output_tokens


def _report(run: AgentRun, ledger: _Ledger, session: runner_tools.Session, status: RunStatus, error: str = "") -> bool:
    """Report the run's totals, and say whether it is still open: a run stopped from outside
    in the meantime takes no more events, and that ends the drive."""
    reported = session.finish.stats.model_dump(by_alias=True, exclude_none=True) if session.finish else {}
    stats = {**reported, "modelCalls": ledger.turns, "fetches": session.fetches}
    try:
        with transaction.atomic():
            _apply(run, ledger, status, stats, error)
    except ValidationError as refused:
        if getattr(refused, "code", None) == "run_finished":
            return False
        raise
    return status is RunStatus.RUNNING


def _apply(run: AgentRun, ledger: _Ledger, status: RunStatus, stats: dict[str, int], error: str) -> None:
    runner_events.apply_event(
        RunnerEvent(
            run_id=run.id,
            status=status,
            stats=stats,
            cost=_cost(ledger.cost_minor),
            tokens_in=ledger.tokens_in,
            tokens_out=ledger.tokens_out,
            error=error[: runner_events.ERROR_MAX],
        )
    )


def _result(session: runner_tools.Session, tool: runner_tools.Tool | None, use: dict[str, Any]) -> dict[str, Any]:
    """One tool call's result block. A refusal is the model's to read and changes nothing."""
    if tool is None:
        content, failed = f"There is no tool named {use['name']}.", True
    else:
        try:
            with transaction.atomic():
                content, failed = runner_tools.call(session, tool, use["input"]), False
        except ProblemError as refused:
            content, failed = f"Refused ({refused.code}): {refused.detail}", True
        except ValidationError as refused:
            content, failed = f"Refused ({getattr(refused, 'code', None) or 'validation_error'}): {' '.join(refused.messages)}", True
        except (SchemaError, ValueError) as refused:
            content, failed = f"Refused (validation_error): {refused}", True
    return {"type": "tool_result", "tool_use_id": use["id"], "content": content[: settings.AGENT_TOOL_RESULT_MAX_CHARS], "is_error": failed}


def _running(run_id: uuid.UUID) -> AgentRun | None:
    return AgentRun.objects.select_related("agent", "agent_version").filter(pk=run_id, status=RunStatus.RUNNING.value).first()  # ordering: pk lookup


def drive(run_id: uuid.UUID) -> None:
    """Drive one keyless platform run to its end."""
    run = _running(run_id)
    if run is None or run.tenant_id is not None or run.api_key_id is not None:
        return
    session = runner_tools.Session(run=run)
    ledger = _Ledger()
    tools = runner_tools.offered(run)
    if not tools:
        _report(run, ledger, session, RunStatus.FAILED, NO_TOOLS)
        return
    by_name = {tool.name: tool for tool in tools}
    system = _prompt(run)
    messages: list[dict[str, Any]] = [{"role": "user", "content": _kickoff(run)}]
    while True:
        if _running(run.id) is None:
            return  # stopped from outside, or closed as overdue
        if ledger.turns >= settings.AGENT_RUN_MAX_TURNS:
            _report(run, ledger, session, RunStatus.FAILED, TURN_LIMIT)
            return
        try:
            platform.refuse_over_budget(run.agent)
        except ProblemError:
            _report(run, ledger, session, RunStatus.FAILED, OVER_BUDGET)
            return
        # The failed call's own row is written in a savepoint of its own, so the error is
        # caught inside the transaction and the row is kept (`ai.converse`).
        conversed: ai.Conversed | None
        with transaction.atomic():
            try:
                conversed = ai.converse(
                    system=system,
                    messages=messages,
                    tools=[tool.spec() for tool in tools],
                    prompt_template=f"{run.agent.key}/v{run.pipeline_version}",
                    agent_run_id=run.id,
                    tenant_id=None,
                    model=platform.model_of(run.agent),
                    effort=platform.effort_of(run.agent),
                )
            except ai.LlmError:
                conversed = None
        if conversed is None:
            logger.warning("agent turn not answered", extra={"run_id": str(run.id), "agent": run.agent.key})
            _report(run, ledger, session, RunStatus.FAILED, NO_ANSWER)
            return
        ledger.add(conversed)
        session.generation = conversed.generation
        turn = conversed.turn
        messages.append({"role": "assistant", "content": turn.content})
        if turn.stop_reason != "tool_use":
            if turn.stop_reason != "end_turn":
                _report(run, ledger, session, RunStatus.FAILED, CUT_SHORT)
            elif session.finish is not None:
                _report(run, ledger, session, RunStatus(session.finish.status), session.finish.error)
            else:
                _report(run, ledger, session, RunStatus.SUCCEEDED)
            return
        messages.append({"role": "user", "content": [_result(session, by_name.get(use["name"]), use) for use in turn.tool_uses]})
        if not _report(run, ledger, session, RunStatus.RUNNING):
            return

