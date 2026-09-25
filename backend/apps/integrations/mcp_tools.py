"""The six tools `tools/call` serves (ACC-05, AGENT_ACCESS.md section 6): each one is the
REST route behind it, run as a request of its own, so the server adds no read path.

The call becomes a request to the route: the tool's arguments go to the route's query
string, body or path, and the credential's own headers go with them. Django resolves it and
the route runs as it does over HTTP, through the same authentication class, the same agent
access fence (`read_only_credential`, `step_up_required`), the same scope gate, the same
logic and the same pagination. Only the rate is not spent twice: the MCP request already
spent it (`agent_access_guard.TOOL_CALL`).

The route's answer comes back as it is: a 2xx body is the structured content, and a
problem is a tool error whose structured content is the problem, code included. A tool name
this server does not have, or a call that is not shaped as one, is the protocol error
-32602; an argument the tool does not declare, or one of the wrong type, is a tool error
the model can correct, as the specification asks (Verification_Log, 2026-09-25).

The access log (ACC-08) keeps one row per MCP request: it names the tool, and takes the
filters, the record count and the status from the route's own call.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from django.core.handlers.wsgi import WSGIRequest
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.urls import Resolver404, resolve

from apps.governance import access_log
from apps.integrations.schemas import McpTool
from apps.shared import agent_access_guard
from apps.shared.errors import ProblemError


@dataclass(frozen=True)
class Route:
    """The REST route behind a tool, as Ninja registers it under /api/v1, and where each
    argument goes: `query` names the ones sent as they are, `body` and `path_args` map an
    argument to the body field or the path parameter it fills."""

    method: str
    path: str
    query: tuple[str, ...] = ()
    body: dict[str, str] = field(default_factory=dict)
    path_args: dict[str, str] = field(default_factory=dict)


ROUTES: dict[str, Route] = {
    "search": Route("POST", "/search", body={"query": "q", "limit": "limit"}),
    "list_obligations": Route("GET", "/obligations", query=("asOf", "limit", "offset")),
    "get_obligation": Route("GET", "/obligations/{obligation_id}", query=("asOf",), path_args={"stableKey": "obligation_id"}),
    "list_upcoming_changes": Route("GET", "/upcoming", query=("limit", "offset")),
    "list_register_entries": Route("GET", "/register-entries", query=("limit", "offset")),
    "what_applies": Route("POST", "/agent-access/what-applies", query=("limit", "offset"), body={"description": "description"}),
}


@dataclass(frozen=True)
class Outcome:
    """What the route answered: its parsed body, and whether it was a refusal."""

    body: Any
    is_error: bool


def _refused(argument: str, message: str) -> Outcome:
    problem = ProblemError(status=422, code="validation_error", detail="Some fields need attention.", errors=[{"field": argument, "message": message}])
    return Outcome(problem.as_dict(), True)


def _scalar(value: object) -> str | None:
    """A query or path value: a string, or a whole number written out; anything else is refused."""
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return None


def _request(outer: HttpRequest, route: Route, path: str, query: dict[str, str], body: dict[str, Any] | None) -> WSGIRequest:
    data = b"" if body is None else json.dumps(body).encode("utf-8")
    environ = {
        **outer.META,
        "REQUEST_METHOD": route.method,
        "SCRIPT_NAME": "",
        # WSGI carries the path as UTF-8 bytes read as Latin-1.
        "PATH_INFO": f"/{agent_access_guard.API_ROUTE_PREFIX}{path.lstrip('/')}".encode().decode("iso-8859-1"),
        "QUERY_STRING": urlencode(query),
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": io.BytesIO(data),
    }
    return WSGIRequest(environ)


def call(outer: HttpRequest, tool: McpTool, arguments: dict[str, Any]) -> Outcome:
    """Run `tool` for the credential of `outer` with `arguments`, checked against the
    arguments the tool declares."""
    route = ROUTES[tool.name]
    for argument in arguments:
        if argument not in tool.input_schema.properties:
            return _refused(argument, "This tool takes no such argument.")
    for argument in tool.input_schema.required:
        if argument not in arguments:
            return _refused(argument, "This argument is required.")
    query: dict[str, str] = {}
    path = route.path
    for argument, value in arguments.items():
        if argument in route.body:
            continue
        text = _scalar(value)
        if text is None:
            return _refused(argument, "Give a string or a whole number.")
        if argument in route.path_args:
            path = path.replace("{" + route.path_args[argument] + "}", text)
        else:
            query[argument] = text
    body = {route.body[argument]: value for argument, value in arguments.items() if argument in route.body} if route.body else None
    inner = _request(outer, route, path, query, body)
    try:
        inner.resolver_match = resolve(inner.path_info)
    except Resolver404:
        inner.resolver_match = None
    operation = agent_access_guard.operation_of(inner)
    if inner.resolver_match is None or operation is None or (operation.method, operation.path) != (route.method, route.path):
        # A path argument that routes anywhere but the tool's own route: a slash, an empty key.
        return _refused(next(iter(route.path_args), "arguments"), "This is not a key the tool can read by.")
    match = inner.resolver_match
    setattr(inner, agent_access_guard.TOOL_CALL, True)
    with transaction.atomic():
        response: HttpResponse = match.func(inner, *match.args, **match.kwargs)
    pending: access_log.PendingCall | None = getattr(inner, access_log.REQUEST_ATTRIBUTE, None)
    access_log.note(
        outer,
        tool=tool.name,
        filters=pending.filters if pending is not None else {},
        record_count=pending.record_count if pending is not None and pending.counted else None,
        answered=response,
    )
    return Outcome(json.loads(response.content or b"null"), response.status_code >= 400)
