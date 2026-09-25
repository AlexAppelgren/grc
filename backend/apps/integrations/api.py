"""Routes of the integrations app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1)."""

from django.http import HttpRequest, HttpResponse, JsonResponse
from ninja import Router

from apps.shared.authentication import ApiKeyAuth
from apps.taxonomy.http import principal

from apps.integrations import mcp
from apps.integrations.schemas import McpMessage

router = Router(tags=["Integrations"])

# acc-mcp-transport ----------------------------------------------------------------------
# The body is one JSON-RPC message the server parses itself (apps/integrations/mcp.py), so a
# malformed one gets the protocol's own error rather than a 422; the contract describes it
# here instead of through a schema Ninja would validate.
_MCP_REQUEST_BODY = {
    "requestBody": {
        "required": True,
        "description": (
            "One JSON-RPC 2.0 request or notification, never a batch. `jsonrpc` is always `2.0`; `id` is a string "
            "or an integer, and a message without one is a notification; `method` names the call; `params` is an "
            "object. On revision 2026-07-28, `params._meta` carries `io.modelcontextprotocol/protocolVersion` and "
            "`io.modelcontextprotocol/clientCapabilities`."
        ),
        "content": {
            "application/json": {
                "schema": {"type": "object", "description": "One JSON-RPC 2.0 request or notification."},
                "example": {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {
                        "_meta": {
                            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                            "io.modelcontextprotocol/clientInfo": {"name": "order-routing-agent", "version": "0.4.0"},
                            "io.modelcontextprotocol/clientCapabilities": {},
                        }
                    },
                },
            }
        },
    }
}


@router.post(
    "/mcp",
    response={200: McpMessage, 202: None, 400: McpMessage, 404: McpMessage},
    auth=ApiKeyAuth(),
    operation_id="mcpMessage",
    by_alias=True,
    summary="Let a bank's own agent read through the Model Context Protocol",
    openapi_extra=_MCP_REQUEST_BODY,
)
def mcp_endpoint(request: HttpRequest) -> HttpResponse:
    """The MCP server a bank's own agents read through (ACC-05): one endpoint speaking
    JSON-RPC 2.0 over MCP's Streamable HTTP transport, over the same API and under the same
    gates as the REST routes. Point an MCP client at `/api/v1/mcp` with the credential.

    Who may call it: the key of an agent access entry or a personal access token, as
    `X-API-Key` or as a bearer token. A person's session is not accepted and answers 401
    `unauthenticated`; any other key answers 403 `agent_access_only`. Every such credential
    reads and nothing else, is refused a step-up, and is rate-limited per credential, as
    the `ApiKeyAuth` scheme describes.

    Stateless: each POST carries one message and is answered on its own. The server never
    issues an `Mcp-Session-Id`, ignores one that is sent, and offers no stream, so `GET` and
    `DELETE` answer 405. A batch (a JSON array) is refused with -32600.

    Versions: revision 2026-07-28 sends its version and client capabilities in
    `params._meta` on every request and mirrors them in the `MCP-Protocol-Version` and
    `Mcp-Method` headers, which must match the body (400, -32020, when they do not); its
    methods here are `server/discover` and `tools/list`. Revisions 2025-11-25 and 2025-06-18
    open with `initialize`, which answers the version asked for when it is one of those two
    and otherwise 2025-11-25, then send `MCP-Protocol-Version` on every request; their
    methods here are `ping` and `tools/list`, and `notifications/initialized` answers 202
    with no body. A revision this server does not speak answers 400 with -32022 and the list
    of supported revisions.

    The tool list follows the credential: search needs `search:read`; list_obligations,
    get_obligation and what_applies need `library:read`; list_upcoming_changes needs
    `upcoming:read`; list_register_entries needs `tenant:read` and an entry whose tenant
    reach is on, so a credential without both is not offered it. Calling a tool
    (`tools/call`) is not offered yet and answers -32601.

    Errors: HTTP-level refusals come as RFC 9457 problem details (`unauthenticated`,
    `agent_access_only`, `rate_limited`); everything about the message itself comes as a
    JSON-RPC error: -32700 for a body that is not UTF-8 JSON, -32600 for anything that is not
    one JSON-RPC request or notification, -32601 for an unknown method, -32602 for missing
    or malformed parameters or protocol metadata. A browser `Origin` other than the app's
    own answers 403 with -32600.
    """
    answer = mcp.handle(request.body, request.headers, principal(request))
    if answer.message is None:
        return HttpResponse(status=answer.status)
    return JsonResponse(answer.message.model_dump(mode="json", by_alias=True, exclude_none=True), status=answer.status)
