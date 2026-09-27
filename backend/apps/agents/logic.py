"""Business logic of the agents app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3).

The agent definitions are library rows the reference seed loads (AGT-03); this module only
reads them. Nothing here writes one, so the library fence has nothing to allow.

It is also where a module of this app that writes a bank's rows (`tenant_agents.py`,
`scope.py`) reads the fenced rows it needs: the library fence refuses a module that both
names a library model and calls a write (apps/shared/tests_library_fence.py), so those
writers name none and ask here, the split `apps/watch/keys.py` makes for the watch app.
"""

from __future__ import annotations

import uuid

from apps.agents.models import Agent
from apps.taxonomy.models import TaxonomyTerm


def definition(agent_id: uuid.UUID) -> Agent | None:
    return Agent.objects.filter(pk=agent_id).first()  # ordering: pk lookup, at most one row


def definition_by_key(key: str) -> Agent | None:
    return Agent.objects.filter(key=key).first()  # ordering: unique key, at most one row


def live_term_keys(keys: list[str]) -> set[str]:
    """Which of `keys` are active taxonomy terms (AGT-02)."""
    return set(TaxonomyTerm.objects.filter(key__in=keys, active=True).values_list("key", flat=True))


def term_keys() -> list[str]:
    """Every active taxonomy term key, for a refusal that lists what may be said."""
    return list(TaxonomyTerm.objects.filter(active=True).order_by("key").values_list("key", flat=True).distinct())
