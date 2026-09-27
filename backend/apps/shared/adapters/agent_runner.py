"""Agent runner adapter (playbook 16, DECISIONS D-08, AGT-06). The app is the scheduler of
record: the worker records a run, then starts it through this seam, and the runner is an
executor that writes no row. What a runner may tell the app is a `RunnerEvent` and nothing
else; `apps/agents/runner_events.apply_event` validates each one and applies it to its run
through `record()`.

`mock` starts a run that completes at once with no findings and reports it in events seeded
from the run id, so a test never depends on the clock. `managed_agents` stays named and
unbuilt: D-54 and ADR 0047 refuse it on every deployed environment."""

from __future__ import annotations

import random
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.conf import settings

from apps.agents.models import RunStatus


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
    zone: the zone is the run's own. `stats` holds the run's counters in the camelCase shape
    `AgentRunStats` publishes; `cost` (EUR) and the token counts are totals so far, never
    increments. `error` is stored on the run for the people who operate the agents and never
    logged, because it can carry text off a fetched page."""

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
    def poll(self, handle: RunHandle) -> list[RunnerEvent]: ...

    @abstractmethod
    def interrupt(self, handle: RunHandle) -> RunHandle: ...


# The mock's clock: a fixed instant, so what it reports never depends on when a test runs.
MOCK_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class MockAgentRunner(AgentRunnerAdapter):
    """Completes a run at once with no findings: one progress event, then success. Every
    number is drawn from a generator seeded with the run id."""

    name = "mock"

    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle:
        started_at = MOCK_EPOCH + timedelta(seconds=run_id.int % 86_400)
        return RunHandle(run_id=run_id, external_id=f"mock-{run_id}", status=RunStatus.RUNNING, started_at=started_at)

    def poll(self, handle: RunHandle) -> list[RunnerEvent]:
        seeded = random.Random(handle.run_id.int)  # noqa: S311 - a test double's numbers, not a secret
        tokens_in, tokens_out, cents = seeded.randint(1_000, 50_000), seeded.randint(100, 5_000), seeded.randint(1, 500)
        progress = RunnerEvent(
            run_id=handle.run_id,
            status=RunStatus.RUNNING,
            cost=Decimal(cents) / 200,
            tokens_in=tokens_in // 2,
            tokens_out=tokens_out // 2,
        )
        final = replace(progress, cost=Decimal(cents) / 100, tokens_in=tokens_in, tokens_out=tokens_out)
        if handle.status is RunStatus.INTERRUPTED:
            return [replace(progress, status=RunStatus.INTERRUPTED)]
        return [progress, replace(final, status=RunStatus.SUCCEEDED)]

    def interrupt(self, handle: RunHandle) -> RunHandle:
        return replace(handle, status=RunStatus.INTERRUPTED)


# Ruling 4 of docs/plans/briefs/CHUNK11_TASKS.md, pinned by apps/agents/tests_runner_events.py.
MANAGED_AGENTS_REFUSED = (
    "The Managed Agents runner is not built: D-54 and ADR 0047 refuse managed_agents on every "
    "deployed environment but test, so production agents run in our own worker on an EU endpoint."
)


class ManagedAgentsRunner(AgentRunnerAdapter):
    """Named and never the first real runner (ruling 4): D-54 and ADR 0047 refuse
    `managed_agents` on every deployed environment except `ENVIRONMENT=test`, because
    Managed Agents follows the workspace geography and no EU location is offered. The real
    runner is the Agent SDK in our own worker, a later package with its own ADR amendment."""

    name = "managed_agents"

    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle:
        raise NotImplementedError(MANAGED_AGENTS_REFUSED)

    def poll(self, handle: RunHandle) -> list[RunnerEvent]:
        raise NotImplementedError(MANAGED_AGENTS_REFUSED)

    def interrupt(self, handle: RunHandle) -> RunHandle:
        raise NotImplementedError(MANAGED_AGENTS_REFUSED)


PROVIDERS: dict[str, type[AgentRunnerAdapter]] = {
    "mock": MockAgentRunner,
    "managed_agents": ManagedAgentsRunner,
}


def get_agent_runner() -> AgentRunnerAdapter:
    provider = settings.AGENT_RUNNER
    if provider not in PROVIDERS:
        raise ValueError(f"AGENT_RUNNER={provider!r} is not one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider]()
