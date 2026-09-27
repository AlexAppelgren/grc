"""`GET /upcoming` as a bank's own agent reads it (HOM-04, ACC-02, ACC-04, ACC-07).

An agent access credential holding `upcoming:read` gets the dated changes inside its bank's
footprint and its entry's scope, judged over the scope the watch feed judges a change by. It
stays library-only: every row it gets is byte for byte the row a person gets, so nothing of
the bank is joined in for it. A person's list, and a key that is no agent access
credential's, are what they were (`tests_calendar.py`)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.identity.models import User
from apps.library import testing as build
from apps.shared import factories
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.tests_entry_scope import EntryBank, seed, term
from apps.watch import testing as watch_build

URL = "/api/v1/upcoming"


class AgentUpcoming(TestCase):
    """A bank whose footprint covers securities with the derivatives and cards product
    types; its Trading department's product carries derivatives. Four changes are dated
    ahead: one on futures, one on cards, one on nothing in particular and one under the
    insurance regime, outside the footprint."""

    tenant: Tenant
    titles: dict[str, str]
    trading_key: str
    general_key: str
    person: User

    @classmethod
    def setUpTestData(cls) -> None:
        seed()
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="acc-upcoming")
        bank = EntryBank(cls.tenant)
        derivatives, cards = term("product_type", "derivatives"), term("product_type", "cards")
        bank.footprint(build.term("regime:securities"), derivatives, cards)
        trading = bank.unit("Trading")
        bank.product("Futures", derivatives, unit=trading)
        ahead = timezone.localdate() + datetime.timedelta(days=30)
        cls.titles = {}
        for name, ref in (("futures", "product_type:derivatives"), ("cards", "product_type:cards"), ("insurance", "regime:insurance"), ("general", None)):
            change = watch_build.change(title=f"acc-upcoming {name}", authority=None, key_date=ahead)
            if ref is not None:
                watch_build.term_link(change, term_ref=ref)
            cls.titles[name] = change.title
        cls.trading_key = factories.entry_key(cls.tenant, SimpleNamespace(id=bank.entry(departments=[trading], name="Trading agent").id), scopes=("upcoming:read",)).plain_key
        cls.general_key = factories.entry_key(cls.tenant, SimpleNamespace(id=bank.entry(name="Assistant").id), scopes=("upcoming:read",)).plain_key
        cls.person = factories.member(cls.tenant, roles=("compliance_officer",)).user

    def setUp(self) -> None:
        cache.clear()  # the per-credential rate buckets

    def rows(self, key: str | None = None) -> dict[str, Any]:
        headers = {"HTTP_X_API_KEY": key} if key else sign_in(self.person, tenant=self.tenant)
        response = self.client.get(URL, {"limit": 100}, **headers)
        self.assertEqual(response.status_code, 200, response.content)
        ours = set(self.titles.values())
        return {row["title"]: row for row in response.json() if row["title"] in ours}

    def named(self, *names: str) -> set[str]:
        return {self.titles[name] for name in names}

    def test_an_entry_reads_the_changes_its_scope_opens(self) -> None:
        self.assertEqual(set(self.rows(self.trading_key)), self.named("futures", "general"))

    def test_an_entry_naming_nothing_reads_the_footprint(self) -> None:
        self.assertEqual(set(self.rows(self.general_key)), self.named("futures", "cards", "general"))

    def test_a_person_reads_every_change_as_before(self) -> None:
        self.assertEqual(set(self.rows()), self.named("futures", "cards", "insurance", "general"))

    def test_what_an_agent_reads_is_the_library_row_everyone_reads(self) -> None:
        everyone = self.rows()
        for title, row in self.rows(self.trading_key).items():
            with self.subTest(title=title):
                self.assertEqual(row, everyone[title])
