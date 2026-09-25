"""The platform's agent definitions and their versions (AGT-03, ID-10).

The list is served: what a platform administrator binds a key to, with each definition's
scope and when its current version was published. One definition's detail, publishing a
version and retiring one answer 501 `not_built` behind their routes' real gates until
`c11-agent-definitions` and `c11-platform-agent-settings` fill them. A published version is
never rewritten; retiring one only stops new runs.
"""

from __future__ import annotations

from typing import NoReturn

from django.db.models import OuterRef, Subquery

from apps.agents.models import Agent, AgentVersion
from apps.agents.schemas import AgentDefinitionOut, AgentDefinitionPage, AgentVersionInput
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError


def list_definitions(*, limit: int, offset: int) -> AgentDefinitionPage:
    """Every definition by key, one page at a time, the same for every bank."""
    published = AgentVersion.objects.filter(agent=OuterRef("pk"), version_number=OuterRef("current_version"))
    queryset = Agent.objects.annotate(published_at=Subquery(published.values("published_at")[:1])).order_by("key", "id")
    return AgentDefinitionPage(
        items=[AgentDefinitionOut.model_validate(row) for row in queryset[offset : offset + limit]],
        total=queryset.count(),
    )


def get_definition(*, agent_key: str) -> NoReturn:
    """`GET /agent-definitions/{agentKey}`. Built by `c11-agent-definitions`."""
    raise ProblemError(status=501, code="not_built", detail="Reading one agent definition is not built yet.")


def publish_version(*, who: Principal, agent_key: str, body: AgentVersionInput) -> NoReturn:
    """`POST /agent-definitions/{agentKey}/versions`. Built by `c11-platform-agent-settings`."""
    raise ProblemError(status=501, code="not_built", detail="Publishing an agent version is not built yet.")


def retire_version(*, who: Principal, agent_key: str, version_no: int) -> NoReturn:
    """`POST /agent-definitions/{agentKey}/versions/{versionNo}/retire`. Built by
    `c11-platform-agent-settings`."""
    raise ProblemError(status=501, code="not_built", detail="Retiring an agent version is not built yet.")
