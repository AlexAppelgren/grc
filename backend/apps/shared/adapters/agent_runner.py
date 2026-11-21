"""Agent runner adapter (playbook 16, DECISIONS D-08, AGT-06). The app is the scheduler of
record: the worker records a run, then starts it through this seam; the runner writes no
row. A runner tells the app only `RunnerEvent`s, which
`apps/agents/runner_events.apply_event` validates and applies through `record()`.

`mock` starts a run that completes at once with no findings; `none` starts nothing; `worker`
queues the run on the app's own worker, which drives it turn by turn (`apps/agents/worker.py`,
D-147). There is no `managed_agents`: D-54 and ADR 0047 refuse it."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from celery import current_app
from django.conf import settings
from django.db import transaction

from apps.agents.models import AgentRun, RunStatus


@dataclass(frozen=True)
class RunHandle:
    """The runner's answer to a start: its own id for the run and where the run stands."""

    run_id: uuid.UUID
    external_id: str
    status: RunStatus
    started_at: datetime | None


@dataclass(frozen=True)
class RunnerEvent:
    """The only thing a runner may tell the app about a run. It names the run and never a
    zone. `stats` holds the run's counters in `AgentRunStats`' shape; `cost` (EUR) and the
    token counts are totals so far. `error` is stored, never logged: it can carry text off a
    fetched page."""

    run_id: uuid.UUID
    status: RunStatus
    stats: dict[str, int] = field(default_factory=dict)
    cost: Decimal | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    error: str = ""


class AgentRunnerAdapter(ABC):
    name: str

    @abstractmethod
    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle: ...

    @abstractmethod
    def interrupt(self, handle: RunHandle) -> RunHandle: ...


# The mock's clock: a fixed instant, so what it reports never depends on when a test runs.
MOCK_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class MockAgentRunner(AgentRunnerAdapter):
    """Starts a run that is running at once, at an instant drawn from the run id; what it
    then reports is `apps/agents/testing.mock_run_events`."""

    name = "mock"

    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle:
        started_at = MOCK_EPOCH + timedelta(seconds=run_id.int % 86_400)
        return RunHandle(run_id=run_id, external_id=f"mock-{run_id}", status=RunStatus.RUNNING, started_at=started_at)

    def interrupt(self, handle: RunHandle) -> RunHandle:
        return replace(handle, status=RunStatus.INTERRUPTED)


NO_RUNNER = "No agent runner is configured (AGENT_RUNNER=none), so no agent run can start."


class NoAgentRunner(AgentRunnerAdapter):
    """`none` (ADR 0047): what a deployed environment sets until the in-worker EU runner
    exists (D-54 refuses Managed Agents, rule 5 refuses `mock`). A start raises, so the
    opener closes the run as failed; a stop succeeds, since nothing runs."""

    name = "none"

    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle:
        raise NotImplementedError(NO_RUNNER)

    def interrupt(self, handle: RunHandle) -> RunHandle:
        return replace(handle, status=RunStatus.INTERRUPTED)


# The worker's task, named rather than imported: the agents app imports this module.
PLATFORM_TASK = "apps.agents.tasks.drive_platform_run"
BANK_RUNS_NOT_BUILT = "The in-worker runner does not drive a bank's own agents yet."


class WorkerAgentRunner(AgentRunnerAdapter):
    """`worker` (D-147): a run of one of bleqq's agents is queued on the app's own worker
    once the opener's transaction commits. A bank's run is refused until the bank-zone leg
    exists, so the opener closes it as failed. A stop needs nothing from here: the worker
    reads the run's status before every turn and ends it there."""

    name = "worker"

    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle:
        tenant_id = AgentRun.objects.filter(pk=run_id).values_list("tenant_id", flat=True).first()  # ordering: pk lookup
        if tenant_id is not None:
            raise NotImplementedError(BANK_RUNS_NOT_BUILT)
        transaction.on_commit(lambda: current_app.send_task(PLATFORM_TASK, args=[str(run_id)]))
        return RunHandle(run_id=run_id, external_id=f"worker-{run_id}", status=RunStatus.RUNNING, started_at=None)

    def interrupt(self, handle: RunHandle) -> RunHandle:
        return replace(handle, status=RunStatus.INTERRUPTED)


PROVIDERS: dict[str, type[AgentRunnerAdapter]] = {
    "mock": MockAgentRunner,
    "none": NoAgentRunner,
    "worker": WorkerAgentRunner,
}


def get_agent_runner() -> AgentRunnerAdapter:
    provider = settings.AGENT_RUNNER
    if provider not in PROVIDERS:
        raise ValueError(f"AGENT_RUNNER={provider!r} is not one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider]()
