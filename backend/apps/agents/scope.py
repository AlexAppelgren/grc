"""What one run of a bank's own agent looks at (AGT-04, FP-04, D-32), built at run start and
stored on the run, so a later market or scope change never alters a run already started.

By default the scope follows the bank's markets: the jurisdictions it operates in first,
then the ones it watches, then the jurisdictions whose rules reach them (the EU for Sweden
and for Norway, D-28). When the agent's own row names jurisdictions, those replace the
markets. The vocabularies are read again here (AGT-02): a key retired since a person chose
it is dropped from the run's copy and noted on it, while the agent's row keeps it, so the
admin still sees what they chose.

Keys only: no market name, no tenant name, no free text ever reaches the runner (D-32). The
footprint is read here and never written. A platform run never comes here: bleqq's agents
read their own `platform_scope`, which no bank's market may reach.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from apps.agents.models import AgentRun, TenantAgent
from apps.library.models import Jurisdiction
from apps.agents.logic import live_term_keys
from apps.taxonomy.models import FootprintTerm, WatchedMarket

Level = Literal["operating", "watching", "reaching", "chosen"]


class ScopedJurisdiction(BaseModel):
    key: str = Field(description="The jurisdiction's key, such as `se`.")
    level: Level = Field(
        description=(
            "Why it is in scope. `operating`: the bank operates there. `watching`: the bank "
            "watches it. `reaching`: its rules reach one of those. `chosen`: the agent's own "
            "scope names it."
        )
    )


class DroppedKey(BaseModel):
    vocabulary: Literal["jurisdiction", "taxonomy_term"] = Field(description="The list the key was in.")
    key: str = Field(description="The key retired since it was chosen.")


class AgentRunScope(BaseModel):
    """The copy of a scope a run of a bank's own agent carries (`agent_run.scope`)."""

    source: Literal["markets", "agent"] = Field(
        description="`markets`: the bank's markets, the default. `agent`: the agent's own jurisdictions."
    )
    jurisdictions: list[ScopedJurisdiction] = Field(description="The jurisdictions, in the order the run reads them.")
    terms: list[str] = Field(description="The taxonomy term keys the run narrows to; none means no narrowing.")
    dropped: list[DroppedKey] = Field(description="The keys retired since they were chosen, left out of this run.")


def _markets(tenant_id: uuid.UUID) -> list[ScopedJurisdiction]:
    """Operating, then watching, then reaching, each in the jurisdictions' own order; a
    market counts once, at its first level."""
    operating = set(
        FootprintTerm.objects.filter(tenant_id=tenant_id, term__jurisdiction__isnull=False).values_list("term__jurisdiction_id", flat=True)
    )
    watched = set(WatchedMarket.objects.filter(tenant_id=tenant_id).values_list("jurisdiction_id", flat=True))
    everyone = {row.id: row for row in Jurisdiction.objects.filter(active=True).order_by("sort_order", "key")}
    ordered = list(everyone.values())
    scope: list[ScopedJurisdiction] = []
    seen: set[uuid.UUID] = set()

    def add(ids: set[uuid.UUID], level: Level) -> None:
        for row in ordered:
            if row.id in ids and row.id not in seen:
                seen.add(row.id)
                scope.append(ScopedJurisdiction(key=row.key, level=level))

    add(operating, "operating")
    add(watched, "watching")
    reaching: set[uuid.UUID] = set()
    for market in list(seen):
        parent = everyone[market].parent_id
        while parent in everyone and parent not in reaching:
            reaching.add(parent)
            parent = everyone[parent].parent_id
    add(reaching, "reaching")
    return scope


def for_run(tenant_agent: TenantAgent) -> AgentRunScope:
    """The scope a run of this agent starts with, read fresh from the footprint and the
    vocabularies."""
    chosen = tenant_agent.scope or {}
    jurisdictions: list[str] = list(chosen.get("jurisdictions", []))
    terms: list[str] = list(chosen.get("terms", []))
    dropped: list[DroppedKey] = []
    if jurisdictions:
        active = set(Jurisdiction.objects.filter(key__in=jurisdictions, active=True).values_list("key", flat=True))
        scoped = [ScopedJurisdiction(key=key, level="chosen") for key in jurisdictions if key in active]
        dropped += [DroppedKey(vocabulary="jurisdiction", key=key) for key in jurisdictions if key not in active]
        source: Literal["markets", "agent"] = "agent"
    else:
        scoped = _markets(tenant_agent.tenant_id)
        source = "markets"
    live_terms = live_term_keys(terms)
    dropped += [DroppedKey(vocabulary="taxonomy_term", key=key) for key in terms if key not in live_terms]
    return AgentRunScope(
        source=source, jurisdictions=scoped, terms=[key for key in terms if key in live_terms], dropped=dropped
    )


def snapshot(run: AgentRun) -> AgentRunScope:
    """Store the scope on a run of one of the bank's own agents as it opens, inside the
    transaction whose audit row the opener writes. A platform run is refused: its scope is
    bleqq's, and no bank's market may reach it."""
    tenant_agent = run.tenant_agent
    if tenant_agent is None or run.tenant_id is None:
        raise ValueError("A platform run reads its own platform scope, never a bank's markets.")
    scope = for_run(tenant_agent)
    run.scope = scope.model_dump(mode="json")
    run.save(update_fields=["scope"])
    return scope
