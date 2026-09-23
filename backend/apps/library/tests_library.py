"""The library's data layer (chunk 3): the "as of" rule, the demo loader and the zone
rules the new tables carry (INV-01..INV-06, AC-INV1, INPUT_DELTAS §3, §5).

The API scenarios INV-S1..S10 live in tests_scenarios.py and land with the read API."""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from io import StringIO
from typing import Any
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, IntegrityError, ProgrammingError, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from apps.library import testing as build
from apps.library.fixtures.check_prototype_data import FIXTURE, Checker
from apps.library.logic import in_force
from apps.library.models import (
    Instrument,
    InstrumentRelation,
    Jurisdiction,
    JurisdictionKind,
    Obligation,
    ObligationSummary,
    ObligationVersion,
    ProblemReport,
    Provision,
    ReportStatus,
    SubjectType,
)
from apps.library.seeds import JURISDICTIONS, seed_jurisdictions, seed_languages
from apps.library.seeds.library import RESEARCH_OBLIGATION, load_library, seed_authorities
from apps.shared import factories, tenancy
from apps.shared.e2e_seed import SeedRefused
from apps.shared.models import AuditEvent, Tenant
from apps.shared.tenancy import LibraryWriteRefused, library_write
from apps.taxonomy.models import InstrumentLevel, InstrumentLevelKind, ProvisionKind, TaxonomyTerm
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.seeds import MIRRORED_JURISDICTION_KINDS, fixture, seed_library_vocabularies, seed_taxonomy_terms


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
        self.assertEqual(counts, {"instruments": 16, "provisions": 9, "obligations": 16, "obligation_versions": 17})
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

    def test_an_instrument_is_verified_when_its_latest_obligation_was_or_on_the_anchor_date(self) -> None:
        """INV-06: every record carries a verified date. The fixture dates obligations only,
        so an instrument takes the latest date among its obligations, or the fixture's
        anchor date when it has none. The loader names no verifier: the fixture's is a
        tenant user."""
        seed_library()
        stockholm = ZoneInfo("Europe/Stockholm")
        # LVM's obligations were verified 2026-08-28, 2026-08-28 and 2026-09-10.
        self.assertEqual(Instrument.objects.get(stable_key="sfs-2007-528").last_verified_at, datetime.datetime(2026, 9, 10, tzinfo=stockholm))
        # MiFID II has no obligation: the anchor date, 2026-09-16.
        self.assertEqual(Instrument.objects.get(stable_key="celex-32014l0065").last_verified_at, datetime.datetime(2026, 9, 16, tzinfo=stockholm))
        for instrument in Instrument.objects.prefetch_related("obligations"):
            with self.subTest(instrument=instrument.stable_key):
                dates = [o.last_verified_at for o in instrument.obligations.all() if o.last_verified_at]
                expected = max(dates) if dates else datetime.datetime(2026, 9, 16, tzinfo=stockholm)
                self.assertEqual(instrument.last_verified_at, expected)
        self.assertFalse(Instrument.objects.exclude(verified_by=None).exists())
        self.assertFalse(Obligation.objects.exclude(verified_by=None).exists())

    def test_fffs_2026_11_amends_fffs_2017_2_and_takes_the_anchor_date(self) -> None:
        """T8, INV-01: the sample amending instrument carries no obligation of its own, so
        its verified date falls to the fixture's anchor date (T2's rule)."""
        seed_library()
        stockholm = ZoneInfo("Europe/Stockholm")
        amendment = Instrument.objects.get(stable_key="fffs-2026-11")
        assert amendment.authority is not None
        self.assertEqual((amendment.jurisdiction.key, amendment.authority.key, amendment.binding), ("se", "fi", True))
        self.assertEqual((amendment.in_force_from, amendment.in_force_from_precision), (D(2026, 10, 1), "day"))
        self.assertEqual(amendment.last_verified_at, datetime.datetime(2026, 9, 16, tzinfo=stockholm))
        relation = InstrumentRelation.objects.get(from_instrument=amendment, to_instrument__stable_key="fffs-2017-2")
        self.assertEqual(relation.relation_type.key, "amends")

    def test_the_advice_only_sample_obligation_is_filed_with_one_translated_version(self) -> None:
        """J-6: the one obligation whose only service is advice, added to the prototype's
        library (from_prototype false) so switching off Advice hides something."""
        seed_library()
        obligation = Obligation.objects.select_related("instrument__jurisdiction").get(stable_key="obl-suitability-statement")
        self.assertEqual(obligation.instrument.jurisdiction.key, "se")
        self.assertEqual({t.key for t in obligation.terms.filter(dimension__key="service_type")}, {"advice"})
        self.assertIsNotNone(obligation.last_verified_at)
        version = obligation.versions.get()
        self.assertEqual((version.version_number, version.effective_from), (1, None))
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
        filed = AuditEvent.objects.filter(action="library.seeded", subject_type__in=("authority", "instrument", "obligation"))
        audited = filed.count()
        self.assertEqual(audited, 8 + 16 + 16, "one audit row per authority, instrument and obligation")
        summaries = ObligationSummary.objects.count()
        self.assertEqual(load_library(), {"instruments": 16, "provisions": 9, "obligations": 16, "obligation_versions": 17})
        self.assertEqual(seed_authorities(), 8)
        self.assertEqual(filed.count(), audited)
        self.assertEqual(ObligationSummary.objects.count(), summaries)

    def test_the_fffs_provision_tree_has_three_levels_and_is_audited_once_each(self) -> None:
        """T8, INV-02, INV-S2: chapter, section and paragraph, 9 kap. 6 §'s amendment still
        in the future on the fixture's anchor date, and one library.seeded audit row per
        provision stable key, none of them written again on reload."""
        seed_library()
        chapter = Provision.objects.get(stable_key="fffs-2017-2/9")
        section = Provision.objects.get(stable_key="fffs-2017-2/9-6")
        paragraph = Provision.objects.get(stable_key="fffs-2017-2/9-6-1")
        self.assertIsNone(chapter.parent_id)
        self.assertEqual(section.parent_id, chapter.id)
        self.assertEqual(paragraph.parent_id, section.id)
        self.assertEqual((chapter.kind.key, section.kind.key, paragraph.kind.key), ("chapter", "section", "paragraph"))

        versions = list(section.versions.order_by("version_number"))
        self.assertEqual([v.version_number for v in versions], [1, 2])
        self.assertEqual(versions[0].effective_from, D(2018, 1, 3))
        self.assertEqual(versions[1].effective_from, D(2026, 10, 1))
        assert versions[1].effective_from is not None
        self.assertGreater(versions[1].effective_from, D(2026, 9, 16), "the amendment is still ahead of the anchor date")
        self.assertEqual(versions[0].transitional_note, "")
        self.assertTrue(versions[1].transitional_note)
        self.assertIsNone(versions[0].effective_to, "nothing is stored; every read derives it")

        stable_keys = {"fffs-2017-2/9", "fffs-2017-2/9-6", "fffs-2017-2/9-6-1", "fffs-2017-2/9-10", "fffs-2017-2/9-23", "fffs-2017-2/10", "fffs-2017-2/11"}
        audited = AuditEvent.objects.filter(action="library.seeded", subject_type="provision", subject_title__in=stable_keys)
        self.assertEqual(audited.count(), len(stable_keys), "one audit row per provision stable key")
        load_library()
        self.assertEqual(
            AuditEvent.objects.filter(action="library.seeded", subject_type="provision", subject_title__in=stable_keys).count(),
            len(stable_keys),
            "a second load writes none",
        )

    def test_every_seeded_instrument_carries_a_regime_from_the_regime_dimension(self) -> None:
        """INV-S12's seed half (D-39): the regime is the sector boundary, so every seeded
        instrument has one and it is a term of `regime`, never of another dimension."""
        seed_library()
        dimensions = {row.stable_key: row.regime.dimension.key for row in Instrument.objects.select_related("regime__dimension")}
        self.assertIn("fffs-2017-2", dimensions)
        self.assertEqual(set(dimensions.values()), {"regime"})

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
        self.assertIn("obligations: 16", out.getvalue())
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
            seed_taxonomy_terms()
        self.tenant_a = factories.tenant(slug="lib-a")
        self.tenant_b = factories.tenant(slug="lib-b")
        self.reporter = factories.user(email="reporter@lib-a.test")

    def _instrument(self, key: str, owner: Tenant | None, *, level: str = "act") -> Instrument:
        with library_write("test"):
            return Instrument.objects.using("app").create(
                stable_key=key,
                short_name=key,
                official_ref=key,
                source_url="https://example.test/",
                level=InstrumentLevel.objects.get(key=level),
                binding=level != "standard",
                jurisdiction=Jurisdiction.objects.get(key="se"),
                regime=build.term("regime:securities"),
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

    def _provision(self, under: Instrument, key: str) -> Provision:
        with library_write("test"):
            return Provision.objects.using("app").create(
                stable_key=key, instrument=under, kind=ProvisionKind.objects.using("app").get(key="chapter"), ref_label="1", path=f"{under.short_name} > 1"
            )

    def test_no_zone_writes_a_provision_under_an_instrument_it_cannot_see(self) -> None:
        """D-35, INV-07: `provision_not_under_standard` runs as the writer, and row-level
        security hides another zone's instrument from it, so it fails closed. Under a bank's
        private standard no zone writes a provision, the bank's own included; under its
        private law only the bank does, never another bank or the library."""
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            policy = self._instrument("bank-a-policy", self.tenant_a)
            standard = self._instrument("bank-a-standard", self.tenant_a, level="standard")
            self._provision(policy, "bank-a-policy/1")
        for zone, under in (
            (self.tenant_a, standard),
            (self.tenant_b, standard),
            (None, standard),
            (self.tenant_b, policy),
            (None, policy),
        ):
            with (
                self.subTest(zone=zone.slug if zone else "library", under=under.stable_key),
                self.assertRaisesMessage(IntegrityError, "provision_not_under_standard"),
                transaction.atomic(using="app"),
            ):
                if zone:
                    tenancy.activate(zone.id, using="app")
                self._provision(under, f"{under.stable_key}/{zone.slug if zone else 'library'}")
        self.assertEqual(list(Provision.objects.using("app").values_list("stable_key", flat=True)), ["bank-a-policy/1"])
        # Nor does the library turn a level into a standard while it cannot see where a
        # provision sits: bank A's is at `act`, hidden from it, and `eu_guidance` is refused too.
        with self.assertRaisesMessage(IntegrityError, "provision_not_under_standard"), transaction.atomic(using="app"), library_write("test"):
            InstrumentLevel.objects.using("app").filter(key="eu_guidance").update(kind=InstrumentLevelKind.STANDARD.value)

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

    def test_a_report_is_open_or_closed_with_who_when_and_a_note(self) -> None:
        """library 0009 (AUD-03): the database refuses a closed report missing who closed it,
        when or why, and an open one carrying any of the three."""
        now = datetime.datetime.now(tz=datetime.UTC)
        closed: dict[str, Any] = {"status": ReportStatus.FIXED.value, "resolution_note": "Checked against the source.", "closed_by": self.reporter, "closed_at": now}
        broken: list[dict[str, Any]] = [
            {**closed, "resolution_note": ""},
            {**closed, "closed_by": None},
            {**closed, "closed_at": None},
            {"resolution_note": "A note on an open report."},
            {"closed_at": now},
        ]
        for fields in broken:
            with self.subTest(fields=sorted(fields)):
                with self.assertRaisesMessage(IntegrityError, "problem_report_closed_with_note"), transaction.atomic(using="app"):
                    tenancy.activate(self.tenant_a.id, using="app")
                    self._report(**fields)
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            self.assertEqual(self._report(**closed).status, ReportStatus.FIXED.value)

    def _report(self, **fields: Any) -> ProblemReport:
        return ProblemReport.objects.using("app").create(
            tenant=self.tenant_a,
            reporter=self.reporter,
            subject_type=SubjectType.OBLIGATION.value,
            subject_id=self.tenant_a.id,
            text="The retention period looks wrong.",
            **fields,
        )


class JurisdictionReach(TestCase):
    """`Jurisdiction.parent` is the jurisdiction whose rules reach this one (D-28, ADR 0026),
    not membership of a union: Norway is outside the Union and still reached by EU financial
    rules through the EEA Agreement, so a bank operating only there must see EU law."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()

    def test_every_seeded_country_is_reached_by_the_union(self) -> None:
        reach = {row.key: row.parent.key if row.parent else None for row in Jurisdiction.objects.select_related("parent")}
        # International (D-38) is reached by nothing: a standards body is no market's rule-maker.
        self.assertEqual(reach, {"eu": None, "se": "eu", "dk": "eu", "no": "eu", "fi": "eu", "intl": None})

    def test_the_fixture_and_the_seed_name_the_same_reach(self) -> None:
        """The two places T15 had to change. They are read by different code paths — the seed
        writes the rows, the fixture loader writes the prototype's records against them — so a
        later edit to one alone would leave the two lists disagreeing with nothing to say so."""
        fixture_reach = {
            row["code"].lower(): (row["parent_code"] or "").lower() or None for row in fixture.load()["jurisdictions"]
        }
        seeded_reach = {key: parent for key, (_, parent, _, _) in JURISDICTIONS.items()}
        self.assertEqual(fixture_reach, seeded_reach)


class StandardsAndRegimes(TestCase):
    """INV-01, INV-02, INV-08, AC-INV2 (D-35, D-37, D-38, D-39): the standard level, the
    International jurisdiction, the required regime and the provision trigger, pinned where
    they live, in the seed and in the database. The proposal half of INV-S12 (`not_a_regime`
    at apply) comes with the instrument proposal kind; INV-S11's screen and seeded standard
    come after this."""

    standard: Instrument
    law: Instrument
    chapter: Provision

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        cls.standard = build.instrument(key="iso-iec-27001-2022", short_name="ISO/IEC 27001:2022", regime="regime:ai_ict", level="standard", binding=False)
        cls.law = build.instrument(key="fffs-2017-2", short_name="FFFS 2017:2", regime="regime:securities", level="authority_regulation")
        cls.chapter = build.provision(cls.law, key="fffs-2017-2/9", ref_label="9 kap.")

    def test_standard_is_the_one_level_with_a_kind_and_binds_nobody_by_default(self) -> None:
        levels = {row.key: row for row in InstrumentLevel.objects.prefetch_related("labels")}
        standard = levels.pop("standard")
        self.assertEqual((standard.kind, standard.binding_default, standard.is_system, standard.active), (InstrumentLevelKind.STANDARD.value, False, True, True))
        self.assertEqual({label.language: label.text for label in standard.labels.all()}, {"en": "Standard", "sv": "Standard"})
        self.assertTrue(levels, "the law and guidance levels are seeded beside it")
        self.assertEqual({row.kind for row in levels.values()}, {None}, "every other level stays kindless and is read by `binding`")
        self.assertGreater(standard.rank, max(row.rank for row in levels.values()), "a standard ranks below every law")
        entry = REGISTRY["instrument_level"]
        self.assertEqual((entry.kind_name, entry.kinds, entry.kind_required), ("instrument_level_kind", ("standard",), False))

    def test_international_is_seeded_for_standards_bodies_and_never_mirrored_as_a_market(self) -> None:
        intl = Jurisdiction.objects.select_related("default_language").prefetch_related("labels").get(key="intl")
        self.assertEqual(
            (intl.kind, intl.parent_id, intl.default_language.key, intl.is_system, intl.is_default, intl.active),
            (JurisdictionKind.INTERNATIONAL.value, None, "en", True, False, True),
        )
        self.assertEqual({label.language: label.text for label in intl.labels.all()}, {"en": "International", "sv": "Internationell"})
        self.assertNotIn(intl.kind, MIRRORED_JURISDICTION_KINDS)
        self.assertFalse(TaxonomyTerm.objects.filter(jurisdiction=intl).exists(), "no bank operates in International")

    def test_the_database_refuses_an_instrument_without_a_regime(self) -> None:
        with self.assertRaises(IntegrityError) as caught, transaction.atomic(), library_write("test"):
            Instrument.objects.create(
                stable_key="no-regime",
                short_name="No regime",
                official_ref="NO REGIME",
                source_url=build.SOURCE_URL,
                level=InstrumentLevel.objects.get(key="act"),
                binding=True,
                jurisdiction=Jurisdiction.objects.get(key="se"),
                created_origin="user",
            )
        self.assertIn("regime_id", str(caught.exception))
        self.assertFalse(Instrument.objects.filter(stable_key="no-regime").exists())

    def test_the_database_refuses_a_provision_under_a_standard(self) -> None:
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            build.provision(self.standard, key="iso-iec-27001-2022/1", ref_label="1")
        self.assertIn("provision_not_under_standard", str(caught.exception))
        self.assertFalse(Provision.objects.filter(instrument=self.standard).exists())

    def test_the_database_refuses_moving_a_provision_under_a_standard(self) -> None:
        with self.assertRaises(IntegrityError) as caught, transaction.atomic(), library_write("test"):
            Provision.objects.filter(pk=self.chapter.pk).update(instrument=self.standard)
        self.assertIn("provision_not_under_standard", str(caught.exception))
        self.assertEqual(Provision.objects.get(pk=self.chapter.pk).instrument_id, self.law.id)

    def test_the_database_refuses_moving_an_instrument_that_holds_provisions_onto_a_standard_level(self) -> None:
        standard = InstrumentLevel.objects.get(key="standard")
        with self.assertRaises(IntegrityError) as caught, transaction.atomic(), library_write("test"):
            Instrument.objects.filter(pk=self.law.pk).update(level=standard)
        self.assertIn("provision_not_under_standard", str(caught.exception))
        self.assertEqual(Instrument.objects.get(pk=self.law.pk).level.key, "authority_regulation")
        empty = build.instrument(key="sfs-2007-528", short_name="LVM", regime="regime:securities")
        with library_write("test"):
            Instrument.objects.filter(pk=empty.pk).update(level=standard)
        self.assertEqual(Instrument.objects.get(pk=empty.pk).level.key, "standard", "an instrument holding no provision may be filed as a standard")

    def test_the_database_refuses_turning_a_level_that_holds_provisions_into_a_standard(self) -> None:
        with self.assertRaises(IntegrityError) as caught, transaction.atomic(), library_write("test"):
            InstrumentLevel.objects.filter(key="authority_regulation").update(kind=InstrumentLevelKind.STANDARD.value)
        self.assertIn("provision_not_under_standard", str(caught.exception))
        self.assertIsNone(InstrumentLevel.objects.get(key="authority_regulation").kind)
        # A deploy still puts the kind back on the standard level itself, which holds no provision.
        with library_write("test"):
            InstrumentLevel.objects.filter(key="standard").update(kind=None)
        seed_library_vocabularies()
        self.assertEqual(InstrumentLevel.objects.get(key="standard").kind, InstrumentLevelKind.STANDARD.value)

    def test_a_provision_under_law_is_written_and_moved_as_before(self) -> None:
        other = build.instrument(key="sfs-2007-528", short_name="LVM", regime="regime:securities")
        with library_write("test"):
            Provision.objects.filter(pk=self.chapter.pk).update(instrument=other, heading="Investment advice")
        self.assertEqual(Provision.objects.get(pk=self.chapter.pk).instrument_id, other.id)
        self.assertEqual(build.provision(self.law, key="fffs-2017-2/10", ref_label="10 kap.").instrument_id, self.law.id)


class FixtureCheck(SimpleTestCase):
    """check_prototype_data.py (INV-01, INV-08, D-35, D-39): the prototype fixture passes its
    own check, and the check refuses the two things the database refuses too, before a seed
    ever runs."""

    def load(self) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
        return data

    def test_the_fixture_passes_its_own_check(self) -> None:
        self.assertEqual(Checker(self.load()).run(), [])

    def test_a_regime_must_be_a_term_of_the_regime_dimension(self) -> None:
        data = self.load()
        instruments = {row["stable_key"]: row for row in data["instruments"]}
        instruments["sfs-2007-528"]["regime"] = "service_type:advice"
        instruments["fffs-2017-2"]["regime"] = None
        problems = Checker(data).run()
        self.assertIn("instruments.sfs-2007-528: regime 'service_type:advice' is not a term of the regime dimension", problems)
        self.assertIn("instruments.fffs-2017-2: regime is required", problems)

    def test_no_provision_may_sit_under_a_standard(self) -> None:
        data = self.load()
        instruments = {row["stable_key"]: row for row in data["instruments"]}
        instruments["sfs-2007-528"]["level"] = "standard"
        self.assertIn(
            "provisions.sfs-2007-528/9: a standard's text is licensed, so no provision sits under one", Checker(data).run()
        )
