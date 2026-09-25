"""Reference seed of the agents app (AGT-03), run by `manage.py seed_reference` on every
deploy: the platform's versioned definitions in `backend/agents/<agent>/v<n>/` become
`agent` rows, matched on the definition's immutable `id`, each with its first published
`agent_version`.

Library rows, so the writes sit inside `library_write()` and each created row leaves an
audit event, as the taxonomy and library seeds do. An existing row is left alone: a new
version folder is published by a platform admin (AGT-03, chunk 11), not by a deploy
silently rewriting what a run already points at. The one exception is an agent seeded
before versions existed (agents 0004) with no version row at all: it gets the row of the
version it is on, when that is the folder this build ships.

The definition says whether an agent is one of bleqq's or one a bank may add for itself
(`scope`, `tenant_configurable`, `writes_to`), so the platform fence is set by the file and
never by hand. A definition's scope never changes once seeded (agents 0004).
"""

from __future__ import annotations

from apps.agents.models import Agent, AgentVersion
from apps.agents.seeds.definition import DEFINITIONS, Definition, read_definition
from apps.shared.audit import Actor, record
from apps.shared.tenancy import library_write

SEED_REASON = "seed_reference"
ACTOR = Actor.system(SEED_REASON)
# The definitions this build ships, newest version folder each. Frozen here rather than
# globbed: a folder half-added to the tree never becomes an agent by accident. The sweeper
# proposes and the confirmer decides (kind `review`, D-62, D-80): two definitions, so the
# second pair of eyes on a proposal is never the definition that filed it. The third is the
# one a bank may add for itself (AGT-04, ruling 1): bleqq's definition, a bank's agent. The
# fourth is the bank's own researcher for a scope item the library does not cover (OWN-02).
SHIPPED: tuple[tuple[str, int], ...] = (
    ("watch-sweeper", 1),
    ("library-confirmer", 2),
    ("tenant-source-watch", 1),
    ("scope-researcher", 1),
)


def definitions() -> list[Definition]:
    return [read_definition(DEFINITIONS / name / f"v{version}" / "definition.yaml") for name, version in SHIPPED]


def seed_agent_definitions() -> int:
    """Create the agent row of every shipped definition and its first version row. Every
    file is read before anything is written, so a definition the reader refuses stops the
    seed with its path named and nothing half-seeded. Returns how many agents were created."""
    shipped = definitions()
    created = 0
    with library_write(SEED_REASON):
        for definition in shipped:
            agent, is_new = Agent.objects.get_or_create(
                key=definition.key,
                defaults={
                    "kind": definition.kind,
                    "description": definition.description,
                    "active": definition.active,
                    "current_version": definition.version,
                    "scope": definition.scope,
                    "tenant_configurable": definition.tenant_configurable,
                    "writes_to": definition.writes_to,
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
                    after={
                        "key": agent.key,
                        "kind": agent.kind,
                        "currentVersion": agent.current_version,
                        "active": agent.active,
                        "scope": agent.scope,
                        "tenantConfigurable": agent.tenant_configurable,
                        "writesTo": agent.writes_to,
                    },
                )
                created += 1
            if agent.current_version == definition.version and not agent.versions.exists():
                _seed_first_version(agent, definition)
    return created


def _seed_first_version(agent: Agent, definition: Definition) -> None:
    version = AgentVersion.objects.create(
        agent=agent,
        version_no=definition.version,
        model=definition.model,
        prompt_path=definition.prompt,
        tools=list(definition.tools),
        change_note=definition.change_note,
    )
    record(
        action="agent_version.seeded",
        actor=ACTOR,
        subject_type="agent_version",
        subject_id=version.id,
        subject_title=f"{agent.key} v{version.version_no}",
        summary=f"Version {version.version_no} of agent {agent.key} loaded from its definition.",
        tenant_id=None,
        after={"agent": agent.key, "versionNo": version.version_no, "model": version.model, "tools": version.tools},
    )
