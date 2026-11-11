"""Business logic of the agents app: reads of the agent definitions (library rows the
reference seed loads, AGT-03) for the modules here that write a bank's rows
(`tenant_agents.py`, `scope.py`), which the library fence forbids to name a library model.
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
