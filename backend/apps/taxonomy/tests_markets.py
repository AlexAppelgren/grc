"""The watched-market row (FP-04, D-30, INPUT_DELTAS §1).

A tenant watches a market by naming a jurisdiction: one row per tenant per jurisdiction,
in the tenant zone under forced row-level security, keeping the jurisdiction it names
alive. The markets logic, its routes and the screen are later slices; these pin what the
table itself promises, because a second row or a vanished jurisdiction would be a silent
wrong answer everywhere the level is computed from these rows.

Forced row-level security and the tenant policy are proved for every tenant table at once
by apps/shared/tests_rls.py (NFR-S3), so they are not repeated here.

Proven to fail 2026-09-19 in a scratch copy: without `watched_market_unique` the second
watch of the same market landed as a second row, and with the jurisdiction foreign key on
CASCADE the delete took the watch row with it instead of being refused.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.library.models import Jurisdiction
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.taxonomy.models import WatchedMarket


class WatchedMarketRow(TestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        self.norway = Jurisdiction.objects.get(key="no")

    def test_a_tenant_watches_a_market_once(self) -> None:
        company = factories.tenant(slug="markets-once")
        WatchedMarket.objects.create(tenant=company, jurisdiction=self.norway)
        with self.assertRaises(IntegrityError), transaction.atomic():
            WatchedMarket.objects.create(tenant=company, jurisdiction=self.norway)

    def test_two_tenants_watch_the_same_market(self) -> None:
        first = factories.tenant(slug="markets-first")
        WatchedMarket.objects.create(tenant=first, jurisdiction=self.norway)
        second = factories.tenant(slug="markets-second")
        WatchedMarket.objects.create(tenant=second, jurisdiction=self.norway)
        # The second tenant is the activated one, so its own row is all it sees.
        self.assertEqual([row.tenant_id for row in WatchedMarket.objects.all()], [second.id])
        tenancy.activate(first.id)
        self.assertEqual([row.tenant_id for row in WatchedMarket.objects.all()], [first.id])

    def test_a_watched_jurisdiction_cannot_be_deleted(self) -> None:
        company = factories.tenant(slug="markets-protect")
        watch = WatchedMarket.objects.create(tenant=company, jurisdiction=self.norway)
        with self.assertRaises(ProtectedError) as refused, transaction.atomic():
            Jurisdiction.objects.filter(pk=self.norway.pk).delete()
        self.assertEqual([row.pk for row in refused.exception.protected_objects], [watch.pk])
