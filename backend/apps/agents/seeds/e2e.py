"""The E2E seed's second published version of a platform agent (c11-e2e-seed, AGT-03).

AGT-S4's journey needs a definition with a version history, and earlier runs naming an
earlier version. `seed_e2e` asks for it here because `agent_version` is a library row that
only a reference seed's directory may write (apps/shared/tests_library_fence.py). The
version repeats the one before it (model, prompt file, tools) with its own change note, as
publishing does in the console, and moves the agent onto it. Refused on a deployed
environment: a deploy never publishes a version (`apps/agents/seeds/__init__.py`).
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
    existing = agent.versions.filter(version_no=version_no).first()  # ordering: unique (agent, version_no)
    if existing is not None:
        return existing
    previous = agent.versions.get(version_no=version_no - 1)
    with library_write(SEED_REASON):
        version = AgentVersion.objects.create(
            agent=agent,
            version_no=version_no,
            model=previous.model,
            prompt_path=previous.prompt_path,
            tools=previous.tools,
            change_note=change_note,
        )
        before = agent.current_version
        agent.current_version = version_no
        agent.save(update_fields=["current_version"])
        record(
            action="agent_version.published",
            actor=Actor.system(SEED_REASON),
            subject_type="agent_version",
            subject_id=version.id,
            subject_title=f"{agent.key} v{version_no}",
            summary=f"Version {version_no} of agent {agent.key} published for the E2E journeys.",
            tenant_id=None,
            before={"currentVersion": before},
            after={"agent": agent.key, "versionNo": version_no, "currentVersion": version_no},
        )
    return version
