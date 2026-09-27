"""Scenario stubs for the integrations app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ACC, INT.
"""

import json
import re
import uuid
from typing import Any
from unittest import mock, skip

from django.test import TestCase

from apps.integrations import mcp_tools
from apps.library import testing as build
from apps.shared import agent_access_guard, factories
from apps.shared import permissions as perms
from apps.shared.routes import iter_operations
from apps.taxonomy.tests_entry_scope import EntryBank, seed
from config.api import api

V1 = "/api/v1"
_META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}


class IntegrationsScenarioTests(TestCase):
    """Scenario tests for apps.integrations, one method per @integration scenario."""

    @skip("pending: INT-S1")
    def test_int_s1(self) -> None:
        """INT-S1

        A signed webhook is delivered from the outbox with a delivery log (INT-01).
        """

    @skip("pending: INT-S2")
    def test_int_s2(self) -> None:
        """INT-S2

        Webhook delivery and inbound handlers are idempotent (INT-01).
        """

    @skip("pending: INT-S3")
    def test_int_s3(self) -> None:
        """INT-S3

        Actions export as tickets (INT-02).
        """

    @skip("pending: INT-S4")
    def test_int_s4(self) -> None:
        """INT-S4

        Audit events stream to the customer's SIEM (INT-03).
        """

    @skip("pending: INT-S5")
    def test_int_s5(self) -> None:
        """INT-S5

        Subscriptions store keys so a rename changes nothing (INT-01).
        """

    def test_acc_s7(self) -> None:
        """ACC-S7

        The MCP server is one router over the same gates, and every credential is read-only (ACC-05, AC-ACC4).
        Its endpoint is `mcpMessage` (POST /mcp); the transport and the tool list are pinned in
        tests_mcp_transport.py (acc-mcp-transport), each tool's parity, refusals, log and rate in
        tests_mcp_tools.py (acc-mcp-tools).
        """
        seed()
        bank = factories.tenant(slug="acc-s7")
        EntryBank(bank).footprint(build.term("regime:securities"))
        duty = build.obligation(build.instrument(key="acc-s7-act", regime="regime:securities"), key="acc-s7-duty")
        entry = factories.agent_access_entry(bank)
        every_read = factories.entry_key(bank, entry, scopes=sorted(perms.AGENT_ACCESS_SCOPES)).plain_key
        library_only = factories.entry_key(bank, entry, scopes=["library:read"]).plain_key

        def mcp_call(method: str, params: dict[str, Any], key: str) -> Any:
            body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {**params, "_meta": _META}}
            return self.client.post(
                f"{V1}/mcp", json.dumps(body), content_type="application/json", HTTP_X_API_KEY=key, HTTP_MCP_PROTOCOL_VERSION="2026-07-28", HTTP_MCP_METHOD=method
            ).json()["result"]

        # Given an agent access credential, when it lists tools, the list holds only what its
        # scopes reach, and a credential without tenant:read is offered no register tool.
        offered = [tool["name"] for tool in mcp_call("tools/list", {}, library_only)["tools"]]
        self.assertEqual(offered, ["list_obligations", "get_obligation", "what_applies"])

        # When it calls a tool, the same authentication class and scope gate run and the body is the route's.
        for key in (every_read, library_only):
            called = mcp_call("tools/call", {"name": "get_obligation", "arguments": {"stableKey": duty.stable_key}}, key)
            direct = self.client.get(f"{V1}/obligations/{duty.stable_key}", HTTP_X_API_KEY=key)
            self.assertEqual((called["isError"], called["structuredContent"]), (False, direct.json()))
        refused = mcp_call("tools/call", {"name": "search", "arguments": {"query": "reporting"}}, library_only)
        direct = self.client.post(f"{V1}/search", json.dumps({"q": "reporting"}), content_type="application/json", HTTP_X_API_KEY=library_only)
        self.assertEqual((refused["isError"], refused["structuredContent"]), (True, direct.json()))
        self.assertEqual(direct.json()["code"], "permission_denied")

        # When it calls any mutating route, by MCP or directly, it answers 403 read_only_credential,
        # and no scope an agent access credential may hold writes anything.
        with mock.patch.dict(mcp_tools.ROUTES, {"search": mcp_tools.Route("POST", "/proposals", body={"query": "title"})}):
            by_mcp = mcp_call("tools/call", {"name": "search", "arguments": {"query": "A new rule"}}, every_read)
        self.assertEqual((by_mcp["isError"], by_mcp["structuredContent"]["code"]), (True, "read_only_credential"))
        wrong = []
        for op in iter_operations(api):
            if not op.auth or op.method in agent_access_guard.READ_METHODS or (op.method, op.path) in agent_access_guard.READ_ONLY_ALLOWED:
                continue
            url = V1 + re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), op.path)
            response = self.client.generic(op.method, url, data="{}", content_type="application/json", HTTP_X_API_KEY=every_read)
            if response.status_code != 403 or response.json()["code"] not in ("read_only_credential", "step_up_required"):
                wrong.append(f"{op.method} {op.path} answered {response.status_code}")
        self.assertEqual(wrong, [])

    def test_acc_s8(self) -> None:
        """ACC-S8

        Pagination, the rate limit, the budget cap and the AI off switch bound every call (ACC-09).
        """
        from unittest import mock

        from django.conf import settings
        from django.core.cache import cache
        from django.test import override_settings

        from apps.agents.tests_what_applies import TradingBank
        from apps.agents.tests_what_applies_summary import Recording, cap
        from apps.identity.models import LoginEvent, LoginEventKind
        from apps.library import testing as library_testing
        from apps.shared import tenancy
        from apps.shared.models import Tenant

        # Given an entry whose scope holds 250 obligations: the general entry names no
        # department, so its scope is the footprint, which holds every duty carrying no term.
        bank = TradingBank(slug="acc-s8")
        act = library_testing.instrument(key="acc-s8-rulebook", regime="regime:securities")
        for n in range(250 - 4):
            library_testing.obligation(act, key=f"acc-s8-duty-{n:03d}", versions=())
        cap(bank.tenant, "5.00")
        llm = Recording()

        def ask(**page: Any) -> dict[str, Any]:
            with mock.patch("apps.shared.ai.get_llm", return_value=llm):
                response = bank.ask(self.client, bank.general_key, **page)
            self.assertEqual(response.status_code, 200, response.content)
            return dict(response.json())

        # When it lists them without a page size, then 20 are returned of the 250.
        first = ask()
        self.assertEqual((len(first["items"]), first["total"]), (settings.API_PAGE_SIZE_DEFAULT, 250))
        # And a page size of 500 is refused with the maximum named.
        refused = bank.ask(self.client, bank.general_key, limit=500)
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(refused.json()["errors"][0]["field"], "query.limit")
        self.assertIn(str(settings.API_PAGE_SIZE_MAX), refused.content.decode())
        # When it exceeds the per-credential rate limit, then the request answers 429 and
        # the security log records it.
        cache.clear()
        with override_settings(RATE_LIMITING_ENABLED=True, AGENT_ACCESS_RATE_PER_MINUTE=1):
            self.assertEqual(bank.ask(self.client, bank.general_key, limit=1, offset=1).status_code, 200)
            over = bank.ask(self.client, bank.general_key, limit=1, offset=1)
        self.assertEqual((over.status_code, over.json()["code"]), (429, "rate_limited"))
        tenancy.activate(bank.tenant.id)
        self.assertTrue(LoginEvent.objects.filter(tenant=bank.tenant, event=LoginEventKind.CREDENTIAL_RATE_LIMITED.value).exists())
        cache.clear()
        # When the tenant's monthly budget cap is reached, then a what-applies call returns
        # its list with no summary and the reason says the cap.
        asked = len(llm.calls)
        cap(bank.tenant, "0.00")
        capped = ask()
        self.assertEqual((capped["summary"]["reason"], capped["total"]), ("budget_cap", 250))
        # When the tenant's AI off switch is on, then no model call is made for that tenant
        # and the list is still returned.
        cap(bank.tenant, "5.00")
        Tenant.objects.filter(pk=bank.tenant.id).update(ai_enabled=False)
        off = ask()
        self.assertEqual((off["summary"]["reason"], off["total"], len(off["items"])), ("ai_off", 250, 20))
        self.assertEqual(len(llm.calls), asked, "neither the cap nor the switch let a model be asked")
