"""Request and response schemas of the agents app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Plain Pydantic, never `ModelSchema`: the agent contract references no Django model, so it
lands beside the watch models rather than behind them. `Literal` rather than an enum class
for the fixed kinds a caller may send (`run_status`, `check_status`): a kind in code stays
in code, and the OpenAPI enum is the same either way.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from ninja import Field

from apps.shared.schemas import CamelSchema, WriteBody

__all__ = [
    "AgentRunFinish",
    "AgentRunInput",
    "AgentRunOut",
    "AgentRunPage",
    "AgentRunStats",
    "CamelSchema",
]


class AgentRunStats(CamelSchema):
    """The `stats` column of agent_run: what one run did, counted against the budget
    defaults of its definition (`backend/agents/<agent>/v<n>/definition.yaml`)."""

    model_calls: int = 0
    fetches: int = 0
    sources_checked: int = 0
    changes_registered: int = 0
    proposals_submitted: int = 0


class AgentRunInput(WriteBody):
    """`POST /agent-runs`, the first call of every execution (AGT-01). `agent` is the
    definition's stable key, never its label."""

    agent: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    pipeline_version: str = Field(min_length=1, max_length=40)


class AgentRunFinish(WriteBody):
    """`PATCH /agent-runs/{runId}`: a run closes once, into a terminal status."""

    status: Literal["succeeded", "failed"]
    stats: AgentRunStats | None = None
    output_ref: str | None = Field(default=None, max_length=500)
    error: str | None = Field(default=None, max_length=2000)


class AgentRunOut(CamelSchema):
    """One run as every reader sees it. A tenant reads the library's runs and its own; no
    reader sees another tenant's (AGT-01, item 14)."""

    id: uuid.UUID
    agent: str
    started_at: datetime
    finished_at: datetime | None
    status: Literal["running", "succeeded", "failed"]
    model: str
    pipeline_version: str
    stats: AgentRunStats
    output_ref: str | None
    error: str | None


class AgentRunPage(CamelSchema):
    """`{items, total}` with `limit` and `offset`, not the designed cursor page (playbook 10)."""

    items: list[AgentRunOut]
    total: int
