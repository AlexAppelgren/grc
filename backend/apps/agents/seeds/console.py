"""The console's writes to bleqq's agent definitions (AGT-03, ADM-02): publishing a shipped
version folder, retiring a version, and a platform agent's settings.

`agent` and `agent_version` are library rows written by no proposal: the definitions are
the platform's own files, loaded by the reference seed beside this module. Publishing is
the same load done by a person's hand, from the same reader, so it sits behind the same
door (`library_write`, the `seed` door the database accepts for these tables) and the
library fence keeps every other module away from them. This module writes rows and nothing
else: who may call it, what is valid and the audit row are the caller's (`definitions.py`,
`platform.py`), in the same transaction.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.utils import timezone

from apps.agents.models import Agent, AgentVersion
from apps.agents.seeds.definition import Definition
from apps.shared.tenancy import library_write

REASON = "console"


def publish(agent: Agent, definition: Definition, *, change_note: str, published_by_id: uuid.UUID) -> AgentVersion:
    """A new version row from the folder the reader read, and the agent moved onto it."""
    with library_write(f"{REASON}: publish {agent.key} v{definition.version}"):
        version = AgentVersion.objects.create(
            agent=agent,
            version_no=definition.version,
            model=definition.model,
            prompt_path=definition.prompt,
            tools=list(definition.tools),
            change_note=change_note,
            published_by_id=published_by_id,
        )
        agent.current_version = definition.version
        agent.save(update_fields=["current_version"])
    return version


def retire(version: AgentVersion) -> AgentVersion:
    """`retired_at`, the one change the append-only trigger lets through, once."""
    with library_write(f"{REASON}: retire {version.agent_id} v{version.version_no}"):
        version.retired_at = timezone.now()
        version.save(update_fields=["retired_at"])
    return version


def set_platform_settings(agent: Agent, *, cadence: str, jurisdictions: list[str], monthly_budget: Decimal | None) -> Agent:
    """A platform agent's cadence, sweep and budget, the same for every bank."""
    with library_write(f"{REASON}: settings of {agent.key}"):
        agent.default_cadence = cadence
        agent.platform_scope = {"jurisdictions": jurisdictions}
        agent.platform_monthly_budget = monthly_budget
        agent.save(update_fields=["default_cadence", "platform_scope", "platform_monthly_budget"])
    return agent
