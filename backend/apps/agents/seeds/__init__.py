"""Reference seed of the agents app (AGT-03), run by `manage.py seed_reference` on every
deploy: the platform's versioned definitions in `backend/agents/<agent>/v<n>/` become
`agent` rows, matched on the definition's immutable `id`.

Library rows, so the writes sit inside `library_write()` and each created row leaves an
audit event, as the taxonomy and library seeds do. An existing row is left alone: a new
version folder is published by a platform admin (AGT-03, chunk 11), not by a deploy
silently rewriting what a run already points at.
"""

from __future__ import annotations

from apps.agents.models import Agent
from apps.agents.seeds.definition import DEFINITIONS, Definition, read_definition
from apps.shared.audit import Actor, record
from apps.shared.tenancy import library_write

SEED_REASON = "seed_reference"
ACTOR = Actor.system(SEED_REASON)
# The definitions this build ships, newest version folder each. Frozen here rather than
# globbed: a folder half-added to the tree never becomes an agent by accident. The sweeper
# proposes and the confirmer decides (kind `review`, D-62, D-80): two definitions, so the
# second pair of eyes on a proposal is never the definition that filed it.
SHIPPED: tuple[tuple[str, int], ...] = (("watch-sweeper", 1), ("library-confirmer", 2))


def definitions() -> list[Definition]:
    return [read_definition(DEFINITIONS / name / f"v{version}" / "definition.yaml") for name, version in SHIPPED]


def seed_agent_definitions() -> int:
    """Create the agent row of every shipped definition. Returns how many were created."""
    created = 0
    with library_write(SEED_REASON):
        for definition in definitions():
            agent, is_new = Agent.objects.get_or_create(
                key=definition.key,
                defaults={
                    "kind": definition.kind,
                    "description": definition.description,
                    "active": definition.active,
                    "current_version": definition.version,
                },
            )
            if is_new:
                record(
                    action="agent.seeded",
                    actor=ACTOR,
                    subject_type="agent",
                    subject_id=agent.id,
                    subject_title=agent.key,
                    summary=f"Agent {agent.key} loaded from its version {agent.current_version} definition.",
                    tenant_id=None,
                    after={"key": agent.key, "kind": agent.kind, "currentVersion": agent.current_version, "active": agent.active},
                )
                created += 1
    return created
