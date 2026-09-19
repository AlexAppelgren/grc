"""Request and response schemas of the agents app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1)."""

from __future__ import annotations

from apps.shared.schemas import CamelSchema

__all__ = ["AgentRunStats", "CamelSchema"]


class AgentRunStats(CamelSchema):
    """The `stats` column of agent_run: what one run did, counted against the budget
    defaults of its definition (`backend/agents/<agent>/v<n>/definition.yaml`)."""

    model_calls: int = 0
    fetches: int = 0
    sources_checked: int = 0
    changes_registered: int = 0
    proposals_submitted: int = 0
