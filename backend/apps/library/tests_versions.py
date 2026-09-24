"""Versions are written once and compared by sentence (chunk 3, INV-02, INV-04, INV-05,
AC-INV1).

The version, text and verification tables refuse UPDATE and DELETE in the database, for the
application role too, so "as of" and "show what changed" read a history nothing can
rewrite. The sentence diff and the choice of the language it is shown in are pure
functions; the read routes only resolve the versions and serialize (INV-S2, INV-S4, INV-S5)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from unittest import mock

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, DatabaseError, connection, connections, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from apps.library.logic import sentence_diff, split_sentences, version_diff
from apps.library.models import (
    Instrument,
    Jurisdiction,
    Obligation,
    ObligationSummary,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
    SubjectType,
    Verification,
    VerificationOutcome,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import load_library, seed_authorities
from apps.shared.tenancy import LibraryModel, library_door, library_write
from apps.taxonomy.models import DutyType, InstrumentLevel, ProvisionKind, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

APPEND_ONLY: tuple[type[LibraryModel], ...] = (ProvisionVersion, ProvisionText, ObligationVersion, ObligationSummary, Verification)
# Per table, a realistic rewrite and a delete: what "nothing overwritten" forbids.
REFUSED = {
    "provision_version": (
        "UPDATE provision_version SET effective_to = '2027-01-01' WHERE id = %s",
        "DELETE FROM provision_version WHERE id = %s",
    ),
    "provision_text": ("UPDATE provision_text SET text = 'Rewritten.' WHERE id = %s", "DELETE FROM provision_text WHERE id = %s"),
    "obligation_version": (
        "UPDATE obligation_version SET effective_from = '2027-01-01' WHERE id = %s",
        "DELETE FROM obligation_version WHERE id = %s",
    ),
    "obligation_summary": (
        "UPDATE obligation_summary SET text = 'Rewritten.' WHERE id = %s",
        "DELETE FROM obligation_summary WHERE id = %s",
    ),
    "verification": ("UPDATE verification SET outcome = 'change_found' WHERE id = %s", "DELETE FROM verification WHERE id = %s"),
}
# The maintenance hatch is the schema owner's alone (apps/shared/tests_append_only.py).
# As cw_app it buys nothing, in either spelling of the case-insensitive setting name.
HATCHES = ("", "SET LOCAL cw.maintenance = 'on'", "SET LOCAL CW.MAINTENANCE = 'on'")


class VersionTablesAreAppendOnly(TransactionTestCase):
    """As cw_app, the production role, a version, text or verification row is inserted and
    never updated or deleted, with or without the maintenance hatch set. Committed rows, so
    the proof runs on the app connection."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_taxonomy_terms()

    def _insert_one_row_each(self) -> dict[str, uuid.UUID]:
        app = "app"
        with transaction.atomic(using=app), library_write("test"), library_door("seed", using=app):
            instrument = Instrument.objects.using(app).create(
                stable_key="fffs-2017-2",
                short_name="FFFS 2017:2",
                official_ref="FFFS 2017:2",
                source_url="https://www.fi.se/",
                level=InstrumentLevel.objects.using(app).get(key="act"),
                binding=True,
                jurisdiction=Jurisdiction.objects.using(app).get(key="se"),
                regime=TaxonomyTerm.objects.using(app).get(dimension__key="regime", key="securities"),
                created_origin="user",
            )
            provision = Provision.objects.using(app).create(
                stable_key="fffs-2017-2/9",
                instrument=instrument,
                kind=ProvisionKind.objects.using(app).get(key="chapter"),
                ref_label="9 kap.",
                path="FFFS 2017:2 > 9 kap.",
            )
            provision_version = ProvisionVersion.objects.using(app).create(provision=provision, version_number=1)
            provision_text = ProvisionText.objects.using(app).create(
                version=provision_version, language_id="sv", text="Ett institut ska bedöma kunden.", is_original=True
            )
            obligation = Obligation.objects.using(app).create(
                stable_key="obl-versions-probe",
                instrument=instrument,
                ref_label="9 kap. 6 §",
                duty_type=DutyType.objects.using(app).get(key="conduct"),
                created_origin="user",
                source_url="https://www.fi.se/",
                source_label="FFFS 2017:2, 9 kap. 6 §",
            )
            obligation_version = ObligationVersion.objects.using(app).create(obligation=obligation, version_number=1)
            summary = ObligationSummary.objects.using(app).create(
                version=obligation_version, language_id="sv", text="Institutet bedömer kunden.", is_original=True
            )
            verification = Verification.objects.using(app).create(
                subject_type=SubjectType.OBLIGATION.value, subject_id=obligation.id, outcome=VerificationOutcome.NO_CHANGE.value
            )
        return {
            "provision_version": provision_version.id,
            "provision_text": provision_text.id,
            "obligation_version": obligation_version.id,
            "obligation_summary": summary.id,
            "verification": verification.id,
        }

    def test_the_app_role_inserts_but_never_updates_or_deletes(self) -> None:
        rows = self._insert_one_row_each()
        self.assertEqual(set(rows), {model._meta.db_table for model in APPEND_ONLY})
        with connections["app"].cursor() as cursor:
            cursor.execute("SELECT current_user")
            self.assertEqual(cursor.fetchone(), ("cw_app",))
            for table, row_id in rows.items():
                for statement in REFUSED[table]:
                    for hatch in HATCHES:
                        with self.subTest(statement=statement, hatch=hatch):
                            # Inside an approved proposal's door, so the database's door
                            # check (H16) lets the statement reach the append-only trigger.
                            with (
                                self.assertRaisesMessage(DatabaseError, f"{table} is append-only"),
                                transaction.atomic(using="app"),
                                library_door("proposal", using="app"),
                            ):
                                if hatch:
                                    cursor.execute(hatch)
                                cursor.execute(statement, [row_id])
        for model in APPEND_ONLY:
            with self.subTest(table=model._meta.db_table):
                self.assertEqual(model.objects.using("app").count(), 1, "the row is still there")
        self.assertIsNone(ProvisionVersion.objects.using("app").get().effective_to, "effective_to is derived, never set")
        self.assertEqual(ObligationSummary.objects.using("app").get().text, "Institutet bedömer kunden.")


class TheLoaderUnderTheTriggers(TestCase):
    def test_load_library_runs_twice_with_the_triggers_in_place(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tgrelid::regclass::text FROM pg_trigger WHERE tgname = ANY(%s) AND tgenabled = 'O'",
                [[f"{model._meta.db_table}_append_only" for model in APPEND_ONLY]],
            )
            self.assertEqual({table for (table,) in cursor.fetchall()}, {model._meta.db_table for model in APPEND_ONLY})
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        seed_authorities()
        counts = load_library()
        rows = {model: model.objects.count() for model in APPEND_ONLY}
        self.assertGreater(rows[ObligationVersion], 0)
        self.assertEqual(load_library(), counts)
        self.assertEqual({model: model.objects.count() for model in APPEND_ONLY}, rows)


class SplitSentences(SimpleTestCase):
    """The unit of "show what changed" (INV-04): a legal reference is never cut in two."""

    def test_a_chapter_and_section_reference_stays_whole(self) -> None:
        self.assertEqual(
            split_sentences("Enligt 9 kap. 6 § LVM ska institutet bedöma kunden. Kunden ska varnas."),
            ["Enligt 9 kap. 6 § LVM ska institutet bedöma kunden.", "Kunden ska varnas."],
        )
        self.assertEqual(
            split_sentences("Under art. 13 the firm informs the client. Records are kept."),
            ["Under art. 13 the firm informs the client.", "Records are kept."],
        )

    def test_never_after_a_legal_abbreviation(self) -> None:
        for abbreviation in ("kap.", "art.", "p.", "nr.", "t.ex.", "bl.a.", "m.m.", "jfr.", "e.g.", "i.e.", "Art.", "T.ex.", "(jfr."):
            with self.subTest(abbreviation=abbreviation):
                text = f"Rapportera {abbreviation} Finansinspektionen och kunden. Spara underlaget."
                self.assertEqual(split_sentences(text), [f"Rapportera {abbreviation} Finansinspektionen och kunden.", "Spara underlaget."])

    def test_never_before_a_digit_or_a_section_sign(self) -> None:
        self.assertEqual(len(split_sentences("Uppgifterna lämnas enligt punkt 2. 3 § gäller också.")), 1)
        self.assertEqual(len(split_sentences("Institutet följer lagen. § 4 gäller också.")), 1)

    def test_a_danish_or_norwegian_date_stays_whole(self) -> None:
        self.assertEqual(
            split_sentences("Reglerne gælder fra den 1. januar 2026. Instituttet skal vurdere kunden."),
            ["Reglerne gælder fra den 1. januar 2026.", "Instituttet skal vurdere kunden."],
        )

    def test_question_marks_exclamation_marks_and_line_breaks(self) -> None:
        self.assertEqual(
            split_sentences("  Passar tjänsten? Varna kunden!\n\nDokumentera bedömningen.  "),
            ["Passar tjänsten?", "Varna kunden!", "Dokumentera bedömningen."],
        )
        self.assertEqual(split_sentences("   "), [])
        self.assertEqual(split_sentences("Ingen punkt på slutet"), ["Ingen punkt på slutet"])

    def test_200_kb_of_boundaries_never_taken_splits_at_once(self) -> None:
        """Security review: each refused boundary used to re-split the growing sentence,
        quadratic on untrusted text (200 KB of "a. a." took minutes). Now linear."""
        for unit in ("Bestämmelsen gäller. 1 § ", "a. ", "bl.a. Finansinspektionen "):
            text = unit * (200_000 // len(unit))
            started = time.perf_counter()
            sentences = split_sentences(text)
            elapsed = time.perf_counter() - started
            self.assertEqual(sentences, [text.strip()], unit)
            self.assertLess(elapsed, 2.0, unit)


class SentenceDiff(SimpleTestCase):
    """AC-INV1: the diff marks the changed sentence and leaves the others unchanged."""

    def test_one_changed_sentence_is_a_delete_and_an_insert(self) -> None:
        old = "Institutet ska bedöma kunden enligt 9 kap. 6 § LVM. Om tjänsten inte passar ska kunden varnas. Bedömningen dokumenteras."
        new = "Institutet ska bedöma kunden enligt 9 kap. 6 § LVM. Om tjänsten inte passar, eller uppgifter saknas, ska kunden varnas. Bedömningen dokumenteras."
        self.assertEqual(
            sentence_diff(old, new),
            [
                ("equal", "Institutet ska bedöma kunden enligt 9 kap. 6 § LVM."),
                ("delete", "Om tjänsten inte passar ska kunden varnas."),
                ("insert", "Om tjänsten inte passar, eller uppgifter saknas, ska kunden varnas."),
                ("equal", "Bedömningen dokumenteras."),
            ],
        )

    def test_an_added_sentence_is_an_insert(self) -> None:
        old = "Research is paid from own resources. It may be paid jointly with execution."
        new = old + " The institution assesses the research every year."
        self.assertEqual(
            sentence_diff(old, new),
            [
                ("equal", "Research is paid from own resources."),
                ("equal", "It may be paid jointly with execution."),
                ("insert", "The institution assesses the research every year."),
            ],
        )

    def test_the_same_texts_always_give_the_same_segments(self) -> None:
        old, new = "Kunden varnas. Kunden varnas. Beslutet sparas.", "Kunden varnas. Beslutet sparas. Kunden varnas."
        expected = [
            ("delete", "Kunden varnas."),
            ("equal", "Kunden varnas."),
            ("equal", "Beslutet sparas."),
            ("insert", "Kunden varnas."),
        ]
        self.assertEqual(sentence_diff(old, new), expected)
        self.assertEqual(sentence_diff(old, new), expected)
        self.assertEqual(sentence_diff(old, old), [("equal", "Kunden varnas."), ("equal", "Kunden varnas."), ("equal", "Beslutet sparas.")])
        self.assertEqual(sentence_diff("", "Beslutet sparas."), [("insert", "Beslutet sparas.")])

    def test_the_worst_case_at_the_cap_stays_inside_the_endpoint_budget(self) -> None:
        """Security review: aligning many repeated sentences is cubic, so the sentence count is
        capped; this is the worst shape measured, at the cap, still sentence by sentence."""
        cap = settings.LIBRARY_DIFF_MAX_SENTENCES
        repealed, amended = "Upphävd. " * cap, "Upphävd. Ny text. " * (cap // 2)
        for old, new in ((repealed, amended), (amended, repealed)):
            started = time.perf_counter()
            segments = sentence_diff(old, new)
            elapsed_ms = (time.perf_counter() - started) * 1000
            self.assertLess(elapsed_ms, settings.API_BUDGET_MS)
            self.assertEqual(len(segments), cap + cap // 2, "one segment per sentence")

    def test_above_the_cap_the_whole_text_is_one_delete_and_one_insert(self) -> None:
        old, new = "Upphävd. " * 800, "Upphävd. Ny text. " * 400  # 21 s before the cap
        started = time.perf_counter()
        self.assertEqual(sentence_diff(old, new), [("delete", old.strip()), ("insert", new.strip())])
        same = "Upphävd. " * 2000  # under LIBRARY_TEXT_MAX_CHARS, so both texts are still split
        self.assertEqual(sentence_diff(same, same), [("equal", "Upphävd.")] * 2000, "unchanged is never a change")
        self.assertLess((time.perf_counter() - started) * 1000, settings.API_BUDGET_MS)
        with override_settings(LIBRARY_DIFF_MAX_SENTENCES=2):
            self.assertEqual(
                sentence_diff("Kunden varnas. Beslutet sparas.", "Kunden varnas. Beslutet sparas. Ny text."),
                [("delete", "Kunden varnas. Beslutet sparas."), ("insert", "Kunden varnas. Beslutet sparas. Ny text.")],
            )
            self.assertEqual(sentence_diff("", " A. B. C. "), [("insert", "A. B. C.")])
            self.assertEqual(sentence_diff("A. B. C.", ""), [("delete", "A. B. C.")])
            self.assertEqual(sentence_diff("A. B.", "A. C."), [("equal", "A."), ("delete", "B."), ("insert", "C.")], "at the cap")

    def test_a_text_longer_than_the_character_cap_is_never_split(self) -> None:
        """Security review: a text is what a source published, and splitting it is linear in
        its length with nothing bounding that length. Above LIBRARY_TEXT_MAX_CHARS neither
        text is split at all, which the patched splitter proves."""
        cap = settings.LIBRARY_TEXT_MAX_CHARS
        old, new = "Ab. " * cap, "Cd. " * cap  # four times the cap, 20,000 sentences each
        with mock.patch("apps.library.logic.split_sentences", side_effect=AssertionError("split")):
            started = time.perf_counter()
            self.assertEqual(sentence_diff(old, new), [("delete", old.strip()), ("insert", new.strip())])
            self.assertLess((time.perf_counter() - started) * 1000, settings.API_BUDGET_MS)
            self.assertEqual(sentence_diff(old, old), [("equal", old.strip())], "unchanged is never a change")
            self.assertEqual(sentence_diff(old, ""), [("delete", old.strip())])
            self.assertEqual(sentence_diff("", new), [("insert", new.strip())])
        with override_settings(LIBRARY_TEXT_MAX_CHARS=20):
            self.assertEqual(
                sentence_diff("Kunden varnas. Beslutet sparas.", "Kunden varnas."),
                [("delete", "Kunden varnas. Beslutet sparas."), ("insert", "Kunden varnas.")],
            )
            self.assertEqual(
                sentence_diff("Kunden varnas.", "Kunden varnas."), [("equal", "Kunden varnas.")], "short enough to split"
            )


@dataclass(frozen=True)
class Text:
    language_id: str
    text: str
    is_original: bool = False
    is_machine: bool = False


OLD = [Text("sv", "Kunden varnas.", is_original=True), Text("en", "The client is warned.", is_machine=True)]
NEW = [
    Text("sv", "Kunden varnas. Beslutet sparas.", is_original=True),
    Text("en", "The client is warned. The decision is kept.", is_machine=True),
]


def language_and_flag(old: list[Text], new: list[Text], order: list[str], lang: str | None) -> tuple[str, bool]:
    result = version_diff(old, new, order, lang)
    assert result is not None
    return result[0], result[1]


class VersionDiff(SimpleTestCase):
    """INV-04, INV-05: the diff is shown in a language both versions have, and says which
    one and whether it is a machine translation."""

    def test_the_requested_language_comes_first(self) -> None:
        self.assertEqual(
            version_diff(OLD, NEW, ["en"], "sv"),
            ("sv", False, [("equal", "Kunden varnas."), ("insert", "Beslutet sparas.")]),
        )

    def test_then_the_language_order(self) -> None:
        expected = ("en", True, [("equal", "The client is warned."), ("insert", "The decision is kept.")])
        self.assertEqual(version_diff(OLD, NEW, ["da", "en", "sv"], None), expected)
        self.assertEqual(version_diff(OLD, NEW, ["en", "sv"], "fi"), expected, "a language neither version has is passed over")
        self.assertEqual(language_and_flag(OLD, NEW[:1], ["en", "sv"], "en"), ("sv", False), "en only in one version")

    def test_then_the_original_then_any_shared_language(self) -> None:
        old = [Text("da", "Kunden advares.", is_machine=True), Text("sv", "Kunden varnas.", is_original=True)]
        new = [Text("da", "Kunden advares straks.", is_machine=True), Text("sv", "Kunden varnas genast.", is_original=True)]
        self.assertEqual(language_and_flag(old, new, ["en"], None), ("sv", False), "the original before a machine translation")
        self.assertEqual(language_and_flag(old[:1], new[:1], ["en"], None), ("da", True))

    def test_a_machine_translation_on_either_side_labels_the_diff(self) -> None:
        human = [Text("en", "The client is warned.", is_original=True)]
        machine = [Text("en", "The client is warned at once.", is_machine=True)]
        self.assertEqual(language_and_flag(human, machine, ["en"], None), ("en", True))
        self.assertEqual(language_and_flag(machine, human, ["en"], None), ("en", True))
        self.assertEqual(language_and_flag(human, human, ["en"], None), ("en", False))

    def test_two_versions_that_share_no_language_have_no_diff(self) -> None:
        self.assertIsNone(version_diff([Text("sv", "Kunden varnas.", is_original=True)], [Text("en", "The client is warned.")], ["en", "sv"], "sv"))
        self.assertIsNone(version_diff([], NEW, ["en"], None))
