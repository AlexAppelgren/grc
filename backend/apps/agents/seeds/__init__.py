"""Reference seed of the agents app (AGT-03), run by `seed_reference` on every deploy: each
shipped definition in `backend/agents/<agent>/v<n>/` becomes an `agent` row, matched on its
immutable `id`, with its first published `agent_version`.

Library rows, written inside `library_write()` with an audit event each. An existing row is
left alone: a new version is published by a platform admin, never by a deploy rewriting what
a run points at; the one exception is an agent with no version row at all (pre agents 0004).
A definition's `scope`, `tenant_configurable` and `writes_to` set the platform fence from
the file, and its scope never changes once seeded.
"""

from __future__ import annotations

from apps.agents.models import Agent, AgentVersion
from apps.agents.seeds.definition import DEFINITIONS, Definition, read_definition
from apps.shared.audit import Actor, record
from apps.shared.tenancy import library_write

SEED_REASON = "seed_reference"
ACTOR = Actor.system(SEED_REASON)
# The definitions this build ships, newest version folder each, frozen so a half-added folder
# never becomes an agent: the sweeper proposes and the confirmer decides (D-62, D-80), a
# definition a bank may add (AGT-04), the bank's scope researcher (OWN-02), the library
# baseline filer (D-118) and the translator (D-129).
SHIPPED: tuple[tuple[str, int], ...] = (
    ("watch-sweeper", 1),
    ("library-confirmer", 2),
    ("tenant-source-watch", 1),
    ("scope-researcher", 2),  # v2 is scored on the screen rows of all ten languages (D-145)
    ("library-baseline", 1),
    ("library-translator", 2),  # v2 names all ten content languages (D-145)
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
        version_number=definition.version,
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
        subject_title=f"{agent.key} v{version.version_number}",
        summary=f"Version {version.version_number} of agent {agent.key} loaded from its definition.",
        tenant_id=None,
        after={"agent": agent.key, "versionNo": version.version_number, "model": version.model, "tools": version.tools},
    )
