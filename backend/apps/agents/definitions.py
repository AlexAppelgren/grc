"""The platform's agent definitions and their versions (AGT-03, ADM-02, ID-10).

A version is published from the folder the build ships (`backend/agents/<agent>/v<n>/`),
never from a request body, so what runs is what was reviewed. A published version is never
rewritten (a run points at it); retiring stops new runs only. Every write needs a fresh
passkey and leaves one tenantless audit row. The rows are platform configuration (D-102,
ADR 0062), written through `seeds/console.py`.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, QuerySet, Subquery

from apps.agents.models import Agent, AgentVersion
from apps.agents.schemas import (
    AgentDefinitionDetail,
    AgentDefinitionOut,
    AgentDefinitionPage,
    AgentVersionInput,
    AgentVersionOut,
)
from apps.agents.seeds import console, definition as reader
from apps.identity.models import User
from apps.shared.audit import Actor, ActorType, record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError, not_found
from apps.taxonomy.schemas import PersonRef

SUBJECT_TYPE = "agent_version"


def _definitions() -> QuerySet[Agent]:
    published = AgentVersion.objects.filter(agent=OuterRef("pk"), version_number=OuterRef("current_version"))
    return Agent.objects.annotate(published_at=Subquery(published.values("published_at")[:1])).order_by("key", "id")


def list_definitions(*, limit: int, offset: int) -> AgentDefinitionPage:
    """Every definition by key, one page at a time, the same for every bank."""
    queryset = _definitions()
    return AgentDefinitionPage(
        items=[AgentDefinitionOut.model_validate(row) for row in queryset[offset : offset + limit]],
        total=queryset.count(),
    )


def _agent(agent_key: str, *, lock: bool = False) -> Agent:
    queryset = Agent.objects.select_for_update() if lock else Agent.objects.all()
    agent = queryset.filter(key=agent_key).first()  # ordering: key is unique, at most one row
    if agent is None:
        raise not_found()
    return agent


def version_row(version: AgentVersion) -> AgentVersionOut:
    person = version.published_by
    return AgentVersionOut(
        version_no=version.version_number,
        model=version.model,
        change_note=version.change_note,
        published_at=version.published_at,
        published_by=PersonRef(id=person.id, name=person.name) if person is not None else None,
        retired_at=version.retired_at,
    )


def get_definition(*, agent_key: str) -> AgentDefinitionDetail:
    """`GET /agent-definitions/{agentKey}`: the definition and its versions, newest first."""
    agent = _definitions().filter(key=agent_key).first()  # ordering: key is unique, at most one row
    if agent is None:
        raise not_found()
    versions = agent.versions.select_related("published_by").order_by("-version_number")
    return AgentDefinitionDetail.model_validate(
        {**AgentDefinitionOut.model_validate(agent).model_dump(), "versions": [version_row(row) for row in versions]}
    )


def platform_person(who: Principal) -> tuple[Actor, uuid.UUID]:
    """The platform administrator behind the session, by name (playbook 4.7)."""
    person = User.objects.filter(pk=who.subject_id).first()  # ordering: pk lookup, at most one row
    if person is None:  # pragma: no cover - the session was resolved from this person a moment ago
        raise ProblemError(status=401, code="unauthenticated", detail="Sign in to continue.")
    return Actor(kind=ActorType.USER, id=person.id, label=person.name), person.id


def _unreadable(agent: Agent, version_no: int, reason: str) -> ValidationError:
    return ValidationError(
        f"agents/{agent.key}/v{version_no}/definition.yaml cannot be published: {reason}",
        code="definition_unreadable",
    )


def _shipped(agent: Agent, version_no: int) -> reader.Definition:
    """The version folder as the seed's reader reads it, refused unless it is this agent's
    next version and keeps what the agent is. The detail names the folder inside the
    build, never where the server keeps it."""
    folder = reader.DEFINITIONS / agent.key / f"v{version_no}"
    try:
        shipped = reader.read_definition(folder / "definition.yaml")
    except FileNotFoundError:
        raise _unreadable(agent, version_no, "this build ships no such file.") from None
    except reader.DefinitionError as error:
        raise _unreadable(agent, version_no, str(error).replace(f"{folder / 'definition.yaml'}", "").lstrip(": ")) from None
    stored = (agent.key, version_no, agent.kind, agent.scope, agent.tenant_configurable, agent.writes_to)
    read = (shipped.key, shipped.version, shipped.kind, shipped.scope, shipped.tenant_configurable, shipped.writes_to)
    if read != stored:
        # A version changes what the agent does, never whose it is or where it writes.
        raise _unreadable(agent, version_no, "its id, version, kind, scope or zone is not this agent's.")
    if not (folder / shipped.prompt).is_file():
        raise _unreadable(agent, version_no, f"its prompt {shipped.prompt} is not in the folder.")
    return shipped


def publish_version(*, who: Principal, agent_key: str, body: AgentVersionInput) -> AgentVersionOut:
    """`POST /agent-definitions/{agentKey}/versions`: publish the next shipped version. The
    agent's row is locked first, so a concurrent publish answers `version_exists`."""
    actor, person_id = platform_person(who)
    with transaction.atomic():
        agent = _agent(agent_key, lock=True)
        published = list(agent.versions.values_list("version_number", flat=True))
        if body.version_no in published:
            raise ProblemError(
                status=409, code="version_exists", detail=f"Version {body.version_no} is already published."
            )
        expected = max(published, default=0) + 1
        if body.version_no != expected:
            raise ValidationError(f"Publish version {expected} next.", code="version_not_next")
        shipped = _shipped(agent, body.version_no)
        before = {"currentVersion": agent.current_version}
        version = console.publish(agent, shipped, change_note=body.change_note, published_by_id=person_id)
        record(
            action="agent_version.published",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=version.id,
            subject_title=f"{agent.key} v{version.version_number}",
            summary=f"Version {version.version_number} of agent {agent.key} published.",
            tenant_id=None,
            before=before,
            after={
                "currentVersion": agent.current_version,
                "versionNo": version.version_number,
                "model": version.model,
                "tools": version.tools,
            },
            step_up_assertion_id=who.step_up_assertion_id,
        )
    return version_row(AgentVersion.objects.select_related("published_by").get(pk=version.pk))


def retire_version(*, who: Principal, agent_key: str, version_no: int) -> AgentVersionOut:
    """`POST /agent-definitions/{agentKey}/versions/{versionNo}/retire`: stop new runs on one
    version. A retired version answers as it is; the last one still published of an active
    agent is refused, because the agent would have nothing left to run."""
    actor, _ = platform_person(who)
    with transaction.atomic():
        agent = _agent(agent_key, lock=True)
        version = agent.versions.select_related("published_by").filter(version_number=version_no).first()  # ordering: unique per agent
        if version is None:
            raise not_found()
        if version.retired_at is not None:
            return version_row(version)
        if agent.active and not agent.versions.filter(retired_at__isnull=True).exclude(pk=version.pk).exists():
            raise ProblemError(
                status=409,
                code="last_version",
                detail="This is the agent's last published version. Publish another before retiring it.",
            )
        console.retire(version)
        record(
            action="agent_version.retired",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=version.id,
            subject_title=f"{agent.key} v{version.version_number}",
            summary=f"Version {version.version_number} of agent {agent.key} retired.",
            tenant_id=None,
            before={"retiredAt": None},
            after={"retiredAt": version.retired_at.isoformat() if version.retired_at else None},
            step_up_assertion_id=who.step_up_assertion_id,
        )
    return version_row(version)


def version_to_run(agent_id: uuid.UUID) -> uuid.UUID | None:
    """The version a run of this agent opens with (AGT-06): its newest published one; all
    retired is 409 `no_published_version`. None only for a pre-versioning definition."""
    versions = AgentVersion.objects.filter(agent_id=agent_id)
    newest = versions.filter(retired_at__isnull=True).order_by("-version_number").values_list("id", flat=True).first()
    if newest is None and versions.exists():
        raise ProblemError(
            status=409,
            code="no_published_version",
            detail="Every version of this agent is retired, so no run can start. A platform administrator publishes one.",
        )
    return newest
