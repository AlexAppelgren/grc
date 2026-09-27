"""Findings of the security review of agent access and the bank's own records
(security-review-c11-access-d89, docs/reviews/CHUNK11_ACCESS_OWN_REVIEW.md) on the MCP
server. Each test was written first and failed before its fix.

M1: a tool's inner request copied every header of the MCP request, so a session bearer sent
beside the agent's key made the route answer the person rather than the credential the MCP
request authenticated, logged and rate-limited: the entry's scope was not applied.
L1: a lone surrogate in a tool argument (valid JSON, not encodable as UTF-8) answered 500.
"""

from __future__ import annotations

import json

from apps.integrations.tests_mcp_tools import MODERN, URL, ToolsWorld, _meta
from apps.shared import factories
from apps.shared.testing import sign_in


class TheToolRunsAsTheMcpCredentialAlone(ToolsWorld):
    def test_a_session_bearer_beside_the_key_does_not_change_who_reads(self) -> None:
        # A person of the same bank reads the card duty; the trading entry never does.
        person = factories.member(self.tenant, roles=("compliance_officer",)).user
        session = sign_in(person, tenant=self.tenant)
        self.assertEqual(self.client.get("/api/v1/obligations/mcp-tools-cards", **session).status_code, 200)

        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_obligation", "arguments": {"stableKey": "mcp-tools-cards"}, "_meta": _meta()},
        }
        response = self.client.post(
            URL,
            data=json.dumps(message),
            content_type="application/json",
            HTTP_X_API_KEY=self.key,
            HTTP_MCP_PROTOCOL_VERSION=MODERN,
            HTTP_MCP_METHOD="tools/call",
            **session,
        )

        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["code"], "not_found")


class AnArgumentThatIsNotText(ToolsWorld):
    def test_a_lone_surrogate_is_a_tool_error_not_a_server_error(self) -> None:
        for name, arguments in (("get_obligation", {"stableKey": "\ud800"}), ("list_obligations", {"asOf": "\ud800"})):
            with self.subTest(tool=name):
                response = self.call(name, arguments)
                self.assertEqual(response.status_code, 200, response.content)
                result = response.json()["result"]
                self.assertTrue(result["isError"])
                self.assertEqual(result["structuredContent"]["code"], "validation_error")
