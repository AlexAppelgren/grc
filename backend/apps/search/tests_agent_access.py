"""`POST /search` as a bank's own agent calls it (SRC-01, ACC-02, ACC-04, ACC-05, D-10).

A key holding `search:read` searches the library as a person does; an agent access
credential's search is then narrowed by its entry's scope over the same scope the footprint
judges (`hybrid._filtered`), so a trading agent never finds a card rule and an entry that
names nothing finds what the bank's footprint holds. It cannot lift the footprint
(`inFootprint` false is refused by name), a key without the scope is refused, and a person's
search is what it was."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.core.cache import cache
from django.test import TestCase

from apps.identity.models import User
from apps.library import testing as build
from apps.library.models import Obligation
from apps.search import indexing
from apps.shared import factories
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.tests_entry_scope import EntryBank, seed, term

SEARCH = "/api/v1/search"
SUMMARY = "Settle every {what} trade within two business days of the trade date."


class AgentSearch(TestCase):
    """One bank whose footprint covers securities and payments with the derivatives and
    cards product types. Its Trading department's product carries derivatives. Three duties
    share the word "settle": a futures one, a card-only one and one under an insurance act
    outside the footprint."""

    tenant: Tenant
    futures: Obligation
    cards: Obligation
    insurance: Obligation
    trading_key: str
    general_key: str
    library_only_key: str
    person: User

    @classmethod
    def setUpTestData(cls) -> None:
        seed()
        cls.tenant = factories.tenant(slug="acc-search")
        bank = EntryBank(cls.tenant)
        derivatives, cards = term("product_type", "derivatives"), term("product_type", "cards")
        bank.footprint(build.term("regime:securities"), build.term("regime:payments"), derivatives, cards)
        trading = bank.unit("Trading")
        bank.product("Futures", derivatives, unit=trading)
        mifid = build.instrument(key="acc-search-mifid", regime="regime:securities")
        psd = build.instrument(key="acc-search-psd", regime="regime:payments")
        lfd = build.instrument(key="acc-search-lfd", regime="regime:insurance")
        cls.futures = build.obligation(
            mifid, key="acc-search-futures", terms=["product_type:derivatives"], versions=((None, {"en": SUMMARY.format(what="futures")}),)
        )
        cls.cards = build.obligation(
            psd, key="acc-search-cards", terms=["product_type:cards"], versions=((None, {"en": SUMMARY.format(what="card")}),)
        )
        cls.insurance = build.obligation(lfd, key="acc-search-insurance", versions=((None, {"en": SUMMARY.format(what="insurance")}),))
        indexing.reindex_all()
        cls.trading_key = factories.entry_key(cls.tenant, SimpleNamespace(id=bank.entry(departments=[trading], name="Trading agent").id), scopes=("search:read",)).plain_key
        cls.general_key = factories.entry_key(cls.tenant, SimpleNamespace(id=bank.entry(name="Assistant").id), scopes=("search:read",)).plain_key
        cls.library_only_key = factories.entry_key(cls.tenant, SimpleNamespace(id=bank.entry(name="Reader").id), scopes=("library:read",)).plain_key
        cls.person = factories.member(cls.tenant, roles=("compliance_officer",)).user

    def setUp(self) -> None:
        cache.clear()  # the per-caller rate buckets

    def post(self, body: dict[str, Any], *, key: str | None = None) -> Any:
        headers = {"HTTP_X_API_KEY": key} if key else sign_in(self.person, tenant=self.tenant)
        return self.client.post(SEARCH, body, content_type="application/json", **headers)

    def found(self, *, key: str | None = None) -> set[str]:
        response = self.post({"q": "settle trade", "lang": "en", "types": ["obligation"]}, key=key)
        self.assertEqual(response.status_code, 200, response.content)
        return {hit["title"] for hit in response.json()["items"]} & {"acc-search-futures", "acc-search-cards", "acc-search-insurance"}

    def test_an_entry_finds_only_what_its_scope_opens(self) -> None:
        self.assertEqual(self.found(key=self.trading_key), {"acc-search-futures"})

    def test_an_entry_naming_nothing_finds_the_footprint(self) -> None:
        self.assertEqual(self.found(key=self.general_key), {"acc-search-futures", "acc-search-cards"})

    def test_a_person_searches_as_before(self) -> None:
        self.assertEqual(self.found(), {"acc-search-futures", "acc-search-cards"})

    def test_an_agent_cannot_search_outside_the_scope(self) -> None:
        refused = self.post({"q": "settle", "filters": {"inFootprint": False}}, key=self.trading_key)
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_filter"))
        # A person still may: that is the screen's "Search outside our scope".
        outside = self.post({"q": "settle trade", "lang": "en", "filters": {"inFootprint": False}})
        self.assertIn("acc-search-insurance", {hit["title"] for hit in outside.json()["items"]})

    def test_a_key_without_search_read_is_refused(self) -> None:
        refused = self.post({"q": "settle"}, key=self.library_only_key)
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "permission_denied"))
        self.assertEqual(refused.json()["requiredPermission"], "search:read")
