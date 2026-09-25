"""Research requests (AGT-05, ADR 0053): a bank asks its own agents to run now, check a
source or an address, or research a topic; re-tagging library records is asked in the
console and answered by a batch proposal, never a direct edit. Each loads what it names
under row-level security first, then answers 501 `not_built` until `c11-research-requests`
fills it. The topic is a bank's own text: nothing here logs it."""

from __future__ import annotations

import uuid
from typing import NoReturn

from apps.agents.models import ResearchRequest
from apps.agents.schemas import ResearchRequestInput, RetagRequestInput
from apps.agents.tenant_agents import own_agent
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant


def list_requests(*, tenant: Tenant, limit: int, offset: int) -> NoReturn:
    """`GET /research-requests`. Built by `c11-research-requests`."""
    raise ProblemError(status=501, code="not_built", detail="Listing research requests is not built yet.")


def create_request(*, who: Principal, tenant: Tenant, body: ResearchRequestInput) -> NoReturn:
    """`POST /research-requests`. Built by `c11-research-requests`."""
    own_agent(body.tenant_agent_id)
    raise ProblemError(status=501, code="not_built", detail="Asking an agent for research is not built yet.")


def get_request(*, tenant: Tenant, request_id: uuid.UUID) -> NoReturn:
    """`GET /research-requests/{requestId}`. The table is mixed (a console re-tag has no
    tenant), so the bank's own rows are asked for by name as well as under row-level
    security. Built by `c11-research-requests`."""
    if not ResearchRequest.objects.filter(pk=request_id, tenant=tenant).exists():
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    raise ProblemError(status=501, code="not_built", detail="Reading a research request is not built yet.")


def create_retag(*, who: Principal, body: RetagRequestInput) -> NoReturn:
    """`POST /console/research-requests`. Built by `c11-research-requests`."""
    raise ProblemError(status=501, code="not_built", detail="Asking for a re-tag is not built yet.")
