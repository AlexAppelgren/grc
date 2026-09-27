"""The access log of the agents a bank runs itself (ACC-08, AGENT_ACCESS.md section 9).

Every request an agent access credential makes leaves one `AgentAccessCall` row: the
credential, the entry it reads as, the person a personal token acts as, the tool (the
operation the request reached), the filters, the record count, the scope applied, the time
it took and its status. Never the content (playbook 4.7): a filter is kept as its name, and
its value only when the value is a key; a free-text parameter keeps its name alone.

`begin` is called by the agent access guard once the credential passed its rate limit, so a
refused write or step-up is logged with its 403, while a request refused for its rate is
not: the security log already holds one row per window for it, and a runaway agent must not
flood this one. `AccessLogMiddleware` writes the row after the response, in a transaction of
its own, so a call whose request rolled back is still logged. A route that knows better than
the query string (a read with a body, the MCP server's tool) says so through `note`.

`list_calls` is the entry's log for `GET /agent-access/{id}/calls`.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse

from apps.governance.models import AgentAccessCall
from apps.governance.schemas import AgentAccessCallRow, AgentAccessCallScope, AgentAccessCredentialRef
from apps.shared import tenancy
from apps.shared.authentication import Principal
from apps.taxonomy.schemas import PersonRef

# Parameters whose value is text a caller typed, never a key: the name is kept, the value never.
TEXT_PARAMETERS: frozenset[str] = frozenset({"q", "query", "text", "description", "topic", "question"})
# Paging is not a filter.
PAGING_PARAMETERS: frozenset[str] = frozenset({"limit", "offset"})
# A value kept in the log: a key, a UUID, a date or a number, and nothing with a space in it.
KEY_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
REQUEST_ATTRIBUTE = "agent_access_call"


@dataclass
class PendingCall:
    """What the request knows of its call before the response: filled by `begin`, amended by
    `note`, written by `finish`."""

    principal: Principal
    tool: str
    filters: dict[str, list[str]]
    record_count: int | None = None
    counted: bool = field(default=False)


def _kept(name: str, values: Iterable[str]) -> list[str]:
    if name in TEXT_PARAMETERS:
        return []
    return sorted({value for value in values if KEY_VALUE.match(value)})


def filters_of(request: HttpRequest) -> dict[str, list[str]]:
    """The query string's and the path's parameters as names and key values."""
    kept: dict[str, list[str]] = {}
    for name in request.GET:
        if name not in PAGING_PARAMETERS:
            kept[name] = _kept(name, request.GET.getlist(name))
    match = getattr(request, "resolver_match", None)
    for name, value in (match.kwargs if match is not None else {}).items():
        kept[name] = _kept(name, [str(value)])
    return kept


def begin(request: HttpRequest, principal: Principal, tool: str) -> None:
    """Start the log of this request's call, once: a request resolved by two auth classes is
    still one call."""
    if getattr(request, REQUEST_ATTRIBUTE, None) is None:
        setattr(request, REQUEST_ATTRIBUTE, PendingCall(principal=principal, tool=tool, filters=filters_of(request)))


def note(
    request: HttpRequest, *, tool: str | None = None, filters: dict[str, list[str]] | None = None, record_count: int | None = None
) -> None:
    """A route's own word on its call: the tool it served, the filters of a body it read
    (names and keys only, the caller's text never) and how many records it answered."""
    pending: PendingCall | None = getattr(request, REQUEST_ATTRIBUTE, None)
    if pending is None:
        return
    if tool is not None:
        pending.tool = tool
    if filters is not None:
        pending.filters.update({name: _kept(name, values) for name, values in filters.items()})
    if record_count is not None:
        pending.record_count = record_count
        pending.counted = True


def _counted(response: HttpResponse) -> int | None:
    """How many records a successful JSON answer carried: a page's items, a list's length,
    or one record. The body is counted and dropped, never kept."""
    if response.status_code >= 300 or getattr(response, "streaming", False):
        return None
    if not response.get("Content-Type", "").startswith("application/json"):
        return None
    try:
        body = json.loads(response.content or b"null")
    except ValueError:
        return None
    if isinstance(body, dict) and isinstance(body.get("items"), list):
        return len(body["items"])
    if isinstance(body, list):
        return len(body)
    return 1 if isinstance(body, dict) else None


def _scope(principal: Principal) -> tuple[bool, dict[str, list[str]]]:
    if principal.agent_access_id is None or principal.tenant_id is None:
        return False, {}
    from apps.taxonomy import entry_scope

    scope = entry_scope.scope_of(principal.tenant_id, principal.agent_access_id)
    return scope.narrowed, {dimension: sorted(keys) for dimension, keys in sorted(scope.terms.items())}


def finish(request: HttpRequest, response: HttpResponse, duration_ms: int) -> None:
    """Write the call's row, in its credential's own bank. A request no credential began
    writes nothing."""
    pending: PendingCall | None = getattr(request, REQUEST_ATTRIBUTE, None)
    tenant_id = pending.principal.tenant_id if pending is not None else None
    if pending is None or tenant_id is None:
        return
    principal = pending.principal
    with transaction.atomic():
        tenancy.activate(tenant_id)
        narrowed, terms = _scope(principal)
        AgentAccessCall.objects.create(
            tenant_id=tenant_id,
            api_key_id=principal.subject_id,
            agent_access_id=principal.agent_access_id,
            acting_user_id=principal.acting_user_id,
            tool=pending.tool[:120],
            filters=pending.filters,
            record_count=pending.record_count if pending.counted else _counted(response),
            scopes=sorted(principal.scopes),
            scope_narrowed=narrowed,
            scope_terms=terms,
            duration_ms=duration_ms,
            status=response.status_code,
        )


class AccessLogMiddleware:
    """Times the request and, after the response, writes the access log row of an agent
    access credential's call."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started = time.perf_counter()
        response = self.get_response(request)
        finish(request, response, round((time.perf_counter() - started) * 1000))
        return response


# ---------------------------------------------------------------------------------------
# Reading the log
# ---------------------------------------------------------------------------------------
def list_calls(tenant_id: uuid.UUID, entry_id: uuid.UUID, *, limit: int, offset: int) -> tuple[list[AgentAccessCallRow], int]:
    """The entry's calls, newest first. An entry of another bank, or none, is 404."""
    from apps.agents.models import AgentAccess

    if not AgentAccess.objects.filter(tenant_id=tenant_id, pk=entry_id).exists():
        raise ValidationError("That agent access entry is not here.", code="not_found")
    queryset = AgentAccessCall.objects.filter(tenant_id=tenant_id, agent_access_id=entry_id).select_related("api_key", "acting_user")
    rows = [
        AgentAccessCallRow(
            id=call.id,
            at=call.at,
            credential=AgentAccessCredentialRef(id=call.api_key_id, key_prefix=call.api_key.key_prefix, kind=call.api_key.kind),  # type: ignore[arg-type]
            person=PersonRef(id=call.acting_user.id, name=call.acting_user.name) if call.acting_user is not None else None,
            tool=call.tool,
            filters=call.filters,
            record_count=call.record_count,
            scopes=list(call.scopes),
            scope=AgentAccessCallScope(narrowed=call.scope_narrowed, terms=call.scope_terms),
            duration_ms=call.duration_ms,
            status=call.status,
        )
        for call in queryset[offset : offset + limit]
    ]
    return rows, queryset.count()
