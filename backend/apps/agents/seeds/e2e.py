"""The E2E seed's second published version of a platform agent (AGT-03), for AGT-S4's
version history; here because only a reference seed's directory may write `agent_version`.

It repeats the previous version with its own change note and leaves the current version
where it was: no definition file ships for it, and a key is minted only for an active or
draft current version (H43, D-93), so moving the sweeper would cost J-4 and ID-S20 their
keys. Refused on a deployed environment.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.agents.models import Agent, AgentVersion
from apps.shared.audit import Actor, record
from apps.shared.tenancy import library_write

SEED_REASON = "seed_e2e"


def publish_e2e_version(*, key: str, version_no: int, change_note: str) -> AgentVersion:
    """Version `version_no` of agent `key`, published once; a second call finds it and
    writes nothing."""
    if settings.IS_DEPLOYED_ENVIRONMENT:
        raise ImproperlyConfigured(f"{SEED_REASON} never publishes an agent version on environment {settings.ENVIRONMENT!r}.")
    agent = Agent.objects.get(key=key)
    existing = agent.versions.filter(version_number=version_no).first()  # ordering: unique (agent, version_number)
    if existing is not None:
        return existing
    previous = agent.versions.get(version_number=version_no - 1)
    with library_write(SEED_REASON):
        version = AgentVersion.objects.create(
            agent=agent,
            version_number=version_no,
            model=previous.model,
            prompt_path=previous.prompt_path,
            tools=previous.tools,
            change_note=change_note,
        )
        record(
            action="agent_version.published",
            actor=Actor.system(SEED_REASON),
            subject_type="agent_version",
            subject_id=version.id,
            subject_title=f"{agent.key} v{version_no}",
            summary=f"Version {version_no} of agent {agent.key} published for the E2E journeys.",
            tenant_id=None,
            after={"agent": agent.key, "versionNo": version_no, "currentVersion": agent.current_version},
        )
    return version
