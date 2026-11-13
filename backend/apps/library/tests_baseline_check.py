"""check_baseline.py over a tranche's provisions, the law's own words (INV-02, INV-05; Alex,
2026-11-13: "we need to correctly have the original text").

The baseline's provisions arrive as `baseline/provisions/<tranche>.json`, produced by script
from the official sources. The checker is what holds a file to the rules the proposal door
does not know: which translations stand beside an original, that each is marked, where the
text was read, and that no obligation of a tranche is left without its text silently. Proved
here on a folder of its own: a good file passes, each rule refuses the one entry that breaks
it, a folder with no provisions file passes as it always did, and the real baseline passes
whole. The tables the checker spells out for itself, since it runs without Django, are
pinned against the seeds and the settings they restate.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings
from django.test import SimpleTestCase

from apps.library.baseline import check_baseline
from apps.library.seeds import JURISDICTIONS
from apps.taxonomy.seeds import LIBRARY_SYSTEM_ROWS

TRANCHE = "test"
SOURCE = "https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/sfs-2099-1/"
TEXTS = {
    "sv": "Ett intygande ska vara undertecknat och daterat.",
    "da": "En egenerklæring skal være underskrevet og dateret.",
    "nb": "En egenerklæring skal være undertegnet og datert.",
    "fi": "Vakuutuksen on oltava allekirjoitettu ja päivätty.",
    "en": "A self-certification must be signed and dated.",
}
# The tranche the provisions belong to: one instrument per jurisdiction, each with its duties.
INSTRUMENTS = {
    "se-act": ("se", ["obl-se-one", "obl-se-two"]),
    "dk-act": ("dk", ["obl-dk"]),
    "no-act": ("no", ["obl-no"]),
    "fi-act": ("fi", ["obl-fi"]),
    "eu-act": ("eu", ["obl-eu"]),
}


def provision(instrument: str, original: str, languages: str, *duties: str, **fields: Any) -> dict[str, Any]:
    """A provision of `instrument` with a text in each of `languages`, cited by `duties`."""
    return {
        "key": f"{instrument}/005",
        "instrument": instrument,
        "provisionKind": "section",
        "refLabel": "5 §",
        "path": "005",
        "heading": None,
        "texts": {language: TEXTS[language] for language in languages.split()},
        "originalLanguage": original,
        "obligations": list(duties),
        "source": SOURCE,
        "sourceLabel": "Riksdagen, Svensk författningssamling, SFS 2099:1, 5 §, text as amended up to SFS 2099:9",
        "readOn": "2026-11-13",
        **fields,
    }


def good() -> dict[str, Any]:
    """A provisions file every rule passes: each original in its jurisdiction's language,
    English beside all but English, Swedish beside Danish, Norwegian and Finnish, Finland's
    Swedish the authority's own, and the one duty with no text excused by name."""
    return {
        "tranche": TRANCHE,
        "researchedOn": "2026-11-13",
        "provisions": [
            provision("se-act", "sv", "sv en", "obl-se-one", isMachine=True, heading="Intygande"),
            provision("dk-act", "da", "da en sv", "obl-dk", isMachine=True),
            provision("no-act", "nb", "nb en sv", "obl-no", isMachine=True),
            provision("fi-act", "fi", "fi sv en", "obl-fi", isMachine=True, officialLanguages=["sv"]),
            provision("eu-act", "en", "en", "obl-eu", provisionKind="article", refLabel="Art. 5"),
        ],
        "withoutProvision": [{"obligation": "obl-se-two", "reason": "The duty rests on the ordinance as a whole; no one section states it."}],
    }


class TheLawsOwnWords(SimpleTestCase):
    def setUp(self) -> None:
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        instruments = [
            {"payload": {"key": key, "jurisdiction": jurisdiction}, "obligations": [{"payload": {"key": duty}} for duty in duties]}
            for key, (jurisdiction, duties) in INSTRUMENTS.items()
        ]
        (self.folder / f"{TRANCHE}.json").write_text(json.dumps({"tranche": TRANCHE, "instruments": instruments}), encoding="utf-8")
        (self.folder / check_baseline.PROVISIONS_DIR).mkdir()

    def problems(self, data: Any = None, *, name: str = TRANCHE) -> list[str]:
        """What the checker says of the folder once `data` is its provisions file."""
        if data is not None:
            text = data if isinstance(data, str) else json.dumps(data)
            (self.folder / check_baseline.PROVISIONS_DIR / f"{name}.json").write_text(text, encoding="utf-8")
        checker = check_baseline.Checker()
        checker.provisions(self.folder)
        return checker.problems

    def test_a_good_file_passes_and_a_folder_with_none_passes_as_before(self) -> None:
        self.assertEqual(self.problems(), [], "no provisions file at all")
        self.assertEqual(self.problems(good()), [])

    def test_each_rule_refuses_the_entry_that_breaks_it(self) -> None:
        def entry(index: int, **fields: Any) -> Callable[[dict[str, Any]], None]:
            """Change fields of the provision at `index`; a value of `...` removes the field."""

            def change(data: dict[str, Any]) -> None:
                for name, value in fields.items():
                    if value is ...:
                        data["provisions"][index].pop(name, None)
                    else:
                        data["provisions"][index][name] = value

            return change

        def whole(**fields: Any) -> Callable[[dict[str, Any]], None]:
            return lambda data: data.update(fields)

        swedish, danish, finnish, union = 0, 1, 3, 4
        long = "x" * (check_baseline.MAX_TEXT + 1)
        cases: list[tuple[str, Callable[[dict[str, Any]], None], str]] = [
            ("a field the file does not know", whole(note="later"), "provisions/test.json: unknown field 'note'"),
            ("a field a provision does not know", entry(swedish, sortOrder=5), "[se-act/005]: unknown field 'sortOrder'"),
            ("the tranche is the file's name", whole(tranche="other"), "tranche must be the file's name, 'test'"),
            ("an instrument of another tranche", entry(swedish, instrument="sfs-1999-1", key="sfs-1999-1/005"), ".instrument: 'sfs-1999-1' is not an instrument of this tranche"),
            ("an obligation nobody holds", entry(swedish, obligations=["obl-nobody"]), ".obligations: 'obl-nobody' is not an obligation under 'se-act' in this tranche"),
            ("an obligation of another instrument", entry(swedish, obligations=["obl-se-one", "obl-dk"]), ".obligations: 'obl-dk' is not an obligation under 'se-act' in this tranche"),
            ("no obligation at all", entry(swedish, obligations=[]), ".obligations: must list the keys of the obligations that cite the provision, at least one and at most 50"),
            ("an obligation named twice", entry(swedish, obligations=["obl-se-one", "obl-se-one"]), ".obligations: names an obligation twice"),
            ("English as the original of Swedish law", entry(swedish, originalLanguage="en"), ".originalLanguage: must be 'sv', the language se-act is written in"),
            ("no text in the original", entry(swedish, texts={"en": TEXTS["en"]}), ".texts: has no text in its original language 'sv'"),
            ("no English beside Swedish", entry(swedish, texts={"sv": TEXTS["sv"]}, isMachine=...), ".texts: lacks en: beside an original in 'sv' a provision carries en"),
            ("no Swedish beside Danish", entry(danish, texts={"da": TEXTS["da"], "en": TEXTS["en"]}), ".texts: lacks sv: beside an original in 'da' a provision carries en, sv"),
            ("an empty text", entry(swedish, texts={"sv": TEXTS["sv"], "en": " "}), ".texts.en: must be a non-empty string"),
            ("a text over the door's maximum", entry(swedish, texts={"sv": long, "en": TEXTS["en"]}), ".texts.sv: is 50001 characters, at most 50000"),
            ("a language the library does not hold", entry(union, texts={"en": TEXTS["en"], "de": "Ein Text."}, isMachine=True), ".texts.de: is not a content language"),
            ("a Swedish text beside a Union act", entry(union, texts={"en": TEXTS["en"], "sv": TEXTS["sv"]}, isMachine=True), ".texts: holds sv: beside an original in 'en' a provision carries nothing"),
            ("a Danish text beside Swedish law", entry(swedish, texts={"sv": TEXTS["sv"], "en": TEXTS["en"], "da": TEXTS["da"]}), ".texts: holds da: beside an original in 'sv' a provision carries en"),
            ("a translation not marked machine", entry(swedish, isMachine=...), ".isMachine: must be true when the entry holds a translation"),
            ("machine marked where nothing is translated", entry(union, isMachine=True), ".isMachine: must be true when the entry holds a translation"),
            ("Finland's Swedish passed off as a machine's", entry(finnish, officialLanguages=...), ".officialLanguages: must be ['sv']"),
            ("an official language a jurisdiction does not have", entry(swedish, officialLanguages=["en"]), ".officialLanguages: must be []"),
            ("a kind the seed does not file", entry(swedish, provisionKind="stycke"), ".provisionKind: 'stycke' is not a provision kind"),
            ("a number not in three digits", entry(swedish, path="5", key="se-act/5"), ".path: must be lowercase words and numbers joined by hyphens, every number in three digits"),
            ("a path that is not lowercase", entry(swedish, path="Kap-002", key="se-act/Kap-002"), ".path: must be lowercase words and numbers"),
            ("a key that is not its instrument and path", entry(swedish, key="se-act-005"), ".key: must be the instrument's key, a slash and the path"),
            ("a key used twice", entry(danish, **{**provision("se-act", "sv", "sv en", "obl-se-one", isMachine=True)}), ".key: 'se-act/005' is already used in provisions/test.json[se-act/005]"),
            ("no reference", entry(swedish, refLabel=""), ".refLabel: must be a non-empty string"),
            ("an empty heading", entry(swedish, heading=""), ".heading: must be a non-empty string"),
            ("a source that is not https", entry(swedish, source="http://www.riksdagen.se/"), ".source: must be an https link"),
            ("no source label", entry(swedish, sourceLabel=...), ".sourceLabel: must be a non-empty string"),
            ("no day read", entry(swedish, readOn=...), ".readOn: must be the day the text was read"),
            ("a day read that is not a date", entry(swedish, readOn="13 November 2026"), ".readOn: must be an ISO date YYYY-MM-DD"),
            ("a provision that is not an object", lambda data: data["provisions"].append("se-act/006"), "provisions/test.json[5]: must be an object"),
            ("an obligation with no text and no reason", whole(withoutProvision=[]), "provisions/test.json: obl-se-two is cited by no provision"),
            ("an excuse without a reason", whole(withoutProvision=[{"obligation": "obl-se-two", "reason": ""}]), ".withoutProvision[0].reason: must be a non-empty string"),
            ("an excuse for an obligation nobody holds", whole(withoutProvision=[{"obligation": "obl-se-two", "reason": "No one section."}, {"obligation": "obl-nobody", "reason": "None."}]), ".withoutProvision[1]: 'obl-nobody' is not an obligation of this tranche"),
            ("an excuse that is not obligation and reason", whole(withoutProvision=[{"obligation": "obl-se-two"}]), ".withoutProvision[0]: must be an object with obligation, a key, and reason"),
            ("excuses that are not a list", whole(withoutProvision="obl-se-two"), ".withoutProvision: must be a list of objects with obligation and reason"),
        ]
        for case, change, expected in cases:
            with self.subTest(case=case):
                data = copy.deepcopy(good())
                change(data)
                found = self.problems(data)
                self.assertTrue(any(expected in problem for problem in found), f"{expected!r} not among {found}")

    def test_a_file_that_cannot_be_read_as_provisions_is_refused_by_name(self) -> None:
        self.assertIn("provisions/test.json: cannot be read", self.problems("{not json")[0])
        self.assertEqual(self.problems(["se-act/005"]), ["provisions/test.json: must be an object with provisions, a list"])
        self.assertEqual(self.problems({"tranche": TRANCHE, "researchedOn": "2026-11-13"}), ["provisions/test.json: must be an object with provisions, a list"])

    def test_a_provisions_file_carries_its_tranches_name(self) -> None:
        self.problems(good())
        found = self.problems(good(), name="tset")
        self.assertEqual(found, ["provisions/tset.json: names no tranche: a provisions file carries its tranche's name (test)"])

    def test_a_tranche_with_a_file_leaves_no_obligation_silently_without_its_text(self) -> None:
        """The gap is visible: every duty of the tranche is cited, or excused with a reason."""
        data = good()
        data["provisions"] = data["provisions"][:1]
        data["withoutProvision"] = []
        self.assertEqual(
            self.problems(data),
            [
                f"provisions/test.json: {key} is cited by no provision: give the text it comes from, or name it in withoutProvision with the reason"
                for key in ("obl-dk", "obl-eu", "obl-fi", "obl-no", "obl-se-two")
            ],
        )
        everything_excused = {**good(), "provisions": [], "withoutProvision": [{"obligation": duty, "reason": "Its source is a PDF not read yet."} for _, duties in INSTRUMENTS.values() for duty in duties]}
        self.assertEqual(self.problems(everything_excused), [], "a tranche may say that none of its texts is here yet")


def correction(**fields: Any) -> dict[str, Any]:
    """A correction of `obl-dk-one` that every rule passes: a new title, citation and cited
    provisions, all of its own instrument."""
    return {
        "key": "obl-dk-one",
        "title": "Correct obl-dk-one: the duty rests on two sections",
        "source": "https://www.retsinformation.dk/eli/lta/2099/1",
        "sourceLabel": "Retsinformation, BEK nr 1 af 1/1/2099, §§ 1-2",
        "why": "§ 2 sets the deadline the summary names, and the old citation left it out.",
        "payload": {
            "summaries": {"en": "The firm keeps the record. It sends it to the supervisor within a month."},
            "originalLanguage": "en",
            "titles": {"en": "Keep the record and send it"},
            "refLabel": "§§ 1-2",
            "provisions": ["dk-act/001", "dk-act/002"],
        },
        **fields,
    }


class TheBaselinesCorrections(SimpleTestCase):
    """A tranche's corrections of its duties (D-144): each a version payload the door takes,
    naming a duty of its tranche once, saying why, and citing provisions of the duty's own
    instrument only."""

    def setUp(self) -> None:
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        duty = {"key": "obl-dk-one", "titles": {"en": "Keep the record"}, "refLabel": "§ 1"}
        instruments = [
            {"payload": {"key": "dk-act", "jurisdiction": "dk"}, "obligations": [{"payload": duty}, {"payload": {"key": "obl-dk-two"}}]},
            {"payload": {"key": "dk-other", "jurisdiction": "dk"}, "obligations": []},
        ]
        (self.folder / f"{TRANCHE}.json").write_text(json.dumps({"tranche": TRANCHE, "instruments": instruments}), encoding="utf-8")
        provisions = [
            {"key": "dk-act/001", "instrument": "dk-act", "obligations": ["obl-dk-one"]},
            {"key": "dk-act/002", "instrument": "dk-act", "obligations": ["obl-dk-two"]},
            {"key": "dk-other/001", "instrument": "dk-other", "obligations": []},
        ]
        (self.folder / check_baseline.PROVISIONS_DIR).mkdir()
        (self.folder / check_baseline.PROVISIONS_DIR / f"{TRANCHE}.json").write_text(json.dumps({"provisions": provisions}), encoding="utf-8")
        (self.folder / check_baseline.CORRECTIONS_DIR).mkdir()

    def problems(self, data: Any = None, *, name: str = TRANCHE) -> list[str]:
        if data is not None:
            text = data if isinstance(data, str) else json.dumps(data)
            (self.folder / check_baseline.CORRECTIONS_DIR / f"{name}.json").write_text(text, encoding="utf-8")
        checker = check_baseline.Checker()
        checker.corrections(self.folder)
        return checker.problems

    @staticmethod
    def good(*entries: dict[str, Any]) -> dict[str, Any]:
        return {"tranche": TRANCHE, "readOn": "2026-11-13", "reading": "docs/reviews/law-text-2026-11-13/duty-reading.json", "obligations": list(entries) or [correction()]}

    def test_a_good_file_passes_and_a_folder_with_none_passes(self) -> None:
        self.assertEqual(self.problems(), [], "no corrections file at all")
        self.assertEqual(self.problems(self.good()), [])

    def test_each_rule_refuses_the_correction_that_breaks_it(self) -> None:
        def payload(**fields: Any) -> dict[str, Any]:
            body = {**correction()["payload"], **fields}
            return correction(payload={name: value for name, value in body.items() if value is not ...})

        cases: list[tuple[str, dict[str, Any], str]] = [
            ("a duty of no tranche here", correction(key="obl-nobody"), ".key: 'obl-nobody' is not an obligation of this tranche"),
            ("a field a correction does not know", correction(note="later"), ": unknown field 'note'"),
            ("no why", correction(why=" "), ".why: must be a non-empty string"),
            ("title and why longer than a proposal's title", correction(why="x" * 450), "title and why together are the proposal's title, at most 500 characters"),
            ("a source that is not https", correction(source="http://www.retsinformation.dk/"), ".source: must be an https link"),
            ("a payload that is not an object", correction(payload=["x"]), ".payload: must be an object"),
            ("a date the correction never sets", payload(effectiveFrom="2026-01-01"), ".payload: unknown field 'effectiveFrom'"),
            ("a scope the correction never sets", payload(terms=[]), ".payload: unknown field 'terms'"),
            ("a machine mark", payload(isMachine=True), ".payload: unknown field 'isMachine'"),
            ("a summary without its original", payload(summaries={"da": "Virksomheden fører registret."}), ".payload.summaries: has no text in its original language 'en'"),
            ("a summary of four sentences", payload(summaries={"en": "One. Two. Three. Four."}), ".payload.summaries.en: is 4 sentences"),
            ("a title without its original", payload(titles={"da": "Før registret"}), ".payload.titles: has no text in its original language 'en'"),
            ("the title the duty has", payload(titles={"en": "Keep the record"}), ".payload.titles: is the title the duty already has"),
            ("the citation the duty has", payload(refLabel="§ 1"), ".payload.refLabel: is the citation the duty already has"),
            ("a blank citation", payload(refLabel=""), ".payload.refLabel: must be a non-empty string"),
            ("a provision of another instrument", payload(provisions=["dk-act/001", "dk-other/001"]), "'dk-other/001' is not a provision of 'dk-act' in the provisions files"),
            ("a provision nobody extracted", payload(provisions=["dk-act/099"]), "'dk-act/099' is not a provision of 'dk-act'"),
            ("a provision named twice", payload(provisions=["dk-act/001", "dk-act/001"]), ".payload.provisions: names a provision twice"),
            ("a source for a field it does not set", correction(fieldSources={"terms": "https://www.retsinformation.dk/"}), ".fieldSources.terms: names no field this correction sets"),
        ]
        for case, entry, expected in cases:
            with self.subTest(case=case):
                found = self.problems(self.good(entry))
                self.assertTrue(any(expected in problem for problem in found), f"{expected!r} not among {found}")

    def test_the_file_its_name_and_one_correction_per_duty(self) -> None:
        self.assertIn("corrections/test.json: cannot be read", self.problems("{not json")[0])
        self.assertEqual(self.problems({"tranche": TRANCHE, "obligations": []}), ["corrections/test.json: must be an object with obligations, a non-empty list"])
        twice = self.problems(self.good(correction(), correction()))
        self.assertTrue(any("'obl-dk-one' is already corrected in corrections/test.json[obl-dk-one]" in problem for problem in twice), twice)
        no_day = self.problems({**self.good(), "readOn": None, "reading": ""})
        self.assertTrue(any(".readOn: must be the day" in problem for problem in no_day) and any(".reading: must be a non-empty string" in problem for problem in no_day), no_day)
        (self.folder / check_baseline.CORRECTIONS_DIR / f"{TRANCHE}.json").unlink()
        self.assertEqual(self.problems(self.good(), name="tset"), ["corrections/tset.json: names no tranche: a corrections file carries its tranche's name (test)"])


class TheRealBaseline(SimpleTestCase):
    def test_the_whole_baseline_passes_its_checker(self) -> None:
        """The quick check is a gate: a provisions file that breaks a rule fails the suite."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = check_baseline.main([])
        self.assertEqual(status, 0, out.getvalue())
        self.assertIn("baseline: ok", out.getvalue())

    def test_the_checkers_own_tables_are_the_seeds_and_the_settings(self) -> None:
        legal = {key: language for key, (_kind, _parent, language, _labels) in JURISDICTIONS.items() if key in check_baseline.JURISDICTIONS}
        self.assertEqual(check_baseline.LEGAL_LANGUAGE, legal)
        self.assertEqual(check_baseline.PROVISION_KINDS, {row.key for row in LIBRARY_SYSTEM_ROWS["provision_kind"][1]})
        self.assertEqual(set(check_baseline.TRANSLATIONS), set(legal.values()), "every legal language says which translations stand beside it")
        self.assertLessEqual(set(check_baseline.OFFICIAL), set(check_baseline.TRANSLATIONS))
        from apps.library.logic import OFFICIAL_BESIDE

        self.assertEqual(check_baseline.OFFICIAL, {original: set(beside) for original, beside in OFFICIAL_BESIDE.items()}, "the checker and the library name the same official languages")
        self.assertEqual(check_baseline.MAX_TEXT, settings.PROPOSAL_TEXT_MAX_CHARS)
        self.assertEqual(check_baseline.MAX_OBLIGATIONS, settings.PROPOSAL_PROVISION_MAX_OBLIGATIONS)
        self.assertEqual(check_baseline.MAX_PROVISIONS, settings.PROPOSAL_OBLIGATION_MAX_PROVISIONS)
        from apps.proposals.models import Proposal
        from apps.proposals.schemas import ProposalObligationVersionPayload

        self.assertEqual(check_baseline.MAX_PROPOSAL_TITLE, Proposal._meta.get_field("title").max_length)
        door = {field.alias or name for name, field in ProposalObligationVersionPayload.model_fields.items()}
        self.assertLessEqual(check_baseline.CORRECTION_PAYLOAD_FIELDS, door, "a correction sets only what the door's version payload names")

    def test_every_correction_of_the_real_baseline_is_a_version_the_door_parses(self) -> None:
        from apps.proposals import logic

        for path in sorted((check_baseline.HERE / check_baseline.CORRECTIONS_DIR).glob("*.json")):
            for item in json.loads(path.read_text(encoding="utf-8"))["obligations"]:
                with self.subTest(correction=item["key"]):
                    logic.parsed_payload("new_obligation_version", item["payload"])
        # The filer's retry key, `baseline:<key>:<32 hex>`, fits the proposal's own column.
        from apps.proposals.logic import IDEMPOTENCY_KEY_MAX_CHARS

        self.assertEqual(len("baseline:") + check_baseline.MAX_PROVISION_KEY + 1 + 32, IDEMPOTENCY_KEY_MAX_CHARS)
