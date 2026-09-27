"""Scenario stubs for the integrations app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: ACC, INT.
"""

from typing import Any
from unittest import skip

from django.test import TestCase


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

    @skip("pending: ACC-S7 (ACC-05, AC-ACC4, chunk 11)")
    def test_acc_s7(self) -> None:
        """ACC-S7

        The MCP server is one router over the same gates, and every credential is read-only (ACC-05, AC-ACC4).
        Its endpoint is `mcpMessage` (POST /mcp); the transport and the tool list are pinned in
        tests_mcp_transport.py (acc-mcp-transport), the tool calls land with acc-mcp-tools.
        """

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
