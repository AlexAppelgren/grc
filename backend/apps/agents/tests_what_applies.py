"""What applies (ACC-06, ACC-07, D-71): `POST /agent-access/what-applies`.

The list is every shared obligation in the footprint and the entry's scope, never shortened
but by paging, ranked by the description's words in the library text, with the bank's
decision when tenant reach passes and without the bank's own private records, which are
counted. Every answer to an agent access credential states its scope, in the body here and
in the `Agent-Access-Scope` header of every answer, errors included. The description is
capped by a setting and never stored or logged."""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from typing import Any

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.agents.models import AgentAccess, AgentAccessDepartment
from apps.governance.models import AgentAccessCall, TenantReach
from apps.library import testing as library_testing
from apps.library.models import Obligation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, TenantObligation
from apps.search import indexing
from apps.shared import factories, tenancy
from apps.shared.agent_access_guard import SCOPE_HEADER
from apps.shared.models import AuditEvent
from apps.shared.audit import Actor, ActorType
from apps.shared.testing import sign_in
from apps.shared.tenancy import library_write
from apps.taxonomy.models import FootprintTerm, TaxonomyTerm, TaxonomyTermLabel, TermDimension
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.tenants.models import OrgUnit, OrgUnitKind, TenantProduct, TenantProductTerm

WHAT_APPLIES = "/api/v1/agent-access/what-applies"
READS = ("library:read", "tenant:read")
CARD_FEATURE = "a feature that issues virtual cards against a trading account"
ORDER_ROUTING = "a new order-routing service for professional clients"


def seed() -> None:
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()


def term(ref: str, label: str | None = None, *, note: str = "") -> TaxonomyTerm:
    """A library term, filed with an English label when the seed has none."""
    dimension, _, key = ref.partition(":")
    with library_write("test"):
        row, created = TaxonomyTerm.objects.get_or_create(
            dimension=TermDimension.objects.get(key=dimension), key=key, defaults={"usage_note": note}
        )
        if created and label:
            TaxonomyTermLabel.objects.create(term=row, language="en", text=label, is_original=True)
    return row


class TradingBank:
    """A bank whose footprint covers trading and card issuing. Its Trading department sells
    futures and equities under an investment-services licence; a debit card sits outside it.
    `trading` is an entry narrowed to Trading, `general` names nothing; both hold a key with
    `library:read` and `tenant:read`, and tenant reach is on for the bank and both entries.

    Four shared obligations: two tagged with Trading's product types, one untagged, one
    tagged for card issuing and cards. One more is the bank's own private obligation."""

    def __init__(self, *, slug: str = "what-applies") -> None:
        seed()
        self.derivatives = term("product_type:derivatives", "Derivatives")
        self.securities = term("product_type:securities", "Securities")
        self.cards = term("product_type:cards", "Cards")
        self.investment = term("licensed_activity:investment_services", "Investment services")
        self.issuing = library_testing.term("licensed_activity:card_issuing")
        self.acquiring = library_testing.term("licensed_activity:card_acquiring")
        self.tenant = factories.tenant(slug=slug)
        self.officer = factories.member(self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lindqvist")).user
        act = library_testing.instrument(key=f"{slug}-act", regime="regime:securities")
        self.execution = library_testing.obligation(
            act, key=f"{slug}-best-execution", titles={"en": "Best execution of client orders"}, terms=("product_type:derivatives",)
        )
        self.records = library_testing.obligation(
            act,
            key=f"{slug}-order-records",
            titles={"en": "Keep records of every order"},
            terms=("product_type:securities",),
            versions=((None, {"en": "Record each routing decision made for professional clients."}),),
        )
        self.outsourcing = library_testing.obligation(act, key=f"{slug}-outsourcing", titles={"en": "Notify outsourcing"})
        self.card = library_testing.obligation(
            act,
            key=f"{slug}-card-authentication",
            titles={"en": "Authenticate card payments strongly"},
            terms=("product_type:cards", "licensed_activity:card_issuing"),
        )
        own_act = library_testing.instrument(key=f"{slug}-own", regime="regime:securities", owner_tenant=self.tenant)
        self.private = library_testing.obligation(own_act, key=f"{slug}-own-order-rule", owner_tenant=self.tenant)
        for obligation in (self.execution, self.records, self.outsourcing, self.card):
            indexing.reindex(obligation.id)
        tenancy.activate(self.tenant.id)
        for row in (self.derivatives, self.securities, self.cards, self.investment, self.issuing, self.acquiring):
            FootprintTerm.objects.create(tenant=self.tenant, term=row)
        self.department = OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.BUSINESS_AREA.value, name="Trading")
        self.product("Futures", self.derivatives, self.investment, unit=self.department)
        self.product("Equities", self.securities, self.investment, unit=self.department)
        self.product("Debit card", self.cards, self.issuing)
        entry = factories.agent_access_entry(self.tenant, name="Trading platform coding agent")
        self.trading = entry.row
        tenancy.activate(self.tenant.id)
        AgentAccessDepartment.objects.create(tenant=self.tenant, agent_access=self.trading, department=self.department)
        self.trading_key = factories.entry_key(self.tenant, entry, scopes=READS).plain_key
        general = factories.agent_access_entry(self.tenant, name="Compliance assistant")
        self.general = general.row
        self.general_key = factories.entry_key(self.tenant, general, scopes=READS).plain_key
        tenancy.activate(self.tenant.id)
        TenantReach.objects.update_or_create(tenant=self.tenant, defaults={"enabled": True})
        AgentAccess.objects.filter(pk__in=[self.trading.id, self.general.id]).update(tenant_reach=True)

    def product(self, name: str, *terms: TaxonomyTerm, unit: OrgUnit | None = None) -> TenantProduct:
        tenancy.activate(self.tenant.id)
        row = TenantProduct.objects.create(tenant=self.tenant, name=name, org_unit=unit)
        for scope_term in terms:
            TenantProductTerm.objects.create(tenant=self.tenant, product=row, term=scope_term)
        return row

    def decide(self, obligation: Obligation, reason: str) -> None:
        tenancy.activate(self.tenant.id)
        actor = Actor(kind=ActorType.USER, id=self.officer.id, label=self.officer.name)
        with transaction.atomic():
            entry = ensure_register_entry(tenant_id=self.tenant.id, obligation_id=obligation.id, actor=actor)
        TenantObligation.objects.filter(pk=entry.pk).update(
            applicability=Applicability.APPLIES.value,
            applicability_reason=reason,
            applicability_decided_at=timezone.now(),
            applicability_decided_by=self.officer,
        )

    def ask(self, client: Any, key: str, description: str = ORDER_ROUTING, **page: Any) -> Any:
        query = "&".join(f"{name}={value}" for name, value in page.items())
        return client.post(
            f"{WHAT_APPLIES}?{query}" if query else WHAT_APPLIES,
            json.dumps({"description": description}),
            content_type="application/json",
            HTTP_X_API_KEY=key,
        )


def keys(body: dict[str, Any]) -> list[str]:
    return [item["stableKey"] for item in body["items"]]


class TheFullList(TestCase):
    def setUp(self) -> None:
        self.bank = TradingBank()

    def test_a_narrowed_entry_reads_its_products_and_the_untagged_and_never_the_card_rule(self) -> None:
        response = self.bank.ask(self.client, self.bank.trading_key)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(set(keys(body)), {self.bank.execution.stable_key, self.bank.records.stable_key, self.bank.outsourcing.stable_key})
        self.assertEqual(body["total"], 3)
        self.assertNotIn(self.bank.card.stable_key, response.content.decode())

    def test_an_entry_naming_nothing_reads_the_whole_footprint(self) -> None:
        body = self.bank.ask(self.client, self.bank.general_key).json()
        self.assertIn(self.bank.card.stable_key, keys(body))
        self.assertFalse(body["scope"]["narrowed"])
        self.assertEqual(body["outsideScope"], {"terms": [], "advice": None})

    def test_the_bank_s_own_records_are_left_out_and_counted(self) -> None:
        response = self.bank.ask(self.client, self.bank.general_key)
        self.assertNotIn(self.bank.private.stable_key, response.content.decode())
        self.assertEqual(response.json()["ownRecordsLeftOut"], 1)

    def test_the_library_text_ranks_the_list_and_the_stable_key_breaks_ties(self) -> None:
        # "order" is in two titles; "routing", "professional" and "clients" only in the
        # records duty's summary, which the search index holds.
        body = self.bank.ask(self.client, self.bank.trading_key, "routing of orders for professional clients").json()
        self.assertEqual(keys(body), [self.bank.records.stable_key, self.bank.execution.stable_key, self.bank.outsourcing.stable_key])

    def test_paging_shortens_the_page_and_never_the_list(self) -> None:
        first = self.bank.ask(self.client, self.bank.trading_key, limit=2).json()
        second = self.bank.ask(self.client, self.bank.trading_key, limit=2, offset=2).json()
        self.assertEqual((first["total"], second["total"]), (3, 3))
        self.assertEqual(len(first["items"]), 2)
        self.assertEqual(len(keys(first) + keys(second)), len(set(keys(first) + keys(second))))
        self.assertEqual(self.bank.ask(self.client, self.bank.trading_key, limit=101).status_code, 422)

    def test_each_row_carries_its_citation_and_the_version_in_force(self) -> None:
        body = self.bank.ask(self.client, self.bank.trading_key).json()
        row = next(item for item in body["items"] if item["stableKey"] == self.bank.execution.stable_key)
        self.assertEqual(row["instrument"]["key"], "what-applies-act")
        self.assertEqual(row["refLabel"], self.bank.execution.ref_label)
        self.assertEqual(row["title"]["text"], "Best execution of client orders")
        self.assertEqual(row["version"]["versionNumber"], 1)

    def test_the_summary_slot_says_it_holds_no_summary(self) -> None:
        body = self.bank.ask(self.client, self.bank.trading_key).json()
        self.assertEqual(body["summary"], {"status": "not_drafted", "text": None})


class TheRegisterBesideIt(TestCase):
    def setUp(self) -> None:
        self.bank = TradingBank()
        self.bank.decide(self.bank.execution, "We route client orders on regulated venues")
        self.bank.decide(self.bank.card, "We issue debit cards")

    def row(self, body: dict[str, Any], obligation: Obligation) -> dict[str, Any]:
        return next(item for item in body["items"] if item["stableKey"] == obligation.stable_key)

    def test_decisions_ride_on_the_rows_while_reach_is_on(self) -> None:
        body = self.bank.ask(self.client, self.bank.trading_key).json()
        self.assertEqual(body["registerRead"], "included")
        decision = self.row(body, self.bank.execution)["decision"]
        self.assertEqual((decision["applicability"], decision["applicabilityReason"]), ("applies", "We route client orders on regulated venues"))
        self.assertIsNone(self.row(body, self.bank.outsourcing)["decision"])
        self.assertNotIn("We issue debit cards", json.dumps(body))

    def test_with_reach_off_the_list_stands_and_no_decision_is_read(self) -> None:
        tenancy.activate(self.bank.tenant.id)
        TenantReach.objects.filter(tenant=self.bank.tenant).update(enabled=False)
        response = self.bank.ask(self.client, self.bank.trading_key)
        body = response.json()
        self.assertEqual((response.status_code, body["registerRead"], body["total"]), (200, "tenant_reach_off", 3))
        self.assertTrue(all(item["decision"] is None for item in body["items"]))
        self.assertNotIn("regulated venues", response.content.decode())

    def test_a_key_without_tenant_read_reads_the_library_alone(self) -> None:
        key = factories.entry_key(self.bank.tenant, SimpleNamespace(id=self.bank.trading.id), scopes=("library:read",)).plain_key
        body = self.bank.ask(self.client, key).json()
        self.assertEqual(body["registerRead"], "not_granted")
        self.assertNotIn("regulated venues", json.dumps(body))


class TheDescription(TestCase):
    def setUp(self) -> None:
        self.bank = TradingBank()

    def test_it_is_required(self) -> None:
        response = self.bank.ask(self.client, self.bank.trading_key, "   ")
        self.assertEqual((response.status_code, response.json()["code"]), (422, "description_required"))

    @override_settings(AGENT_ACCESS_DESCRIPTION_MAX_CHARS=20)
    def test_it_is_capped_by_the_setting(self) -> None:
        self.assertEqual(self.bank.ask(self.client, self.bank.trading_key, "x" * 20).status_code, 200)
        response = self.bank.ask(self.client, self.bank.trading_key, "x" * 21)
        self.assertEqual((response.status_code, response.json()["code"]), (422, "description_too_long"))

    def test_it_is_never_stored_and_the_access_log_keeps_its_name_alone(self) -> None:
        description = "a secret merger desk nobody may know about"
        tenancy.activate(self.bank.tenant.id)
        audit_rows = AuditEvent.objects.count()
        response = self.bank.ask(self.client, self.bank.trading_key, description)
        self.assertEqual(response.status_code, 200)
        tenancy.activate(self.bank.tenant.id)
        self.assertEqual(AuditEvent.objects.count(), audit_rows, "a read writes no audit row")
        call = AgentAccessCall.objects.get(agent_access_id=self.bank.trading.id, tool="whatApplies")
        self.assertEqual((call.filters, call.record_count), ({"description": []}, 3))


class WhoMayAsk(TestCase):
    def setUp(self) -> None:
        self.bank = TradingBank()

    def test_a_person_s_session_is_not_accepted(self) -> None:
        response = self.client.post(
            WHAT_APPLIES, json.dumps({"description": ORDER_ROUTING}), content_type="application/json", **sign_in(self.bank.officer, tenant=self.bank.tenant)
        )
        self.assertEqual(response.status_code, 401)

    def test_a_key_that_is_not_an_agent_access_credential_is_refused(self) -> None:
        key = factories.api_key(self.bank.tenant, name="Bank key", scopes=("library:read",)).plain_key
        response = self.bank.ask(self.client, key)
        self.assertEqual((response.status_code, response.json()["code"]), (403, "permission_denied"))

    def test_a_personal_token_naming_no_entry_reads_the_footprint_as_its_person(self) -> None:
        token = factories.personal_token(self.bank.tenant, self.bank.officer, scopes=("library:read",)).plain_key
        response = self.bank.ask(self.client, token)
        body = response.json()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(body["scope"]["entry"])
        self.assertIn(self.bank.card.stable_key, keys(body))
        self.assertEqual(body["registerRead"], "not_granted")


class TheScopeStatement(TestCase):
    """ACC-07: every answer to an agent access credential states the scope it was given in."""

    def setUp(self) -> None:
        self.bank = TradingBank()

    def test_the_answer_states_the_entry_its_departments_and_products_and_the_date(self) -> None:
        response = self.bank.ask(self.client, self.bank.trading_key)
        scope = response.json()["scope"]
        self.assertEqual(scope["entry"], {"id": str(self.bank.trading.id), "name": "Trading platform coding agent"})
        self.assertEqual(scope["departments"], [{"id": str(self.bank.department.id), "name": "Trading"}])
        self.assertEqual((scope["products"], scope["narrowed"]), ([], True))
        self.assertEqual(datetime.date.fromisoformat(scope["asOf"]), timezone.localdate())
        self.assertEqual(json.loads(response[SCOPE_HEADER]), scope)

    def test_every_answer_carries_it_in_its_header_an_error_included(self) -> None:
        missing = self.client.get("/api/v1/register-entries/00000000-0000-4000-8000-000000000000", HTTP_X_API_KEY=self.bank.trading_key)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(json.loads(missing[SCOPE_HEADER])["entry"]["name"], "Trading platform coding agent")
        write = self.client.post("/api/v1/agent-access", "{}", content_type="application/json", HTTP_X_API_KEY=self.bank.trading_key)
        self.assertEqual(write.status_code, 403)
        self.assertIn(SCOPE_HEADER, write)

    def test_a_non_ascii_name_is_carried_in_ascii(self) -> None:
        tenancy.activate(self.bank.tenant.id)
        OrgUnit.objects.filter(pk=self.bank.department.id).update(name="Handel och värdepapper")
        response = self.bank.ask(self.client, self.bank.trading_key)
        self.assertTrue(response[SCOPE_HEADER].isascii())
        self.assertEqual(json.loads(response[SCOPE_HEADER])["departments"][0]["name"], "Handel och värdepapper")

    def test_a_person_s_answer_carries_no_statement(self) -> None:
        response = self.client.get("/api/v1/agent-access", **sign_in(self.bank.officer, tenant=self.bank.tenant))
        self.assertNotIn(SCOPE_HEADER, response)
