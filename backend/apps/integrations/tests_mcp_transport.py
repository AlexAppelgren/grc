"""The MCP transport (ACC-05, acc-mcp-transport): `POST /mcp` speaks JSON-RPC 2.0 to an agent
access credential and nobody else, statelessly, in the current revision (2026-07-28) and
the two before it, and lists only the tools the credential may call.

Proven to fail 2026-09-25: with `tools_for` returning every tool, the scope and reach tests
listed the tools the credential could not call; with the batch check removed, a batch
answered -32600 for the wrong reason ("not a JSON-RPC message") and the test naming the
batch failed on the message.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.test import TestCase

from apps.agents.models import AgentAccess
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.testing import stub_session

URL = "/api/v1/mcp"
MODERN = "2026-07-28"
EVERY_READ = sorted(perms.AGENT_ACCESS_SCOPES)


def _meta(version: str = MODERN) -> dict[str, Any]:
    return {
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientInfo": {"name": "test-agent", "version": "1.0.0"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }


class McpTestCase(TestCase):
    """A plain client: every call here is a read, so no audit row is owed."""

    def setUp(self) -> None:
        self.bank = factories.tenant(slug="mcp-bank")
        self.entry = factories.agent_access_entry(self.bank)
        self.key = factories.entry_key(self.bank, self.entry, scopes=EVERY_READ).plain_key

    def post(self, body: Any, *, key: str | None = None, raw: bytes | None = None, headers: dict[str, str] | None = None) -> Any:
        data = raw if raw is not None else json.dumps(body)
        extra: dict[str, Any] = {f"HTTP_{name.upper().replace('-', '_')}": value for name, value in (headers or {}).items()}
        return self.client.post(URL, data=data, content_type="application/json", HTTP_X_API_KEY=key or self.key, **extra)

    def modern(self, method: str, *, key: str | None = None, request_id: Any = 1, params: dict[str, Any] | None = None) -> Any:
        body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": {"_meta": _meta(), **(params or {})}}
        return self.post(body, key=key, headers={"MCP-Protocol-Version": MODERN, "Mcp-Method": method})

    def legacy(self, method: str, *, version: str = "2025-11-25", key: str | None = None) -> Any:
        return self.post({"jsonrpc": "2.0", "id": 7, "method": method}, key=key, headers={"MCP-Protocol-Version": version})

    def error_of(self, response: Any, status: int) -> int:
        self.assertEqual(response.status_code, status, response.content)
        self.assertNotIn("result", response.json())
        return int(response.json()["error"]["code"])

    def tool_names(self, key: str) -> list[str]:
        response = self.modern("tools/list", key=key)
        self.assertEqual(response.status_code, 200, response.content)
        return [tool["name"] for tool in response.json()["result"]["tools"]]


class OnlyAnAgentAccessCredential(McpTestCase):
    def test_no_credential_is_unauthenticated(self) -> None:
        response = self.client.post(URL, data="{}", content_type="application/json")
        self.assertEqual((response.status_code, response.json()["code"]), (401, "unauthenticated"))

    def test_a_persons_session_is_refused(self) -> None:
        person = Principal(kind=PrincipalKind.USER, subject_id=uuid.uuid4(), tenant_id=self.bank.id, permissions=perms.ALL_PERMISSIONS)
        with stub_session(person):
            response = self.client.post(URL, data="{}", content_type="application/json", HTTP_AUTHORIZATION="Bearer test-session-token")
        self.assertEqual((response.status_code, response.json()["code"]), (401, "unauthenticated"))

    def test_a_key_of_no_entry_is_refused(self) -> None:
        bank_key = factories.api_key(self.bank, scopes=[perms.SCOPE_LIBRARY_READ]).plain_key
        response = self.modern("tools/list", key=bank_key)
        self.assertEqual((response.status_code, response.json()["code"]), (403, "agent_access_only"))

    def test_a_personal_token_is_served_by_either_header(self) -> None:
        person = factories.member(self.bank, roles=("compliance_officer",)).user
        token = factories.personal_token(self.bank, person).plain_key
        self.assertEqual(self.modern("server/discover", key=token).status_code, 200)
        body = {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": _meta()}}
        response = self.client.post(
            URL,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_MCP_PROTOCOL_VERSION=MODERN,
            HTTP_MCP_METHOD="server/discover",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_foreign_origin_is_refused(self) -> None:
        response = self.post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={"Origin": "https://evil.example"})
        self.assertEqual(self.error_of(response, 403), -32600)


class Stateless(McpTestCase):
    def test_get_and_delete_are_not_allowed(self) -> None:
        for method in ("GET", "DELETE"):
            with self.subTest(method):
                self.assertEqual(self.client.generic(method, URL, HTTP_X_API_KEY=self.key).status_code, 405)

    def test_initialize_mints_no_session_and_a_sent_one_is_ignored(self) -> None:
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}}}
        response = self.post(body, headers={"Mcp-Session-Id": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Mcp-Session-Id", response.headers)
        ping = self.post({"jsonrpc": "2.0", "id": 2, "method": "ping"}, headers={"MCP-Protocol-Version": "2025-11-25", "Mcp-Session-Id": "abc"})
        self.assertEqual(ping.json(), {"jsonrpc": "2.0", "id": 2, "result": {}})
        self.assertNotIn("Mcp-Session-Id", ping.headers)


class EarlierRevisions(McpTestCase):
    def initialize(self, version: str) -> dict[str, Any]:
        body = {
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
        }
        response = self.post(body)
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def test_initialize_agrees_a_supported_version_and_offers_tools(self) -> None:
        answer = self.initialize("2025-06-18")
        self.assertEqual(answer["id"], "init")
        result = answer["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["capabilities"], {"tools": {"listChanged": False}})
        self.assertEqual(set(result["serverInfo"]), {"name", "version"})
        self.assertTrue(result["instructions"])

    def test_initialize_answers_its_latest_for_a_version_it_does_not_speak(self) -> None:
        for asked in ("2024-11-05", MODERN):
            with self.subTest(asked):
                self.assertEqual(self.initialize(asked)["result"]["protocolVersion"], "2025-11-25")

    def test_initialize_without_a_version_is_invalid_params(self) -> None:
        response = self.post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(self.error_of(response, 200), -32602)

    def test_the_initialized_notification_is_accepted_with_no_body(self) -> None:
        response = self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual((response.status_code, response.content), (202, b""))

    def test_an_unknown_notification_is_refused(self) -> None:
        response = self.post({"jsonrpc": "2.0", "method": "notifications/whatever"})
        self.assertEqual(self.error_of(response, 400), -32601)

    def test_ping_and_tools_list(self) -> None:
        self.assertEqual(self.legacy("ping", version="2025-06-18").json()["result"], {})
        result = self.legacy("tools/list").json()["result"]
        self.assertNotIn("resultType", result)
        self.assertIn("list_obligations", [tool["name"] for tool in result["tools"]])

    def test_a_request_naming_no_version_is_unsupported(self) -> None:
        response = self.post({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(self.error_of(response, 400), -32022)
        self.assertEqual(response.json()["error"]["data"]["supported"], [MODERN, "2025-11-25", "2025-06-18"])

    def test_an_unknown_method_is_an_error_in_a_200(self) -> None:
        self.assertEqual(self.error_of(self.legacy("resources/list"), 200), -32601)


class CurrentRevision(McpTestCase):
    def test_discover_names_every_version_and_the_server(self) -> None:
        response = self.modern("server/discover", request_id="d-1")
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertEqual((answer["jsonrpc"], answer["id"]), ("2.0", "d-1"))
        result = answer["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["supportedVersions"], [MODERN, "2025-11-25", "2025-06-18"])
        self.assertEqual(result["capabilities"], {"tools": {"listChanged": False}})
        self.assertEqual((result["ttlMs"], result["cacheScope"]), (0, "private"))
        self.assertEqual(set(result["_meta"]["io.modelcontextprotocol/serverInfo"]), {"name", "version"})

    def test_tools_list_is_complete_uncached_and_read_only(self) -> None:
        result = self.modern("tools/list").json()["result"]
        self.assertEqual((result["resultType"], result["ttlMs"], result["cacheScope"]), ("complete", 0, "private"))
        self.assertNotIn("nextCursor", result)
        for tool in result["tools"]:
            with self.subTest(tool["name"]):
                self.assertEqual(tool["annotations"], {"readOnlyHint": True, "openWorldHint": False})
                self.assertEqual(tool["inputSchema"]["type"], "object")
                self.assertFalse(tool["inputSchema"]["additionalProperties"])
                self.assertTrue(set(tool["inputSchema"]["required"]) <= set(tool["inputSchema"]["properties"]))

    def test_an_unsupported_version_names_the_supported_ones(self) -> None:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": _meta("1900-01-01")}}
        response = self.post(body, headers={"MCP-Protocol-Version": "1900-01-01", "Mcp-Method": "tools/list"})
        self.assertEqual(self.error_of(response, 400), -32022)
        self.assertEqual(response.json()["error"]["data"], {"supported": [MODERN, "2025-11-25", "2025-06-18"], "requested": "1900-01-01"})

    def test_headers_must_match_the_body(self) -> None:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": _meta()}}
        for headers in (
            {"Mcp-Method": "tools/list"},
            {"MCP-Protocol-Version": "2025-11-25", "Mcp-Method": "tools/list"},
            {"MCP-Protocol-Version": MODERN},
            {"MCP-Protocol-Version": MODERN, "Mcp-Method": "server/discover"},
        ):
            with self.subTest(headers):
                self.assertEqual(self.error_of(self.post(body, headers=headers), 400), -32020)

    def test_missing_protocol_metadata_is_invalid_params(self) -> None:
        headers = {"MCP-Protocol-Version": MODERN, "Mcp-Method": "tools/list"}
        no_meta = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        self.assertEqual(self.error_of(self.post(no_meta, headers=headers), 400), -32602)
        no_capabilities = {**no_meta, "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": MODERN}}}
        self.assertEqual(self.error_of(self.post(no_capabilities, headers=headers), 400), -32602)
        not_a_string = {**no_meta, "params": {"_meta": {**_meta(), "io.modelcontextprotocol/protocolVersion": 2026}}}
        self.assertEqual(self.error_of(self.post(not_a_string, headers=headers), 400), -32602)

    def test_methods_this_revision_removed_or_we_do_not_offer_are_not_found(self) -> None:
        for method in ("ping", "prompts/list", "resources/list"):
            with self.subTest(method):
                self.assertEqual(self.error_of(self.modern(method), 404), -32601)


class UntrustedBodies(McpTestCase):
    def test_a_batch_is_refused(self) -> None:
        batch = [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2, "method": "ping"}]
        response = self.post(batch)
        self.assertEqual(self.error_of(response, 400), -32600)
        self.assertIn("Batches", response.json()["error"]["message"])
        self.assertNotIn("id", response.json())

    def test_a_body_that_is_not_json_is_a_parse_error(self) -> None:
        for raw in (b"{not json", b"\xff\xfe", b"", ("[" * 100_000).encode()):
            with self.subTest(raw[:8]):
                self.assertEqual(self.error_of(self.post(None, raw=raw), 400), -32700)

    def test_a_message_that_is_not_a_request_is_invalid(self) -> None:
        for body in (
            "ping",
            42,
            {"id": 1, "method": "ping"},
            {"jsonrpc": "1.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "id": 1, "method": 5},
            {"jsonrpc": "2.0", "id": None, "method": "ping"},
            {"jsonrpc": "2.0", "id": True, "method": "ping"},
            {"jsonrpc": "2.0", "id": 1.5, "method": "ping"},
            {"jsonrpc": "2.0", "id": 1, "result": {}},
        ):
            with self.subTest(body):
                self.assertEqual(self.error_of(self.post(body), 400), -32600)

    def test_params_that_are_not_an_object_are_invalid(self) -> None:
        response = self.post({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": [1]})
        self.assertEqual(self.error_of(response, 400), -32602)
        self.assertEqual(response.json()["id"], 1)


class TheToolListFollowsTheCredential(McpTestCase):
    def set_reach(self, on: bool) -> None:
        tenancy.activate(self.bank.id)
        AgentAccess.objects.filter(pk=self.entry.id).update(tenant_reach=on)

    def test_library_read_alone_offers_the_library_tools(self) -> None:
        key = factories.entry_key(self.bank, self.entry, scopes=[perms.SCOPE_LIBRARY_READ]).plain_key
        self.assertEqual(self.tool_names(key), ["list_obligations", "get_obligation", "what_applies"])

    def test_each_read_scope_adds_its_own_tool(self) -> None:
        for scope, tool in ((perms.SCOPE_SEARCH_READ, "search"), (perms.SCOPE_UPCOMING_READ, "list_upcoming_changes")):
            with self.subTest(scope):
                key = factories.entry_key(self.bank, self.entry, scopes=[scope]).plain_key
                self.assertEqual(self.tool_names(key), [tool])

    def test_no_register_tool_without_reach(self) -> None:
        self.set_reach(False)
        self.assertEqual(
            self.tool_names(self.key), ["search", "list_obligations", "get_obligation", "list_upcoming_changes", "what_applies"]
        )

    def test_no_register_tool_without_tenant_read(self) -> None:
        self.set_reach(True)
        key = factories.entry_key(self.bank, self.entry, scopes=sorted(set(EVERY_READ) - {perms.SCOPE_TENANT_READ})).plain_key
        self.assertNotIn("list_register_entries", self.tool_names(key))

    def test_tenant_read_and_reach_offer_the_register_tool_in_its_place(self) -> None:
        self.set_reach(True)
        self.assertEqual(
            self.tool_names(self.key),
            ["search", "list_obligations", "get_obligation", "list_upcoming_changes", "list_register_entries", "what_applies"],
        )

    def test_a_personal_token_reaches_the_register_only_through_an_entry(self) -> None:
        self.set_reach(True)
        person = factories.member(self.bank, roles=("compliance_officer",)).user
        unbound = factories.personal_token(self.bank, person, scopes=EVERY_READ).plain_key
        bound = factories.personal_token(self.bank, person, scopes=EVERY_READ, entry=self.entry).plain_key
        self.assertNotIn("list_register_entries", self.tool_names(unbound))
        self.assertIn("list_register_entries", self.tool_names(bound))

    def test_both_eras_list_the_same_tools(self) -> None:
        legacy = [tool["name"] for tool in self.legacy("tools/list").json()["result"]["tools"]]
        self.assertEqual(legacy, self.tool_names(self.key))
