"""Agent runner adapter (playbook 16, DECISIONS D-08). The app is the scheduler of record:
the worker starts runs through this seam and updates them from runner events. `mock`
completes a run immediately with no findings; `managed_agents` is named now and built in
chunk 11 after fetching current documentation."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class RunHandle:
    run_id: uuid.UUID
    external_id: str
    status: str  # a RunStatus kind once apps.agents defines it (chunk 11)


class AgentRunnerAdapter(ABC):
    name: str

    @abstractmethod
    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle: ...

    @abstractmethod
    def interrupt(self, handle: RunHandle) -> RunHandle: ...


class MockAgentRunner(AgentRunnerAdapter):
    name = "mock"

    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle:
        return RunHandle(run_id=run_id, external_id=f"mock-{run_id}", status="completed")

    def interrupt(self, handle: RunHandle) -> RunHandle:
        return RunHandle(run_id=handle.run_id, external_id=handle.external_id, status="interrupted")


class ManagedAgentsRunner(AgentRunnerAdapter):
    name = "managed_agents"

    def start(self, *, run_id: uuid.UUID, definition_key: str, definition_version: int) -> RunHandle:
        raise NotImplementedError("Managed Agents runner lands in chunk 11 (D-08)")

    def interrupt(self, handle: RunHandle) -> RunHandle:
        raise NotImplementedError("Managed Agents runner lands in chunk 11 (D-08)")


PROVIDERS: dict[str, type[AgentRunnerAdapter]] = {
    "mock": MockAgentRunner,
    "managed_agents": ManagedAgentsRunner,
}


def get_agent_runner() -> AgentRunnerAdapter:
    provider = settings.AGENT_RUNNER
    if provider not in PROVIDERS:
        raise ValueError(f"AGENT_RUNNER={provider!r} is not one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider]()
