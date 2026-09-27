"""The library as a bank's own agent reads it (ACC-02, ACC-04, ACC-07, D-57, D-76).

An agent access credential reads the shared records inside the bank's footprint and inside
its entry's scope, on every list and every addressed read: the obligations and their card,
diff and sources, the instruments and their card and provision tree, and a provision's diff.
A record beyond any of them, the bank's own private record among them, is the same 404 an
id that names nothing gets, and the lists never name it, not as a related duty, a citing
duty, a lineage row or a count. `footprint=all` and `watched` are refused, the card answers
by stable key as well as by id, and the bank's overlay and tags are withheld unless tenant
reach is on for the bank and the entry, and even then never on a record under a standard.
A person's session is unchanged: `tests_reading.py` and `register/tests_overlay.py` hold it."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.agents.models import AgentAccess
from apps.governance.models import TenantReach
from apps.library import testing as build
from apps.library.models import Obligation
from apps.library.tests_tag_filters import tag_with, tenant_tag
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, TenantObligation
from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.testing import sign_in
from apps.taxonomy.models import TaxonomyTerm, Team
from apps.taxonomy.tests_entry_scope import EntryBank, seed, term

V1 = "/api/v1"
OBLIGATIONS = f"{V1}/obligations"
INSTRUMENTS = f"{V1}/instruments"
READS = ("library:read",)
OVERLAY = ("applicability", "complianceStatus", "firstLineOwner", "ownerTeam")
NOT_ASSESSED = {"applicability": "under_assessment", "complianceStatus": None, "firstLineOwner": None, "ownerTeam": None}


class TradingBank:
    """A bank whose footprint covers securities and payments with the derivatives, securities
    and cards product types, and ISO/IEC 27001. Its Trading department's Futures product
    carries derivatives and the standard, so
    `trading` (an entry naming that department) reads the untagged and the futures duty and
    not the card-only one; `general` names nothing and reads the whole footprint. Beside them:
    a duty under an insurance act, outside the footprint; the bank's own private act and
    duty; and ISO/IEC 27001's conformance duty, which the bank follows. The bank has decided
    every one of them applies and tagged the futures duty with a tag of its own."""

    def __init__(self, slug: str) -> None:
        seed()
        self.tenant = factories.tenant(slug=slug)
        self.bank = EntryBank(self.tenant)
        derivatives, securities, cards = (term("product_type", key) for key in ("derivatives", "securities", "cards"))
        self.standard = Obligation.objects.filter(stable_key="iso-iec-27001-2022-conformance").first() or build.standard()
        with build.library_write(build.REASON):
            TaxonomyTerm.objects.filter(dimension__key="standard", key="iso_iec_27001").update(active=True)
        self.bank.footprint(
            build.term("regime:securities"),
            build.term("regime:payments"),
            self.standard.instrument.regime,
            build.term("standard:iso_iec_27001"),
            derivatives,
            securities,
            cards,
        )
        trading = self.bank.unit("Trading")
        # An opt-in standard reaches a narrowed entry only through a product that names it (ACC-S2).
        self.bank.product("Futures", derivatives, build.term("standard:iso_iec_27001"), unit=trading)
        self.mifid = build.instrument(key=f"{slug}-mifid", regime="regime:securities")
        self.psd = build.instrument(key=f"{slug}-psd", regime="regime:payments")
        self.lfd = build.instrument(key=f"{slug}-lfd", regime="regime:insurance")
        self.untagged = build.obligation(self.mifid, key=f"{slug}-untagged")
        self.futures = build.obligation(
            self.mifid,
            key=f"{slug}-futures",
            terms=["product_type:derivatives"],
            versions=((None, {"en": "Report futures positions weekly."}), (None, {"en": "Report futures positions daily."})),
        )
        self.cards = build.obligation(self.psd, key=f"{slug}-cards", terms=["product_type:cards"])
        self.insurance = build.obligation(self.lfd, key=f"{slug}-insurance")
        self.own_act = build.instrument(key=f"{slug}-own", regime="regime:securities", owner_tenant=self.tenant)
        self.own = build.obligation(self.own_act, key=f"{slug}-own-duty", owner_tenant=self.tenant)
        build.relate(self.futures, self.cards)
        build.relate(self.futures, self.untagged)
        build.relate_instruments(self.psd, self.mifid, relation="implements")
        build.relate_instruments(self.psd, self.lfd, relation="implements")
        chapter = build.provision(self.psd, key=f"{slug}-psd-1")
        build.provision_version(chapter, texts={"en": "Card payments are authenticated."})
        build.provision_version(chapter, version_no=2, texts={"en": "Card payments are strongly authenticated."})
        self.chapter = chapter
        with build.library_write(build.REASON):
            self.cards.provisions.add(chapter)
            self.untagged.provisions.add(chapter)
        self.trading = self.bank.entry(departments=[trading], name="Trading platform coding agent")
        self.general = self.bank.entry(name="Compliance assistant")
        self.trading_key = factories.entry_key(self.tenant, SimpleNamespace(id=self.trading.id), scopes=READS).plain_key
        self.general_key = factories.entry_key(self.tenant, SimpleNamespace(id=self.general.id), scopes=READS).plain_key
        self.officer = factories.member(self.tenant, roles=("compliance_officer",)).user
        actor = Actor(kind=ActorType.USER, id=self.officer.id, label=self.officer.name)
        tenancy.activate(self.tenant.id)
        for obligation in (self.untagged, self.futures, self.cards, self.insurance, self.own, self.standard):
            with transaction.atomic():
                entry = ensure_register_entry(tenant_id=self.tenant.id, obligation_id=obligation.id, actor=actor)
            TenantObligation.objects.filter(pk=entry.pk).update(
                applicability=Applicability.APPLIES.value,
                applicability_decided_at=timezone.now(),
                applicability_decided_by=self.officer,
                owner_team=Team.objects.get(tenant=self.tenant, key="compliance"),
            )
        with transaction.atomic():
            tag_with(self.tenant, tenant_tag(self.tenant, "desk-watch", {"en": "Desk watch"}), self.futures)
            tag_with(self.tenant, tenant_tag(self.tenant, "standard-watch", {"en": "Standard watch"}), self.standard)

    def reach(self, on: bool, *entries: AgentAccess) -> None:
        tenancy.activate(self.tenant.id)
        TenantReach.objects.update_or_create(tenant=self.tenant, defaults={"enabled": on})
        AgentAccess.objects.filter(pk__in=[entry.id for entry in entries]).update(tenant_reach=on)


class AgentReadCase(TestCase):
    world: TradingBank

    @classmethod
    def setUpTestData(cls) -> None:
        cls.world = TradingBank("acc-reads")

    def setUp(self) -> None:
        cache.clear()  # the per-credential rate buckets

    def get(self, key: str, url: str, params: dict[str, Any] | None = None) -> Any:
        return self.client.get(url, params or {}, HTTP_X_API_KEY=key)

    def keys(self, key: str, url: str = OBLIGATIONS, params: dict[str, Any] | None = None) -> set[str]:
        response = self.get(key, url, {"limit": "100", **(params or {})})
        self.assertEqual(response.status_code, 200, response.content)
        return {row["stableKey"] for row in response.json()["items"]}

    def assert_not_here(self, response: Any) -> None:
        """The answer an id naming nothing gets: the same status, code and detail."""
        self.assertEqual(response.status_code, 404, response.content)
        nothing = self.get(self.world.general_key, f"{OBLIGATIONS}/00000000-0000-4000-8000-000000000000")
        self.assertEqual(response.json(), nothing.json())


class ObligationsInScope(AgentReadCase):
    def test_the_list_holds_the_shared_duties_in_the_footprint_and_in_the_entrys_scope(self) -> None:
        w = self.world
        ours = {o.stable_key for o in (w.untagged, w.futures, w.cards, w.insurance, w.own, w.standard)}
        self.assertEqual(self.keys(w.trading_key) & ours, {w.untagged.stable_key, w.futures.stable_key, w.standard.stable_key})
        self.assertEqual(
            self.keys(w.general_key) & ours, {w.untagged.stable_key, w.futures.stable_key, w.cards.stable_key, w.standard.stable_key}
        )
        # A person of the same bank sees its own private duty and, lifting the footprint, the insurance one.
        person = self.client.get(OBLIGATIONS, {"limit": "100", "footprint": "all"}, **sign_in(w.officer, tenant=w.tenant))
        self.assertTrue(ours <= {row["stableKey"] for row in person.json()["items"]})
        # The total agrees with the page.
        listed = self.get(w.trading_key, OBLIGATIONS, {"limit": 100}).json()
        self.assertEqual(listed["total"], len(listed["items"]))

    def test_footprint_all_and_watched_are_refused_by_name(self) -> None:
        for value in ("all", "watched"):
            for url in (OBLIGATIONS, INSTRUMENTS):
                with self.subTest(value=value, url=url):
                    refused = self.get(self.world.trading_key, url, {"footprint": value})
                    self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_filter"))

    def test_a_duty_outside_the_scope_is_the_404_of_a_duty_that_is_not_there(self) -> None:
        w = self.world
        for obligation in (w.cards, w.insurance, w.own):
            for address in (obligation.id, obligation.stable_key):
                for suffix in ("", "/diff", "/sources"):
                    if suffix and address == obligation.stable_key:
                        continue
                    with self.subTest(obligation=obligation.stable_key, address=address, suffix=suffix):
                        self.assert_not_here(self.get(w.trading_key, f"{OBLIGATIONS}/{address}{suffix}"))
        # The general entry reads the card duty; nothing reads the insurance or the private one.
        self.assertEqual(self.get(w.general_key, f"{OBLIGATIONS}/{w.cards.stable_key}").status_code, 200)
        for obligation in (w.insurance, w.own):
            with self.subTest(general=obligation.stable_key):
                self.assert_not_here(self.get(w.general_key, f"{OBLIGATIONS}/{obligation.id}"))

    def test_the_card_answers_by_stable_key_as_by_id(self) -> None:
        w = self.world
        by_key = self.get(w.trading_key, f"{OBLIGATIONS}/{w.futures.stable_key}")
        by_id = self.get(w.trading_key, f"{OBLIGATIONS}/{w.futures.id}")
        self.assertEqual(by_key.status_code, 200, by_key.content)
        self.assertEqual(by_key.json(), by_id.json())
        self.assertEqual(by_key.json()["id"], str(w.futures.id))
        self.assertEqual(self.get(w.trading_key, f"{OBLIGATIONS}/{w.futures.id}/diff").status_code, 200)
        self.assertEqual(self.get(w.trading_key, f"{OBLIGATIONS}/{w.futures.id}/sources").status_code, 200)
        self.assert_not_here(self.get(w.trading_key, f"{OBLIGATIONS}/no-such-duty"))

    def test_the_card_names_no_related_duty_outside_the_scope(self) -> None:
        w = self.world
        related = {row["id"] for row in self.get(w.trading_key, f"{OBLIGATIONS}/{w.futures.id}").json()["related"]}
        self.assertEqual(related, {str(w.untagged.id)})
        widest = {row["id"] for row in self.get(w.general_key, f"{OBLIGATIONS}/{w.futures.id}").json()["related"]}
        self.assertEqual(widest, {str(w.untagged.id), str(w.cards.id)})

    def test_an_entry_naming_what_derives_nothing_reads_nothing(self) -> None:
        w = self.world
        back_office = w.bank.entry(departments=[w.bank.unit("Back office")], name="Back office")
        key = factories.entry_key(w.tenant, SimpleNamespace(id=back_office.id), scopes=READS).plain_key
        self.assertEqual(self.get(key, OBLIGATIONS).json(), {"items": [], "total": 0})
        self.assert_not_here(self.get(key, f"{OBLIGATIONS}/{w.untagged.id}"))

    def test_a_personal_token_naming_no_entry_reads_the_footprint_and_never_a_private_record(self) -> None:
        w = self.world
        token = factories.personal_token(w.tenant, w.officer, scopes=READS).plain_key
        ours = {o.stable_key for o in (w.untagged, w.futures, w.cards, w.insurance, w.own, w.standard)}
        self.assertEqual(self.keys(token) & ours, ours - {w.insurance.stable_key, w.own.stable_key})
        self.assert_not_here(self.get(token, f"{OBLIGATIONS}/{w.own.id}"))
        self.assertNotIn(w.own_act.stable_key, self.keys(token, INSTRUMENTS))


class InstrumentsInScope(AgentReadCase):
    def test_the_instruments_list_and_counts_follow_the_scope(self) -> None:
        w = self.world
        listed = {row["stableKey"]: row for row in self.get(w.trading_key, INSTRUMENTS, {"limit": 100}).json()["items"]}
        self.assertIn(w.mifid.stable_key, listed)
        self.assertNotIn(w.lfd.stable_key, listed)
        self.assertNotIn(w.own_act.stable_key, listed)
        # The card-only duty is not counted for the trading entry, and is for the general one.
        self.assertEqual(listed[w.psd.stable_key]["obligationCount"], 0)
        self.assertEqual(listed[w.mifid.stable_key]["obligationCount"], 2)
        general = {row["stableKey"]: row for row in self.get(w.general_key, INSTRUMENTS, {"limit": 100}).json()["items"]}
        self.assertEqual(general[w.psd.stable_key]["obligationCount"], 1)

    def test_an_instrument_outside_is_not_here_and_lineage_names_none(self) -> None:
        w = self.world
        for instrument in (w.lfd, w.own_act):
            for suffix in ("", "/provisions"):
                with self.subTest(instrument=instrument.stable_key, suffix=suffix):
                    self.assert_not_here(self.get(w.trading_key, f"{INSTRUMENTS}/{instrument.id}{suffix}"))
        lineage = self.get(w.trading_key, f"{INSTRUMENTS}/{w.psd.id}").json()["lineage"]
        self.assertEqual([row["instrument"]["key"] for row in lineage], [w.mifid.stable_key])

    def test_the_provision_tree_names_no_citing_duty_outside_the_scope(self) -> None:
        w = self.world
        tree = self.get(w.trading_key, f"{INSTRUMENTS}/{w.psd.id}/provisions").json()
        self.assertEqual([row["id"] for row in tree[0]["obligations"]], [str(w.untagged.id)])
        widest = self.get(w.general_key, f"{INSTRUMENTS}/{w.psd.id}/provisions").json()
        self.assertEqual({row["id"] for row in widest[0]["obligations"]}, {str(w.untagged.id), str(w.cards.id)})

    def test_a_provision_of_an_instrument_outside_is_not_here(self) -> None:
        w = self.world
        chapter = build.provision(w.lfd, key="acc-reads-lfd-1")
        build.provision_version(chapter)
        build.provision_version(chapter, version_no=2, texts={"en": "The provision as amended."})
        self.assert_not_here(self.get(w.trading_key, f"{V1}/provisions/{chapter.id}/diff"))
        self.assertEqual(self.get(w.trading_key, f"{V1}/provisions/{w.chapter.id}/diff").status_code, 200)


class TheBanksLayer(AgentReadCase):
    """The overlay and the bank's own tags reach an agent only through the register's gate."""

    def rows(self, key: str) -> dict[str, Any]:
        return {row["stableKey"]: row for row in self.get(key, OBLIGATIONS, {"limit": 100}).json()["items"]}

    def test_without_reach_the_rows_and_the_card_carry_the_library_alone(self) -> None:
        w = self.world
        w.reach(False, w.trading)
        rows = self.rows(w.trading_key)
        for key in (w.untagged.stable_key, w.futures.stable_key):
            with self.subTest(key=key):
                self.assertEqual({field: rows[key][field] for field in OVERLAY}, NOT_ASSESSED)
                self.assertEqual(rows[key]["tenantTags"], [])
                self.assertIs(rows[key]["privateToUs"], False)
        card = self.get(w.trading_key, f"{OBLIGATIONS}/{w.futures.id}").json()
        self.assertEqual({field: card[field] for field in OVERLAY}, NOT_ASSESSED)
        self.assertEqual(card["tenantTags"], [])
        # The bank's own entry is on and the bank's switch is off: still the library alone.
        w.reach(False)
        tenancy.activate(w.tenant.id)
        AgentAccess.objects.filter(pk=w.trading.id).update(tenant_reach=True)
        self.assertEqual(self.rows(w.trading_key)[w.futures.stable_key]["applicability"], "under_assessment")

    def test_without_reach_a_filter_over_the_banks_layer_is_refused(self) -> None:
        w = self.world
        w.reach(False, w.trading)
        for params in ({"applicability": "applies"}, {"ownerTeam": "compliance"}, {"tenantTag": "desk-watch"}):
            with self.subTest(params=params):
                refused = self.get(w.trading_key, OBLIGATIONS, params)
                self.assertEqual((refused.status_code, refused.json()["code"]), (403, "tenant_reach_off"))

    def test_with_reach_on_the_overlay_shows_except_under_a_standard(self) -> None:
        w = self.world
        w.reach(True, w.trading)
        rows = self.rows(w.trading_key)
        self.assertEqual(rows[w.futures.stable_key]["applicability"], "applies")
        self.assertEqual(rows[w.futures.stable_key]["ownerTeam"]["key"], "compliance")
        self.assertEqual([tag["key"] for tag in rows[w.futures.stable_key]["tenantTags"]], ["desk-watch"])
        self.assertEqual({field: rows[w.standard.stable_key][field] for field in OVERLAY}, NOT_ASSESSED)
        self.assertEqual(rows[w.standard.stable_key]["tenantTags"], [])
        card = self.get(w.trading_key, f"{OBLIGATIONS}/{w.standard.id}").json()
        self.assertEqual({field: card[field] for field in OVERLAY}, NOT_ASSESSED)
        filtered = self.keys(w.trading_key, params={"applicability": "applies"})
        self.assertEqual(filtered & {w.futures.stable_key, w.standard.stable_key}, {w.futures.stable_key})
        # Another entry of the bank whose own toggle is off reads the library alone.
        self.assertEqual(self.rows(w.general_key)[w.futures.stable_key]["applicability"], "under_assessment")
