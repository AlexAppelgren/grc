"""The six MCP tools (ACC-05, acc-mcp-tools): `tools/call` runs the REST route behind each
tool as a request of its own, through the same authentication class, the same agent access
fence and the same scope gate, so a tool answers the REST body as its structured content
and a refusal as a tool error keeping the problem's code. A route that writes answers 403
`read_only_credential` over both, the access log names the tool, and the call spends the
credential's rate once.

Proven to fail 2026-09-25: before `mcp_tools.py`, every `tools/call` answered -32601; with
the rate skip taken out of the fence, the rate test's second call answered 429.
"""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from typing import Any
from unittest import mock

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.agents.models import AgentAccess
from apps.governance.models import AgentAccessCall, TenantReach
from apps.integrations import mcp, mcp_tools
from apps.library import testing as build
from apps.register.logic import ensure_register_entry
from apps.search import indexing
from apps.shared import agent_access_guard, factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.taxonomy.tests_entry_scope import EntryBank, seed, term
from apps.watch import testing as watch_build

V1 = "/api/v1"
URL = f"{V1}/mcp"
MODERN = "2026-07-28"
LEGACY = "2025-11-25"
EVERY_READ = ("library:read", "search:read", "upcoming:read", "tenant:read")
SUMMARY = "Report every futures position to the trade repository by the next working day."


def _meta() -> dict[str, Any]:
    return {"io.modelcontextprotocol/protocolVersion": MODERN, "io.modelcontextprotocol/clientCapabilities": {}}


class ToolsWorld(TestCase):
    """A bank whose footprint covers securities with the derivatives and cards product
    types. Its Trading department's product carries derivatives, so `trading` (an entry
    naming that department) reads the futures duty and not the card one; the bank has
    decided the futures duty applies, and a change on futures is dated a month ahead.
    `trading` holds every read and tenant reach is on for the bank and the entry."""

    tenant: Any
    futures: Any
    cards: Any
    trading: Any
    key: str
    library_only_key: str

    @classmethod
    def setUpTestData(cls) -> None:
        seed()
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="mcp-tools")
        bank = EntryBank(cls.tenant)
        derivatives, cards = term("product_type", "derivatives"), term("product_type", "cards")
        bank.footprint(build.term("regime:securities"), derivatives, cards)
        unit = bank.unit("Trading")
        bank.product("Futures", derivatives, unit=unit)
        act = build.instrument(key="mcp-tools-act", regime="regime:securities")
        cls.futures = build.obligation(act, key="mcp-tools-futures", terms=["product_type:derivatives"], versions=((None, {"en": SUMMARY}),))
        cls.cards = build.obligation(act, key="mcp-tools-cards", terms=["product_type:cards"])
        indexing.reindex_all()
        change = watch_build.change(title="mcp-tools futures reporting", authority=None, key_date=timezone.localdate() + datetime.timedelta(days=30))
        watch_build.term_link(change, term_ref="product_type:derivatives")
        cls.trading = bank.entry(departments=[unit], name="Trading agent")
        officer = factories.member(cls.tenant, roles=("compliance_officer",)).user
        tenancy.activate(cls.tenant.id)
        TenantReach.objects.update_or_create(tenant=cls.tenant, defaults={"enabled": True})
        AgentAccess.objects.filter(pk=cls.trading.id).update(tenant_reach=True)
        with transaction.atomic():
            ensure_register_entry(tenant_id=cls.tenant.id, obligation_id=cls.futures.id, actor=Actor(kind=ActorType.USER, id=officer.id, label=officer.name))
        cls.key = factories.entry_key(cls.tenant, SimpleNamespace(id=cls.trading.id), scopes=EVERY_READ).plain_key
        cls.library_only_key = factories.entry_key(cls.tenant, SimpleNamespace(id=cls.trading.id), scopes=("library:read",)).plain_key

    def setUp(self) -> None:
        cache.clear()  # the per-credential and per-searcher rate buckets

    # -- the two ways in ------------------------------------------------------------------
    def call(self, name: Any, arguments: Any = None, *, key: str | None = None, legacy: bool = False, params: dict[str, Any] | None = None) -> Any:
        body_params: dict[str, Any] = params if params is not None else {"name": name, **({} if arguments is None else {"arguments": arguments})}
        headers: dict[str, Any] = {"HTTP_X_API_KEY": key or self.key}
        if legacy:
            headers["HTTP_MCP_PROTOCOL_VERSION"] = LEGACY
        else:
            body_params = {**body_params, "_meta": _meta()}
            headers.update(HTTP_MCP_PROTOCOL_VERSION=MODERN, HTTP_MCP_METHOD="tools/call")
        message = {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": body_params}
        return self.client.post(URL, data=json.dumps(message), content_type="application/json", **headers)

    def result(self, name: str, arguments: Any = None, **kwargs: Any) -> dict[str, Any]:
        response = self.call(name, arguments, **kwargs)
        self.assertEqual(response.status_code, 200, response.content)
        result: dict[str, Any] = response.json()["result"]
        # The text block always holds the same JSON as the structured content.
        self.assertEqual([block["type"] for block in result["content"]], ["text"])
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        return result

    def rest(self, method: str, path: str, *, query: dict[str, Any] | None = None, body: Any = None, key: str | None = None) -> Any:
        headers: dict[str, Any] = {"HTTP_X_API_KEY": key or self.key}
        if method == "GET":
            return self.client.get(f"{V1}{path}", query or {}, **headers)
        suffix = "" if not query else "?" + "&".join(f"{name}={value}" for name, value in query.items())
        return self.client.post(f"{V1}{path}{suffix}", data=json.dumps(body), content_type="application/json", **headers)


class EachToolAnswersItsRoutesBody(ToolsWorld):
    """Parity: the structured content is the REST body, byte for byte once parsed."""

    def assert_same(self, name: str, arguments: dict[str, Any], rest: Any) -> dict[str, Any]:
        self.assertEqual(rest.status_code, 200, rest.content)
        result = self.result(name, arguments)
        self.assertEqual((result["resultType"], result["isError"]), ("complete", False))
        self.assertEqual(result["structuredContent"], rest.json())
        return result

    def test_search(self) -> None:
        result = self.assert_same("search", {"query": "futures position", "limit": 5}, self.rest("POST", "/search", body={"q": "futures position", "limit": 5}))
        self.assertIn(self.futures.stable_key, json.dumps(result["structuredContent"]))

    def test_list_obligations(self) -> None:
        result = self.assert_same("list_obligations", {"limit": 5}, self.rest("GET", "/obligations", query={"limit": 5}))
        keys = [row["stableKey"] for row in result["structuredContent"]["items"]]
        self.assertIn(self.futures.stable_key, keys)
        self.assertNotIn(self.cards.stable_key, keys, "the entry's scope holds the card duty back")

    def test_get_obligation(self) -> None:
        today = timezone.localdate().isoformat()
        self.assert_same(
            "get_obligation", {"stableKey": self.futures.stable_key, "asOf": today}, self.rest("GET", f"/obligations/{self.futures.stable_key}", query={"asOf": today})
        )

    def test_list_upcoming_changes(self) -> None:
        result = self.assert_same("list_upcoming_changes", {"limit": 10}, self.rest("GET", "/upcoming", query={"limit": 10}))
        self.assertIn("mcp-tools futures reporting", [row["title"] for row in result["structuredContent"]])

    def test_list_register_entries(self) -> None:
        result = self.assert_same("list_register_entries", {}, self.rest("GET", "/register-entries"))
        self.assertEqual(len(result["structuredContent"]["items"]), 1)

    def test_what_applies(self) -> None:
        description = "A futures position reporting service"
        rest = self.rest("POST", "/agent-access/what-applies", query={"limit": 3}, body={"description": description})
        self.assert_same("what_applies", {"description": description, "limit": 3}, rest)

    def test_an_earlier_revision_gets_the_same_body_and_an_array_inside_an_object(self) -> None:
        listed = self.result("list_obligations", {}, legacy=True)
        self.assertNotIn("resultType", listed)
        self.assertEqual(listed["structuredContent"], self.rest("GET", "/obligations").json())
        # Revision 2025-11-25 allows only an object as structured content.
        upcoming = self.result("list_upcoming_changes", {}, legacy=True)
        self.assertEqual(upcoming["structuredContent"], {"items": self.rest("GET", "/upcoming").json()})


class RefusalsAreToolErrorsKeepingTheCode(ToolsWorld):
    def assert_same_refusal(self, name: str, arguments: dict[str, Any], rest: Any, code: str, *, key: str | None = None) -> None:
        self.assertEqual(rest.json()["code"], code, rest.content)
        result = self.result(name, arguments, key=key)
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"], rest.json())

    def test_the_scope_gate_is_the_routes(self) -> None:
        refused = self.rest("POST", "/search", body={"q": "futures"}, key=self.library_only_key)
        self.assert_same_refusal("search", {"query": "futures"}, refused, "permission_denied", key=self.library_only_key)

    def test_a_record_outside_the_scope_is_the_same_not_found(self) -> None:
        refused = self.rest("GET", f"/obligations/{self.cards.stable_key}")
        self.assert_same_refusal("get_obligation", {"stableKey": self.cards.stable_key}, refused, "not_found")

    def test_the_register_follows_the_banks_reach(self) -> None:
        tenancy.activate(self.tenant.id)
        TenantReach.objects.filter(tenant=self.tenant).update(enabled=False)
        self.assert_same_refusal("list_register_entries", {}, self.rest("GET", "/register-entries"), "tenant_reach_off")

    def test_pagination_is_the_routes(self) -> None:
        first = self.result("list_obligations", {"limit": 1})["structuredContent"]
        self.assertEqual(len(first["items"]), 1)
        self.assertEqual(first, self.rest("GET", "/obligations", query={"limit": 1}).json())
        self.assert_same_refusal("list_obligations", {"limit": 500}, self.rest("GET", "/obligations", query={"limit": 500}), "validation_error")

    def test_an_argument_the_tool_does_not_name_is_refused(self) -> None:
        result = self.result("list_upcoming_changes", {"region": "se"})
        self.assertTrue(result["isError"])
        self.assertEqual((result["structuredContent"]["code"], result["structuredContent"]["errors"][0]["field"]), ("validation_error", "region"))

    def test_an_argument_of_the_wrong_type_is_refused(self) -> None:
        result = self.result("list_obligations", {"limit": [5]})
        self.assertEqual((result["isError"], result["structuredContent"]["errors"][0]["field"]), (True, "limit"))

    def test_a_stable_key_cannot_route_to_another_read(self) -> None:
        for crafted in (f"{self.futures.stable_key}/diff", "", "../instruments"):
            with self.subTest(crafted=crafted):
                result = self.result("get_obligation", {"stableKey": crafted})
                self.assertTrue(result["isError"])
                self.assertEqual(result["structuredContent"]["code"], "validation_error")


class EveryCredentialStaysReadOnly(ToolsWorld):
    def test_every_tool_is_a_read_the_fence_lets_through(self) -> None:
        operations = agent_access_guard._operations()
        declared = {spec.tool.name: set(spec.tool.input_schema.properties) for spec in mcp.TOOLS}
        self.assertEqual(set(mcp_tools.ROUTES), set(declared))
        for name, route in mcp_tools.ROUTES.items():
            with self.subTest(name):
                self.assertIn((route.method, route.path.replace("{", "<").replace("}", ">")), operations)
                self.assertTrue(route.method == "GET" or (route.method, route.path) in agent_access_guard.READ_ONLY_ALLOWED)
                self.assertEqual(set(route.query) | set(route.body) | set(route.path_args), declared[name])

    def test_a_route_that_writes_answers_read_only_credential_over_both(self) -> None:
        direct = self.rest("POST", "/proposals", body={})
        self.assertEqual((direct.status_code, direct.json()["code"]), (403, "read_only_credential"))
        writing = mcp_tools.Route("POST", "/proposals", body={"query": "title"})
        with mock.patch.dict(mcp_tools.ROUTES, {"search": writing}):
            result = self.result("search", {"query": "A new rule"})
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"], direct.json())


class ProtocolErrors(ToolsWorld):
    def assert_invalid_params(self, response: Any, status: int) -> None:
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["error"]["code"], -32602)

    def test_an_unknown_tool(self) -> None:
        self.assert_invalid_params(self.call("delete_everything", {}), 400)
        self.assert_invalid_params(self.call("delete_everything", {}, legacy=True), 200)

    def test_a_call_without_a_name_or_with_arguments_that_are_not_an_object(self) -> None:
        self.assert_invalid_params(self.call(None, params={}), 400)
        self.assert_invalid_params(self.call("list_obligations", ["limit", 5]), 400)


class TheCallIsLoggedAndCountedOnce(ToolsWorld):
    def calls(self) -> list[AgentAccessCall]:
        tenancy.activate(self.tenant.id)
        return list(AgentAccessCall.objects.filter(agent_access_id=self.trading.id).order_by("at", "id"))

    def test_the_access_log_names_the_tool_and_never_the_text(self) -> None:
        self.result("get_obligation", {"stableKey": self.futures.stable_key})
        self.result("what_applies", {"description": "A secret futures desk nobody may know of"})
        opened, asked = self.calls()
        self.assertEqual((opened.tool, opened.status, opened.record_count), ("get_obligation", 200, 1))
        self.assertEqual(opened.filters, {"obligation_id": [self.futures.stable_key]})
        self.assertEqual((asked.tool, asked.filters), ("what_applies", {"description": []}))
        self.assertNotIn("secret", json.dumps([asked.filters, asked.scope_terms]))

    def test_a_refused_tool_is_logged_with_the_routes_status(self) -> None:
        self.result("search", {"query": "futures"}, key=self.library_only_key)
        (row,) = self.calls()
        self.assertEqual((row.tool, row.status), ("search", 403))

    @override_settings(RATE_LIMITING_ENABLED=True, AGENT_ACCESS_RATE_PER_MINUTE=2)
    def test_a_tool_call_spends_one_request_of_the_rate(self) -> None:
        self.assertEqual([self.call("list_obligations", {}).status_code for _ in range(2)], [200, 200])
        refused = self.call("list_obligations", {})
        self.assertEqual((refused.status_code, refused.json()["code"]), (429, "rate_limited"))
