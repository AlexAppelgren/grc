"""Business logic of the agents app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3).

The agent definitions are library rows the reference seed loads (AGT-03); this module only
reads them. Nothing here writes one, so the library fence has nothing to allow.
"""

from __future__ import annotations

import uuid

from apps.agents.models import Agent


def definition(agent_id: uuid.UUID) -> Agent | None:
    return Agent.objects.filter(pk=agent_id).first()  # ordering: pk lookup, at most one row
