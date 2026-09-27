"""Request and response schemas of the integrations app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1)."""

from typing import Any, Literal

from pydantic import ConfigDict, Field, JsonValue

from apps.shared.schemas import CamelSchema, LibraryResponse

__all__ = ["CamelSchema"]


# ---------------------------------------------------------------------------------------
# acc-mcp-transport: the JSON-RPC 2.0 messages POST /mcp answers (ACC-05, MCP 2026-07-28
# and 2025-11-25). The names on the wire are the protocol's own; apps/integrations/mcp.py
# builds every answer from these, so the contract and the server cannot drift.
# ---------------------------------------------------------------------------------------
class McpImplementation(LibraryResponse):
    """The server's name and version, as MCP reports an implementation."""

    name: str = Field(description="The server's name, the same for every bank: the product's own name followed by MCP.")
    version: str = Field(description="The version of this server's MCP implementation, which moves when its tools or behaviour change.")


class McpToolsCapability(LibraryResponse):
    """What the server offers about tools beyond listing them."""

    list_changed: bool = Field(
        description=(
            "Whether the server sends a notification when the tool list changes. Always false: the list is "
            "worked out afresh on every request from the credential presented, so a client re-reads it instead."
        )
    )


class McpServerCapabilities(LibraryResponse):
    """The protocol features this server offers: tools, and nothing else."""

    tools: McpToolsCapability = Field(description="The server offers tools, the only feature it has; there are no resources or prompts.")


class McpToolProperty(LibraryResponse):
    """One argument a tool takes, written as JSON Schema."""

    type: Literal["string", "integer"] = Field(description="The argument's JSON type: `string` for text or a date, `integer` for a whole number.")
    description: str = Field(description="What the argument means, in a sentence a model can act on.")
    format: Literal["date"] | None = Field(
        default=None, description="Set to `date` when a string argument is a calendar date written YYYY-MM-DD; absent otherwise."
    )
    minimum: int | None = Field(default=None, description="The smallest whole number the argument accepts; absent when it is not a number.")
    maximum: int | None = Field(default=None, description="The largest whole number the argument accepts; absent when it is not a number.")
    default: int | None = Field(default=None, description="The whole number used when the argument is left out; absent when there is none.")


class McpToolInputSchema(LibraryResponse):
    """The arguments a tool takes, as a JSON Schema object."""

    type: Literal["object"] = Field(description="Always `object`: a tool's arguments are one JSON object.")
    properties: dict[str, McpToolProperty] = Field(description="Each argument the tool takes, by its name; an empty object when it takes none.")
    required: list[str] = Field(description="The names of the arguments a call must give; an empty list when every one may be left out.")
    additional_properties: bool = Field(description="Always false: an argument the tool does not name is refused rather than ignored.")


class McpToolAnnotations(LibraryResponse):
    """Hints about how a tool behaves, for the client to show its user."""

    read_only_hint: bool = Field(description="Always true: every tool here reads and none changes anything, because every agent access credential is read-only.")
    open_world_hint: bool = Field(description="Always false: a tool reads only this service's own records and never reaches another system.")


class McpTool(LibraryResponse):
    """One tool the credential may call, as tools/list describes it."""

    name: str = Field(description="The tool's name, which a tools/call request names; it never changes once published.")
    title: str = Field(description="A short name for the tool, for a person reading the client's list.")
    description: str = Field(description="What the tool returns and when to call it, written for the model that decides.")
    input_schema: McpToolInputSchema = Field(description="The arguments the tool takes, as a JSON Schema object.")
    annotations: McpToolAnnotations = Field(description="Hints about the tool's behaviour: every tool reads only this service.")


class McpTextContent(LibraryResponse):
    """One block of a tool's answer, as text."""

    type: Literal["text"] = Field(description="Always `text`: every tool answers one text block.")
    text: str = Field(description="The tool's answer as JSON text, the same JSON as `structuredContent`, for a client that reads only text.")


class McpResultMeta(LibraryResponse):
    """Protocol metadata on a result of the current revision."""

    server_info: McpImplementation = Field(
        serialization_alias="io.modelcontextprotocol/serverInfo", description="The server's name and version, repeated on every result because no request relies on an earlier one."
    )


class McpResult(LibraryResponse):
    """The result of a request. Which fields it carries depends on the method: `initialize`
    answers protocolVersion, capabilities, serverInfo and instructions; `server/discover`
    answers supportedVersions, capabilities and instructions; `tools/list` answers tools;
    `tools/call` answers content, structuredContent and isError; a `ping` answers an empty
    object."""

    result_type: Literal["complete"] | None = Field(
        default=None, description="Always `complete` on a result of revision 2026-07-28; absent on a result of an earlier revision, which a client reads as complete."
    )
    protocol_version: str | None = Field(
        default=None,
        description=(
            "On an `initialize` result only: the protocol revision this server speaks with the client, the one it asked "
            "for when this server supports it and otherwise the latest revision this server supports that uses `initialize`."
        ),
    )
    supported_versions: list[str] | None = Field(
        default=None, description="On a `server/discover` result only: every protocol revision this server accepts, newest first."
    )
    capabilities: McpServerCapabilities | None = Field(default=None, description="On `initialize` and `server/discover`: the features this server offers, tools only.")
    server_info: McpImplementation | None = Field(default=None, description="On an `initialize` result only: the server's name and version.")
    instructions: str | None = Field(default=None, description="On `initialize` and `server/discover`: a paragraph telling the model what this server is for and what it will not do.")
    tools: list[McpTool] | None = Field(
        default=None,
        description=(
            "On a `tools/list` result only: every tool this credential may call, always in the same order and all on one "
            "page. The list follows the credential: a tool appears only when the credential holds the scope its route "
            "needs, and the register tool only when it also reaches the bank's register."
        ),
    )
    content: list[McpTextContent] | None = Field(
        default=None, description="On a `tools/call` result only: the answer as one text block holding the same JSON as `structuredContent`."
    )
    structured_content: JsonValue = Field(
        default=None,
        description=(
            "On a `tools/call` result only: exactly the body the REST route behind the tool answers, the same "
            "gates, scope and pagination included; when `isError` is true, the route's problem details, whose "
            "`code` is the one to branch on (`permission_denied`, `not_found`, `tenant_reach_off`, "
            "`read_only_credential`, `validation_error` and the others the route names). On revision "
            "2025-11-25 and 2025-06-18 an answer that is a list arrives as the object `{\"items\": [...]}`, "
            "because those revisions take only an object here."
        ),
    )
    is_error: bool | None = Field(
        default=None,
        description="On a `tools/call` result only: true when the route refused the call or an argument was wrong, false when it answered.",
    )
    ttl_ms: int | None = Field(
        default=None,
        description="On a `tools/list` or `server/discover` result of revision 2026-07-28: how many milliseconds a client may reuse it. Always 0, because the list can change with the credential's entry at any moment.",
    )
    cache_scope: Literal["private"] | None = Field(
        default=None,
        description="On a `tools/list` or `server/discover` result of revision 2026-07-28: always `private`, because the answer belongs to one credential and a shared cache may not keep it.",
    )
    meta: McpResultMeta | None = Field(default=None, serialization_alias="_meta", description="On a result of revision 2026-07-28: the protocol metadata, which names the server.")


class McpErrorData(LibraryResponse):
    """Detail on an unsupported protocol revision."""

    supported: list[str] = Field(description="Every protocol revision this server accepts, newest first; retry with one of them.")
    requested: str | None = Field(description="The revision the request asked for, or null when it named none.")


class McpError(LibraryResponse):
    """Why a request failed, as a JSON-RPC error."""

    code: int = Field(
        description=(
            "The JSON-RPC error code to branch on: -32700 the body is not JSON; -32600 the message is not one "
            "JSON-RPC request, a batch included; -32601 the method is not one this server offers; -32602 the "
            "parameters are wrong or the protocol metadata is missing; -32020 an MCP header does not match the body; "
            "-32022 the protocol revision is not supported."
        )
    )
    message: str = Field(description="A sentence saying what was wrong, for a developer's log; branch on the code, never on this text.")
    data: McpErrorData | None = Field(default=None, description="On -32022 only: the revisions this server accepts and the one asked for.")


_MCP_RESULT_EXAMPLE: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "resultType": "complete",
        "tools": [
            {
                "name": "get_obligation",
                "title": "Read one obligation",
                "description": "One obligation of the shared library in this credential's scope, by its stable key.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"stableKey": {"type": "string", "description": "The obligation's stable key."}},
                    "required": ["stableKey"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "openWorldHint": False},
            }
        ],
        "ttlMs": 0,
        "cacheScope": "private",
        "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "bleqq MCP", "version": "1.0.0"}},
    },
}


class McpMessage(LibraryResponse):
    """One JSON-RPC 2.0 response: a result, or an error, never both."""

    model_config = ConfigDict(json_schema_extra={"examples": [_MCP_RESULT_EXAMPLE]})

    jsonrpc: Literal["2.0"] = Field(description="Always `2.0`, the JSON-RPC version.")
    id: int | str | None = Field(default=None, description="The id of the request answered; absent on an error about a message whose id could not be read.")
    result: McpResult | None = Field(default=None, description="The result when the request succeeded; absent on an error.")
    error: McpError | None = Field(default=None, description="The error when the request failed; absent on a result.")
