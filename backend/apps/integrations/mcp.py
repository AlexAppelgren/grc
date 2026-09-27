"""The MCP server a bank's own agents read through (ACC-05, ADR 0055): one endpoint,
`POST /mcp`, speaking JSON-RPC 2.0 over Streamable HTTP, hand-written on the standard
library with no MCP dependency (ADR 0019 pins).

Stateless in both protocol eras it serves (docs/plans/Verification_Log.md, 2026-09-25):

- Revision 2026-07-28, the current one, has no handshake: every request carries its
  revision and client capabilities in `params._meta`, mirrored in the
  `MCP-Protocol-Version` and `Mcp-Method` headers, which must match the body.
  `server/discover` and `tools/list` are its methods here.
- Revisions 2025-11-25 and 2025-06-18 open with `initialize`, which this server answers
  without minting a session, then carry the revision in `MCP-Protocol-Version` alone.
  `ping` and `tools/list` are their methods here.

A body is untrusted input: it is parsed here, never by a schema that answers 422, so a
malformed message gets the JSON-RPC error the protocol names. A batch is refused. The tool
list follows the credential (the tools themselves are served by `tools/call`, which is not
built yet and answers method not found).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.shared import permissions as perms
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError

from apps.integrations.schemas import (
    McpError,
    McpErrorData,
    McpImplementation,
    McpMessage,
    McpResult,
    McpResultMeta,
    McpServerCapabilities,
    McpTool,
    McpToolAnnotations,
    McpToolInputSchema,
    McpToolProperty,
    McpToolsCapability,
)

MODERN_VERSIONS: tuple[str, ...] = ("2026-07-28",)
LEGACY_VERSIONS: tuple[str, ...] = ("2025-11-25", "2025-06-18")
SUPPORTED_VERSIONS: tuple[str, ...] = MODERN_VERSIONS + LEGACY_VERSIONS
# What the spec says a server assumes when a request names no revision at all.
UNNAMED_VERSION = "2025-03-26"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
# A notification needs no answer; these two are the ones a client of an earlier revision sends.
ACCEPTED_NOTIFICATIONS = frozenset({"notifications/initialized", "notifications/cancelled"})

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
HEADER_MISMATCH = -32020
UNSUPPORTED_VERSION = -32022

SERVER_VERSION = "1.0.0"
INSTRUCTIONS = (
    "Reads the shared library of Nordic and EU financial regulation, in the scope of the agent this "
    "credential belongs to, and, where the bank has allowed it, the bank's own register decisions. "
    "Every tool reads; nothing here changes anything. An answer states the scope it was answered in, "
    "and a record outside that scope is not found."
)


@dataclass(frozen=True)
class Answer:
    """An HTTP status and the JSON-RPC message to send, or none for an accepted notification."""

    status: int
    message: McpMessage | None


# ---------------------------------------------------------------------------------------
# The tools, in the order tools/list gives them. Each names the scope its route needs;
# the register tool also needs the entry's reach into the bank's register (ACC-04, D-72).
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolSpec:
    tool: McpTool
    scope: str
    needs_reach: bool = False


def _object(properties: dict[str, McpToolProperty], required: list[str] | None = None) -> McpToolInputSchema:
    return McpToolInputSchema(type="object", properties=properties, required=required or [], additional_properties=False)


def _tool(name: str, title: str, description: str, schema: McpToolInputSchema) -> McpTool:
    return McpTool(
        name=name,
        title=title,
        description=description,
        input_schema=schema,
        annotations=McpToolAnnotations(read_only_hint=True, open_world_hint=False),
    )


_LIMIT = McpToolProperty(
    type="integer",
    description=f"How many records to return: {settings.API_PAGE_SIZE_DEFAULT} unless given, {settings.API_PAGE_SIZE_MAX} at most.",
    minimum=1,
    maximum=settings.API_PAGE_SIZE_MAX,
    default=settings.API_PAGE_SIZE_DEFAULT,
)
_OFFSET = McpToolProperty(type="integer", description="How many records to skip before the page starts.", minimum=0, default=0)
_AS_OF = McpToolProperty(type="string", format="date", description="Read the records as they stood on this date, YYYY-MM-DD; today unless given.")
_PAGE = {"limit": _LIMIT, "offset": _OFFSET}

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        _tool(
            "search",
            "Search the library",
            "Find obligations, provisions and changes in this credential's scope by identifier or by concept, best match first.",
            _object({"query": McpToolProperty(type="string", description="What to look for, in words or as an identifier."), "limit": _LIMIT}, ["query"]),
        ),
        perms.SCOPE_SEARCH_READ,
    ),
    ToolSpec(
        _tool(
            "list_obligations",
            "List obligations",
            "The obligations of the shared library in this credential's scope, ordered by stable key, a page at a time.",
            _object({"asOf": _AS_OF, **_PAGE}),
        ),
        perms.SCOPE_LIBRARY_READ,
    ),
    ToolSpec(
        _tool(
            "get_obligation",
            "Read one obligation",
            "One obligation of the shared library in this credential's scope, by its stable key, with its versions and provenance.",
            _object({"stableKey": McpToolProperty(type="string", description="The obligation's stable key, which never changes."), "asOf": _AS_OF}, ["stableKey"]),
        ),
        perms.SCOPE_LIBRARY_READ,
    ),
    ToolSpec(
        _tool(
            "list_upcoming_changes",
            "List upcoming changes",
            "Regulatory changes with a date still ahead, earliest first, as public facts of the shared library.",
            _object(dict(_PAGE)),
        ),
        perms.SCOPE_UPCOMING_READ,
    ),
    ToolSpec(
        _tool(
            "list_register_entries",
            "List the bank's register decisions",
            "The bank's own decisions on the obligations in this credential's scope: whether each applies and why, and its compliance status.",
            _object(dict(_PAGE)),
        ),
        perms.SCOPE_TENANT_READ,
        needs_reach=True,
    ),
    ToolSpec(
        _tool(
            "what_applies",
            "Ask what applies",
            "Given what is being built, bought or reviewed, the full list of obligations in scope that match, with the scope it was answered in and what that scope could not see.",
            _object({"description": McpToolProperty(type="string", description="What is being built, bought or reviewed, in a few sentences.")}, ["description"]),
        ),
        perms.SCOPE_LIBRARY_READ,
    ),
)


def reaches_register(principal: Principal) -> bool:
    """The entry's half of tenant reach (D-72): a credential bound to no entry never reaches
    the register. The bank's own switch is apps/governance's, and the register route checks
    both on every call."""
    from apps.agents.models import AgentAccess

    if principal.agent_access_id is None:
        return False
    return AgentAccess.objects.filter(pk=principal.agent_access_id, active=True, tenant_reach=True).exists()


def tools_for(principal: Principal) -> list[McpTool]:
    reach: bool | None = None
    offered: list[McpTool] = []
    for spec in TOOLS:
        if not principal.has_scope(spec.scope):
            continue
        if spec.needs_reach:
            reach = reaches_register(principal) if reach is None else reach
            if not reach:
                continue
        offered.append(spec.tool)
    return offered


# ---------------------------------------------------------------------------------------
# The transport
# ---------------------------------------------------------------------------------------
def _server_info() -> McpImplementation:
    return McpImplementation(name=f"{settings.PRODUCT_NAME} MCP", version=SERVER_VERSION)


def _capabilities() -> McpServerCapabilities:
    return McpServerCapabilities(tools=McpToolsCapability(list_changed=False))


def _error(status: int, request_id: int | str | None, code: int, message: str, data: McpErrorData | None = None) -> Answer:
    return Answer(status, McpMessage(jsonrpc="2.0", id=request_id, error=McpError(code=code, message=message, data=data)))


def _unsupported(request_id: int | str | None, requested: str | None) -> Answer:
    return _error(400, request_id, UNSUPPORTED_VERSION, "Unsupported protocol version", McpErrorData(supported=list(SUPPORTED_VERSIONS), requested=requested))


def _valid_id(value: object) -> bool:
    # JSON-RPC as MCP narrows it: a string or an integer, never null, a float or a boolean.
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def handle(body: bytes, headers: Mapping[str, str], principal: Principal) -> Answer:
    """Answer one POSTed JSON-RPC message. Only an agent access credential is served: a
    bank's other keys and bleqq's own agents have the REST API and no business here. A
    browser's `Origin` other than the app's own is refused, as the transport requires
    against DNS rebinding."""
    if not principal.is_agent_access:
        raise ProblemError(
            status=403, code="agent_access_only", detail="The MCP server serves the key of an agent access entry or a personal access token."
        )
    origin = headers.get("Origin")
    if origin is not None and origin not in settings.CORS_ALLOWED_ORIGINS:
        return _error(403, None, INVALID_REQUEST, "This origin may not call the MCP server.")
    try:
        message: Any = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return _error(400, None, PARSE_ERROR, "The body is not UTF-8 JSON.")
    if isinstance(message, list):
        return _error(400, None, INVALID_REQUEST, "Batches are not accepted; send one message per request.")
    if not isinstance(message, dict):
        return _error(400, None, INVALID_REQUEST, "The body is not a JSON-RPC message.")
    has_id = "id" in message
    request_id = message.get("id")
    if has_id and not _valid_id(request_id):
        return _error(400, None, INVALID_REQUEST, "The id must be a string or an integer.")
    method = message.get("method")
    params = message.get("params", {})
    if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
        # A client sends requests and notifications only, never a response.
        return _error(400, request_id if has_id else None, INVALID_REQUEST, "The body is not a JSON-RPC 2.0 request or notification.")
    if not isinstance(params, dict):
        return _error(400, request_id if has_id else None, INVALID_PARAMS, "params must be an object.")
    if not has_id:
        if method in ACCEPTED_NOTIFICATIONS:
            return Answer(202, None)
        return _error(400, None, METHOD_NOT_FOUND, "This notification is not accepted.")
    if method == "initialize":
        return _initialize(request_id, params)
    return _request(request_id, method, params, headers, principal)


def _initialize(request_id: int | str | None, params: dict[str, Any]) -> Answer:
    """The earlier revisions' handshake, answered without a session: the version the client
    asked for when it is supported, else the latest one that has a handshake."""
    asked = params.get("protocolVersion")
    if not isinstance(asked, str):
        return _error(200, request_id, INVALID_PARAMS, "initialize needs a protocolVersion string.")
    agreed = asked if asked in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
    result = McpResult(protocol_version=agreed, capabilities=_capabilities(), server_info=_server_info(), instructions=INSTRUCTIONS)
    return Answer(200, McpMessage(jsonrpc="2.0", id=request_id, result=result))


def _request(request_id: int | str | None, method: str, params: dict[str, Any], headers: Mapping[str, str], principal: Principal) -> Answer:
    header_version = headers.get("MCP-Protocol-Version")
    meta = params.get("_meta")
    meta = meta if isinstance(meta, dict) else {}
    body_version = meta.get(META_VERSION)
    if body_version is None:
        # An earlier revision: the header names it, or, absent, the spec's default we do not serve.
        version = header_version or UNNAMED_VERSION
        if version in MODERN_VERSIONS:
            return _error(400, request_id, INVALID_PARAMS, f"params._meta must carry {META_VERSION} and {META_CAPABILITIES}.")
        if version not in LEGACY_VERSIONS:
            return _unsupported(request_id, header_version)
        return _legacy(request_id, method, principal)
    if not isinstance(body_version, str):
        return _error(400, request_id, INVALID_PARAMS, f"{META_VERSION} must be a string.")
    if header_version != body_version:
        return _error(400, request_id, HEADER_MISMATCH, "The MCP-Protocol-Version header does not match the body's protocol version.")
    if headers.get("Mcp-Method") != method:
        return _error(400, request_id, HEADER_MISMATCH, "The Mcp-Method header does not match the body's method.")
    if body_version not in MODERN_VERSIONS:
        return _unsupported(request_id, body_version)
    if not isinstance(meta.get(META_CAPABILITIES), dict):
        return _error(400, request_id, INVALID_PARAMS, f"params._meta must carry {META_CAPABILITIES}.")
    return _modern(request_id, method, principal)


def _modern(request_id: int | str | None, method: str, principal: Principal) -> Answer:
    meta = McpResultMeta(server_info=_server_info())
    if method == "server/discover":
        result = McpResult(
            result_type="complete",
            supported_versions=list(SUPPORTED_VERSIONS),
            capabilities=_capabilities(),
            instructions=INSTRUCTIONS,
            ttl_ms=0,
            cache_scope="private",
            meta=meta,
        )
    elif method == "tools/list":
        result = McpResult(result_type="complete", tools=tools_for(principal), ttl_ms=0, cache_scope="private", meta=meta)
    else:
        return _error(404, request_id, METHOD_NOT_FOUND, "Method not found")
    return Answer(200, McpMessage(jsonrpc="2.0", id=request_id, result=result))


def _legacy(request_id: int | str | None, method: str, principal: Principal) -> Answer:
    # An earlier revision reads a 404 as "your session is gone", so its errors travel in a 200.
    if method == "ping":
        result = McpResult()
    elif method == "tools/list":
        result = McpResult(tools=tools_for(principal))
    else:
        return _error(200, request_id, METHOD_NOT_FOUND, "Method not found")
    return Answer(200, McpMessage(jsonrpc="2.0", id=request_id, result=result))
