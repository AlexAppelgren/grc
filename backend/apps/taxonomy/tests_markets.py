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
from apps.shared.tenancy import library_write
from apps.taxonomy import markets_logic
from apps.taxonomy.models import FootprintTerm, TaxonomyTerm, TermDimension, WatchedMarket
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions


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


class OperatingReadsTheMirrorLink(TestCase):
    """A market is operating when a footprint term links to its jurisdiction (FP-S12, D-28),
    whatever that term or its dimension is called. Proven to fail 2026-09-23 against the
    read it replaced, which looked for the jurisdiction's key under the literal dimension key
    `jurisdiction`: renaming the dimension's key left Sweden reading as not followed."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.sweden = Jurisdiction.objects.get(key="se")
        self.company = factories.tenant(slug="markets-mirror")

    def _level(self, key: str) -> str:
        return next(row.level for row in markets_logic.markets_of(self.company.id, ["en"]) if row.jurisdiction.key == key)

    def test_a_renamed_mirror_still_reads_as_operating(self) -> None:
        term = TaxonomyTerm.objects.get(jurisdiction=self.sweden)
        with library_write("test: a mirror renamed by hand"):
            TermDimension.objects.filter(pk=term.dimension_id).update(key="market")
            TaxonomyTerm.objects.filter(pk=term.pk).update(key="sweden")
        tenancy.activate(self.company.id)
        FootprintTerm.objects.create(tenant=self.company, term=term)
        self.assertEqual(self._level("se"), markets_logic.OPERATING)
