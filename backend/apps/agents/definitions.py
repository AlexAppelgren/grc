"""The platform's agent definitions and their versions (AGT-03, ADM-02, ID-10).

The list is what a platform administrator binds a key to; one definition's detail carries
every version it published. A published version is never rewritten: a run points at the
version it opened with (`runs.open_run`, `version_to_run`), and retiring one only stops new
runs.

Publishing and retiring answer 501 until Alex decides how the console may write a
library row (docs/TODO_FOR_alex.md, c11-definitions-platform): the library fence lets only a
proposal's approval reach one.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from django.db.models import OuterRef, QuerySet, Subquery

from apps.agents.models import Agent, AgentVersion
from apps.agents.schemas import (
    AgentDefinitionDetail,
    AgentDefinitionOut,
    AgentDefinitionPage,
    AgentVersionInput,
    AgentVersionOut,
)
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.taxonomy.schemas import PersonRef


def _definitions() -> QuerySet[Agent]:
    published = AgentVersion.objects.filter(agent=OuterRef("pk"), version_no=OuterRef("current_version"))
    return Agent.objects.annotate(published_at=Subquery(published.values("published_at")[:1])).order_by("key", "id")


def list_definitions(*, limit: int, offset: int) -> AgentDefinitionPage:
    """Every definition by key, one page at a time, the same for every bank."""
    queryset = _definitions()
    return AgentDefinitionPage(
        items=[AgentDefinitionOut.model_validate(row) for row in queryset[offset : offset + limit]],
        total=queryset.count(),
    )


def version_row(version: AgentVersion) -> AgentVersionOut:
    person = version.published_by
    return AgentVersionOut(
        version_no=version.version_no,
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
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    versions = agent.versions.select_related("published_by").order_by("-version_no")
    return AgentDefinitionDetail.model_validate(
        {**AgentDefinitionOut.model_validate(agent).model_dump(), "versions": [version_row(row) for row in versions]}
    )


def publish_version(*, who: Principal, agent_key: str, body: AgentVersionInput) -> NoReturn:
    """`POST /agent-definitions/{agentKey}/versions`. Waits on a decision: `agent_version`
    is a library row, and the library fence lets no route but a proposal's approval, gated
    by `proposals.review`, reach a library write (CLAUDE.md section 5). docs/TODO_FOR_alex.md,
    c11-definitions-platform."""
    raise ProblemError(status=501, code="not_built", detail="Publishing an agent version is not built yet.")


def retire_version(*, who: Principal, agent_key: str, version_no: int) -> NoReturn:
    """`POST /agent-definitions/{agentKey}/versions/{versionNo}/retire`. Waits on the same
    decision as `publish_version`."""
    raise ProblemError(status=501, code="not_built", detail="Retiring an agent version is not built yet.")


def version_to_run(agent_id: uuid.UUID) -> uuid.UUID | None:
    """The version a run of this agent opens with (AGT-06): its newest one still published.
    Every version retired is 409 `no_published_version`, since a retired version starts no
    new run. None for a definition that has never had a version row, which only a build
    older than agents 0004 left behind."""
    versions = AgentVersion.objects.filter(agent_id=agent_id)
    newest = versions.filter(retired_at__isnull=True).order_by("-version_no").values_list("id", flat=True).first()
    if newest is None and versions.exists():
        raise ProblemError(
            status=409,
            code="no_published_version",
            detail="Every version of this agent is retired, so no run can start. A platform administrator publishes one.",
        )
    return newest
