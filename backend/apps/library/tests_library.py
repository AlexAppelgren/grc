"""The library's data layer (chunk 3): the "as of" rule, the demo loader and the zone
rules the new tables carry (INV-01..INV-06, AC-INV1, INPUT_DELTAS §3, §5).

The API scenarios INV-S1..S10 live in tests_scenarios.py and land with the read API."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from io import StringIO

from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, IntegrityError, ProgrammingError, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from apps.library.logic import in_force
from apps.library.models import (
    Instrument,
    Jurisdiction,
    Obligation,
    ObligationSummary,
    ObligationVersion,
    ProblemReport,
    Provision,
    ReportStatus,
    SubjectType,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import RESEARCH_OBLIGATION, load_library, seed_authorities
from apps.shared import factories, tenancy
from apps.shared.e2e_seed import SeedRefused
from apps.shared.models import AuditEvent, Tenant
from apps.shared.tenancy import LibraryWriteRefused, library_write
from apps.taxonomy.models import InstrumentLevel
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms


@dataclass(frozen=True)
class V:
    version_number: int
    effective_from: datetime.date | None


D = datetime.date


class InForceTests(SimpleTestCase):
    """AC-INV1, data-model §4: the latest effective_from on or before the date; null is
    since always."""

    def test_null_means_since_always(self) -> None:
        first = V(1, None)
        self.assertIs(in_force([first], D(1900, 1, 1)), first)

    def test_the_latest_on_or_before_the_date_wins(self) -> None:
        first, second = V(1, D(2025, 1, 1)), V(2, D(2026, 10, 1))
        self.assertIs(in_force([second, first], D(2026, 6, 30)), first)
        self.assertIs(in_force([first, second], D(2026, 10, 1)), second, "on the effective date itself the new version applies")
        self.assertIs(in_force([first, second], D(2026, 9, 30)), first, "the day before it the old one still does")

    def test_a_future_version_is_not_in_force_yet(self) -> None:
        first, future = V(1, None), V(2, D(2026, 10, 1))
        self.assertIs(in_force([first, future], D(2026, 9, 16)), first)
        self.assertIs(in_force([first, future], D(2027, 1, 1)), future)

    def test_nothing_is_in_force_before_the_first_dated_version(self) -> None:
        self.assertIsNone(in_force([V(1, D(2025, 1, 1))], D(2024, 12, 31)))
        self.assertIsNone(in_force([], D(2026, 1, 1)))

    def test_a_tie_goes_to_the_higher_version_number(self) -> None:
        first, correction = V(1, D(2025, 1, 1)), V(2, D(2025, 1, 1))
        self.assertIs(in_force([correction, first], D(2025, 6, 1)), correction)


def seed_library() -> dict[str, int]:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_taxonomy_terms()
    seed_authorities()
    return load_library()


class LibraryLoaderTests(TestCase):
    def test_the_loader_files_the_prototype_library(self) -> None:
        counts = seed_library()
        self.assertEqual(counts, {"instruments": 15, "provisions": 2, "obligations": 15, "obligation_versions": 16})
        lvm = Instrument.objects.get(stable_key="sfs-2007-528")
        self.assertIsNone(lvm.owner_tenant_id, "a seeded record is shared")
        self.assertEqual((lvm.level.key, lvm.jurisdiction.key, lvm.authority and lvm.authority.key), ("act", "se", "riksdagen"))
        self.assertEqual((lvm.in_force_from, lvm.in_force_from_precision), (D(2007, 11, 1), "day"))
        title = lvm.titles.get()
        self.assertEqual((title.language_id, title.is_original, title.is_machine), ("sv", True, False))
        self.assertEqual(
            {(r.to_instrument.stable_key, r.relation_type.key) for r in lvm.relations_out.all()}, {("celex-32014l0065", "implements")}
        )
        chapter = Provision.objects.get(stable_key="sfs-2007-528/9")
        self.assertEqual((chapter.kind.key, chapter.ref_label, chapter.sort_order), ("chapter", "9 kap.", 9))

        obligation = Obligation.objects.get(stable_key="obl-appropriateness")
        self.assertEqual(obligation.duty_type.key, "conduct")
        self.assertEqual(obligation.source_url, lvm.source_url)
        self.assertIsNotNone(obligation.last_verified_at)
        self.assertIn("appropriateness", set(obligation.tags.values_list("key", flat=True)))
        self.assertIn("account_type:isk", {f"{t.dimension.key}:{t.key}" for t in obligation.terms.select_related("dimension")})
        self.assertEqual(list(obligation.provisions.values_list("stable_key", flat=True)), ["sfs-2007-528/9"])
        self.assertEqual(set(obligation.relations_out.values_list("to_obligation__stable_key", flat=True)), {"obl-esma-warnings"})
        self.assertEqual(obligation.titles.get().language_id, "en")

    def test_summaries_keep_the_original_and_label_the_translation(self) -> None:
        seed_library()
        version = ObligationVersion.objects.get(obligation__stable_key="obl-appropriateness", version_number=1)
        rows = {row.language_id: (row.is_original, row.is_machine) for row in version.summaries.all()}
        self.assertEqual(rows, {"sv": (True, False), "en": (False, True)})

    def test_the_research_payment_obligation_has_a_future_second_version(self) -> None:
        seed_library()
        versions = list(ObligationVersion.objects.filter(obligation__stable_key=RESEARCH_OBLIGATION))
        self.assertEqual([(v.version_number, v.effective_from) for v in versions], [(1, None), (2, D(2026, 10, 1))])
        self.assertIs(in_force(versions, D(2026, 9, 16)), versions[0])
        self.assertIs(in_force(versions, D(2026, 10, 1)), versions[1])

    def test_the_loader_is_idempotent_and_audits_each_record_once(self) -> None:
        seed_library()
        audited = AuditEvent.objects.filter(action="library.seeded").count()
        self.assertEqual(audited, 8 + 15 + 15, "one audit row per authority, instrument and obligation")
        summaries = ObligationSummary.objects.count()
        self.assertEqual(load_library(), {"instruments": 15, "provisions": 2, "obligations": 15, "obligation_versions": 16})
        self.assertEqual(seed_authorities(), 8)
        self.assertEqual(AuditEvent.objects.filter(action="library.seeded").count(), audited)
        self.assertEqual(ObligationSummary.objects.count(), summaries)

    def test_library_rows_refuse_a_write_outside_the_fence(self) -> None:
        seed_library()
        instrument = Instrument.objects.get(stable_key="sfs-2007-528")
        with self.assertRaises(LibraryWriteRefused):
            instrument.save()
        with self.assertRaises(LibraryWriteRefused):
            ObligationVersion.objects.filter(obligation__stable_key=RESEARCH_OBLIGATION).update(version_number=3)

    def test_a_version_number_is_unique_per_obligation(self) -> None:
        seed_library()
        with self.assertRaises(IntegrityError), transaction.atomic(), library_write("test"):
            ObligationVersion.objects.create(obligation=Obligation.objects.get(stable_key=RESEARCH_OBLIGATION), version_number=2)

    def test_seed_demo_prints_counts_and_refuses_a_deployed_environment(self) -> None:
        out = StringIO()
        call_command("seed_demo", stdout=out)
        self.assertIn("obligations: 15", out.getvalue())
        with override_settings(IS_DEPLOYED_ENVIRONMENT=True, ENVIRONMENT="prod"), self.assertRaises(SeedRefused):
            call_command("seed_demo", stdout=StringIO())


class SharedOrMineIsolation(TransactionTestCase):
    """INPUT_DELTAS §5, INV-07: a tenant-private instrument is visible to its owner only;
    shared rows to everyone. problem_report is mixed: a tenant's reports are its own."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
        self.tenant_a = factories.tenant(slug="lib-a")
        self.tenant_b = factories.tenant(slug="lib-b")
        self.reporter = factories.user(email="reporter@lib-a.test")

    def _instrument(self, key: str, owner: Tenant | None) -> Instrument:
        with library_write("test"):
            return Instrument.objects.using("app").create(
                stable_key=key,
                short_name=key,
                official_ref=key,
                source_url="https://example.test/",
                level=InstrumentLevel.objects.get(key="act"),
                binding=True,
                jurisdiction=Jurisdiction.objects.get(key="se"),
                owner_tenant=owner,
                created_origin="user",
            )

    def test_a_private_instrument_is_visible_to_its_owner_only(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            self._instrument("shared", None)
            self._instrument("mine", self.tenant_a)
        for tenant, expected in ((self.tenant_a, {"shared", "mine"}), (self.tenant_b, {"shared"})):
            with transaction.atomic(using="app"):
                tenancy.activate(tenant.id, using="app")
                self.assertEqual(set(Instrument.objects.using("app").values_list("stable_key", flat=True)), expected)
        with self.assertRaises(ProgrammingError), transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            self._instrument("forged", self.tenant_a)

    def test_a_problem_report_stays_with_its_tenant(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            ProblemReport.objects.using("app").create(
                tenant=self.tenant_a,
                reporter=self.reporter,
                subject_type=SubjectType.OBLIGATION.value,
                subject_id=self.tenant_a.id,
                text="The retention period looks wrong.",
            )
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            self.assertFalse(ProblemReport.objects.using("app").exists())
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            self.assertEqual(ProblemReport.objects.using("app").get().status, ReportStatus.OPEN.value)
