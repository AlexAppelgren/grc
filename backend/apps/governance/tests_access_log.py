"""The access log of the agents a bank runs itself (ACC-08; governance 0005).

One row per call an agent access credential makes, written after the response and never
changed: the filter names with their key values only, never free text; the record count;
the scope the entry was answered in; a person for a token and none for a service key. A
call refused for its rate is left to the security log. A person's session writes nothing.
The table is append-only by trigger, and its entry and person are the bank's own.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.agents.models import AgentAccessProduct
from apps.governance import access_log
from apps.governance.models import AgentAccessCall
from apps.shared import factories, tenancy
from apps.shared.audit import AppendOnlyRefused
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import FootprintTerm
from apps.taxonomy.tests_entry_scope import seed, term
from apps.tenants.models import TenantProduct, TenantProductTerm

V1 = "/api/v1"


class FiltersAreNamesAndKeys(SimpleTestCase):
    def test_free_text_keeps_its_name_and_a_value_that_is_not_a_key_is_dropped(self) -> None:
        request = RequestFactory().get(
            "/api/v1/obligations",
            {"q": "cards", "footprint": "in", "term": ["product_type:cards", "a phrase with spaces"], "limit": "5", "offset": "0"},
        )
        self.assertEqual(access_log.filters_of(request), {"q": [], "footprint": ["in"], "term": ["product_type:cards"]})

    def test_a_route_notes_its_body_filters_tool_and_count(self) -> None:
        request = RequestFactory().post("/api/v1/mcp")
        principal = SimpleNamespace()  # stands in: note reads nothing of it
        access_log.begin(request, principal, "mcp")  # type: ignore[arg-type]
        access_log.note(request, tool="list_obligations", filters={"description": ["x"], "jurisdiction": ["se"]}, record_count=0)
        pending = getattr(request, access_log.REQUEST_ATTRIBUTE)
        self.assertEqual((pending.tool, pending.filters, pending.record_count, pending.counted), ("list_obligations", {"description": [], "jurisdiction": ["se"]}, 0, True))
        access_log.begin(request, principal, "again")  # type: ignore[arg-type]
        self.assertEqual(getattr(request, access_log.REQUEST_ATTRIBUTE).tool, "list_obligations", "one call per request")


class AccessLogRows(ScenarioTestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant(slug="acc-log")
        self.entry = factories.agent_access_entry(self.tenant)
        self.key = factories.entry_key(self.tenant, self.entry)

    def calls(self) -> list[AgentAccessCall]:
        tenancy.activate(self.tenant.id)
        return list(AgentAccessCall.objects.filter(tenant_id=self.tenant.id))

    def test_a_narrowed_entry_logs_the_terms_it_read_in(self) -> None:
        seed()
        custody = term("service_type", "custody")
        tenancy.activate(self.tenant.id)
        FootprintTerm.objects.create(tenant=self.tenant, term=custody)
        product = TenantProduct.objects.create(tenant=self.tenant, name="Custody accounts")
        TenantProductTerm.objects.create(tenant=self.tenant, product=product, term=custody)
        AgentAccessProduct.objects.create(tenant=self.tenant, agent_access=self.entry.row, product=product)
        self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=self.key.plain_key)
        (call,) = self.calls()
        self.assertEqual((call.scope_narrowed, call.scope_terms), (True, {"service_type": ["custody"]}))

    def test_a_single_record_counts_one_and_a_refusal_counts_none(self) -> None:
        self.client.get(f"{V1}/obligations/{uuid.uuid4()}", HTTP_X_API_KEY=self.key.plain_key)
        (call,) = self.calls()
        self.assertEqual((call.tool, call.status, call.record_count), ("getObligation", 404, None))
        self.assertEqual(list(call.filters), ["obligation_id"])

    @override_settings(RATE_LIMITING_ENABLED=True, AGENT_ACCESS_RATE_PER_MINUTE=1)
    def test_a_call_refused_for_its_rate_is_left_to_the_security_log(self) -> None:
        from django.core.cache import cache

        cache.clear()
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=self.key.plain_key).status_code, 200)
        self.assertEqual(self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=self.key.plain_key).status_code, 429)
        self.assertEqual([call.status for call in self.calls()], [200])
        cache.clear()

    def test_a_persons_session_and_a_key_of_no_entry_write_nothing(self) -> None:
        self.client.get(f"{V1}/obligations", **sign_in(self.entry.admin, tenant=self.tenant))
        self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=factories.api_key(self.tenant).plain_key)
        self.assertEqual(self.calls(), [])

    def test_a_row_is_never_changed_or_deleted(self) -> None:
        self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=self.key.plain_key)
        (call,) = self.calls()
        with self.assertRaises(AppendOnlyRefused):
            call.save()
        with self.assertRaises(AppendOnlyRefused):
            AgentAccessCall.objects.filter(pk=call.pk).delete()
        for statement in ("UPDATE agent_access_call SET tool = 'rewritten' WHERE id = %s", "DELETE FROM agent_access_call WHERE id = %s"):
            with self.subTest(statement=statement), self.assertRaisesMessage(DatabaseError, "append-only"), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(statement, [str(call.pk)])

    def test_a_row_cannot_name_another_banks_entry(self) -> None:
        other = factories.tenant(slug="acc-log-other")
        foreign = factories.agent_access_entry(other)
        tenancy.activate(self.tenant.id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AgentAccessCall.objects.create(
                tenant=self.tenant, api_key_id=self.key.id, agent_access_id=foreign.id, tool="listObligations", duration_ms=1, status=200
            )

    def test_the_log_is_paged_newest_first(self) -> None:
        for _ in range(3):
            self.client.get(f"{V1}/obligations", HTTP_X_API_KEY=self.key.plain_key)
        page = self.client.get(f"{V1}/agent-access/{self.entry.id}/calls?limit=2", **sign_in(self.entry.admin, tenant=self.tenant)).json()
        self.assertEqual((page["total"], len(page["items"])), (3, 2))
        self.assertGreaterEqual(page["items"][0]["at"], page["items"][1]["at"])
        self.assertNotIn("plain", json.dumps(page))
