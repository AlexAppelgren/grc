#!/usr/bin/env python
"""Shape and reference check for the library baseline (backend/apps/library/baseline/*.json).

Every entry is a proposal `manage.py file_library_baseline` files, so this checks, without a
database, what the proposal door will ask of it: fields and limits, vocabulary and taxonomy
keys, a source on every entry, languages, dates and precisions, and stable keys unique across
the baseline and the sample library. The authority is apps/proposals/tests_baseline.py; this
is the quick answer while writing one file.

A tranche's provisions, the law's own words (`provisions/<tranche>.json`), are checked with
the whole baseline, never with a single file: the original is the language its jurisdiction
writes law in, the translations the README names are there and marked, every obligation a
provision names sits under its instrument, and every obligation of a tranche that has a
provisions file is cited by one or excused by name with a reason.

Exit 0 when clean, 1 with every problem listed. No Django, no database: plain Python.

    python backend/apps/library/baseline/check_baseline.py [file.json ...]
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixtures" / "prototype_data.json"

# The pages the watch checks for the baseline, beside the tranches: checked by `sources()`.
SOURCES_FILE = "sources.json"
KEY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LANGUAGES = {"en", "sv", "da", "nb", "fi"}
JURISDICTIONS = {"eu", "se", "dk", "no", "fi"}
EU_LEVELS = {"eu_regulation", "eu_directive", "eu_guidance"}
NATIONAL_LEVELS = {"act", "government_regulation", "authority_regulation"}
PRECISIONS = {"day", "month", "quarter", "year"}
# Terms the taxonomy seed authors beside the fixture's (apps/taxonomy/seeds `_EXTRA_TERMS`).
EXTRA_TERMS = {"licensed_activity:card_issuing", "licensed_activity:card_acquiring"}
# A mirrored jurisdiction term never goes on an obligation (FP-S12), and a standard's term
# only on a standard's own records, which the baseline holds none of (D-47).
REFUSED_DIMENSIONS = {"jurisdiction", "standard"}

INSTRUMENT_FIELDS = {
    "key", "titles", "originalLanguage", "isMachine", "shortName", "officialRef", "eliUri", "level", "binding",
    "jurisdiction", "authority", "regime", "inForceFrom", "inForceFromPrecision", "inForceTo", "inForceToPrecision",
    "implementsNote",
}
OBLIGATION_FIELDS = {
    "key", "instrument", "titles", "summaries", "originalLanguage", "isMachine", "refLabel", "dutyType",
    "effectiveFrom", "effectiveFromPrecision", "terms",
}
ENTRY_FIELDS = {"title", "source", "sourceLabel", "fieldSources", "payload"}
MAX_TITLE = 500
MAX_SOURCE_LABEL = 500
MAX_SHORT_NAME = 120
MAX_OFFICIAL_REF = 200
MAX_REF_LABEL = 200
MAX_SUMMARY = 50000
MAX_TERMS = 20

# The law's own words (INV-02): each tranche's provisions, in a file of its name in this folder.
PROVISIONS_DIR = "provisions"
PROVISIONS_FILE_FIELDS = {"tranche", "researchedOn", "provisions", "withoutProvision"}
PROVISION_FIELDS = {
    "key", "instrument", "provisionKind", "refLabel", "path", "heading", "texts", "originalLanguage", "isMachine",
    "officialLanguages", "obligations", "source", "sourceLabel", "readOn",
}
WITHOUT_PROVISION_FIELDS = {"obligation", "reason"}
# The provision kinds the reference seed files, none of them one jurisdiction's own
# (apps/taxonomy/seeds `_PROVISION_KINDS`).
PROVISION_KINDS = {"part", "chapter", "section", "article", "paragraph", "guideline", "annex"}
# The language each jurisdiction writes its law in (apps/library/seeds `JURISDICTIONS`): the
# original of every provision under it, as the proposal door holds it.
LEGAL_LANGUAGE = {"eu": "en", "se": "sv", "dk": "da", "no": "nb", "fi": "fi"}
# The texts a provision carries beside its original, by that original: English always, and
# Swedish beside Danish, Norwegian and Finnish.
TRANSLATIONS: dict[str, set[str]] = {"en": set(), "sv": {"en"}, "da": {"en", "sv"}, "nb": {"en", "sv"}, "fi": {"en", "sv"}}
# Of those, the ones the authority itself publishes: Finland enacts its law in Swedish too.
# The library's `apps.library.logic.OFFICIAL_BESIDE` holds the same; a test ties the two.
OFFICIAL: dict[str, set[str]] = {"fi": {"sv"}}
MAX_TEXT = 50000  # PROPOSAL_TEXT_MAX_CHARS
MAX_OBLIGATIONS = 50  # PROPOSAL_PROVISION_MAX_OBLIGATIONS
# The door takes a key of 200; the filer's retry key, `baseline:<key>:<32 hex>`, has 200 in all.
MAX_PROVISION_KEY = 158
# A provision's place in its instrument, the last part of its key.
PATH = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NUMBER = re.compile(r"\d+")


def load_reference() -> dict[str, set[str]]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    vocab = data["vocabularies"]
    terms = {f"{t['dimension']}:{t['key']}" for t in data["taxonomy_terms"]} | EXTRA_TERMS
    return {
        "levels": {key for key, row in vocab["instrument_level"].items() if row.get("kind") != "standard"},
        "duty_types": set(vocab["duty_type"]),
        "authorities": {a["key"] for a in data["authorities"]},
        "authority_jurisdiction": {f"{a['key']}:{a['jurisdiction'].lower()}" for a in data["authorities"]},
        "regimes": {t for t in terms if t.startswith("regime:")},
        "terms": {t for t in terms if not t.startswith("regime:")},
        "sample_obligations": {o["stable_key"] for o in data["obligations"]},
    }


# The fields a proposal never needs a source for (apps/proposals/logic.py UNSOURCED_FIELDS).
UNSOURCED = {"key", "originalLanguage", "isMachine", "effectiveFromPrecision", "inForceFromPrecision", "inForceToPrecision"}
DEFAULTS: dict[str, object] = {"eliUri": "", "binding": None, "implementsNote": "", "inForceTo": None, "inForceFrom": None, "effectiveFrom": None, "terms": None}


def sourced_fields(payload: dict, *, obligation: bool) -> set[str]:
    """The names `fieldSources` may use, as the door names them: every field the payload
    sets, a text field once per language (`titles.en`). An obligation's `instrument` is set
    by the filing and sourced like the rest."""
    names = {"instrument"} if obligation else set()
    for name, value in payload.items():
        if name in UNSOURCED or (name in DEFAULTS and value == DEFAULTS[name]):
            continue
        names |= {f"{name}.{language}" for language in value} if isinstance(value, dict) else {name}
    return names


class Checker:
    def __init__(self) -> None:
        self.ref = load_reference()
        self.problems: list[str] = []
        self.instrument_keys: dict[str, str] = {}
        self.obligation_keys: dict[str, str] = {}
        self.provision_keys: dict[str, str] = {}
        self.counts: dict[str, tuple[int, int]] = {}

    def fail(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}")

    def text(self, where: str, value: object, limit: int | None = None) -> bool:
        if not isinstance(value, str) or not value.strip():
            self.fail(where, "must be a non-empty string")
            return False
        if value != value.strip():
            self.fail(where, "has leading or trailing whitespace")
        if limit is not None and len(value) > limit:
            self.fail(where, f"is {len(value)} characters, at most {limit}")
        return True

    def link(self, where: str, value: object) -> None:
        if self.text(where, value, 2000) and not str(value).startswith("https://"):
            self.fail(where, "must be an https link")

    def day(self, where: str, value: object) -> date | None:
        if value is None:
            return None
        if not isinstance(value, str) or not DATE.match(value):
            self.fail(where, "must be an ISO date YYYY-MM-DD")
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            self.fail(where, "is not a real date")
            return None

    def languages(self, where: str, texts: object, original: object, limit: int | None = None) -> None:
        if not isinstance(texts, dict) or not texts:
            self.fail(where, "must be an object of language -> text")
            return
        for language, value in texts.items():
            if language not in LANGUAGES:
                self.fail(f"{where}.{language}", f"is not a content language ({', '.join(sorted(LANGUAGES))})")
            self.text(f"{where}.{language}", value, limit)
        if original not in texts:
            self.fail(where, f"has no text in its original language {original!r}")

    def entry(self, where: str, entry: object, fields: set[str]) -> dict | None:
        if not isinstance(entry, dict):
            self.fail(where, "must be an object")
            return None
        for stray in sorted(set(entry) - ENTRY_FIELDS - {"obligations"}):
            self.fail(where, f"unknown field {stray!r}")
        self.text(f"{where}.title", entry.get("title"), MAX_TITLE)
        self.link(f"{where}.source", entry.get("source"))
        self.text(f"{where}.sourceLabel", entry.get("sourceLabel"), MAX_SOURCE_LABEL)
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            self.fail(f"{where}.payload", "must be an object")
            return None
        for stray in sorted(set(payload) - fields):
            self.fail(f"{where}.payload", f"unknown field {stray!r}")
        sources = entry.get("fieldSources", {})
        if not isinstance(sources, dict):
            self.fail(f"{where}.fieldSources", "must be an object of field -> https link")
            return payload
        sourced = sourced_fields(payload, obligation=fields is OBLIGATION_FIELDS)
        for name, value in sources.items():
            self.link(f"{where}.fieldSources.{name}", value)
            if name not in sourced:
                self.fail(f"{where}.fieldSources.{name}", f"names no field this entry sets: {', '.join(sorted(sourced))}")
        return payload

    def instrument(self, where: str, entry: object) -> tuple[str | None, str | None, date | None]:
        payload = self.entry(where, entry, INSTRUMENT_FIELDS)
        if payload is None:
            return None, None, None
        key = payload.get("key")
        if not isinstance(key, str) or not KEY.match(key) or len(key) > 120:
            self.fail(f"{where}.key", "must be lowercase words joined by hyphens, at most 120 characters")
            key = None
        elif key in self.instrument_keys:
            self.fail(f"{where}.key", f"{key!r} is already used in {self.instrument_keys[key]}")
        else:
            self.instrument_keys[key] = where
        self.languages(f"{where}.titles", payload.get("titles"), payload.get("originalLanguage"))
        self.text(f"{where}.shortName", payload.get("shortName"), MAX_SHORT_NAME)
        self.text(f"{where}.officialRef", payload.get("officialRef"), MAX_OFFICIAL_REF)
        if payload.get("eliUri"):
            self.link(f"{where}.eliUri", payload["eliUri"])
        level, jurisdiction, authority = payload.get("level"), payload.get("jurisdiction"), payload.get("authority")
        if level not in self.ref["levels"]:
            self.fail(f"{where}.level", f"{level!r} is not a level ({', '.join(sorted(self.ref['levels']))})")
        if jurisdiction not in JURISDICTIONS:
            self.fail(f"{where}.jurisdiction", f"{jurisdiction!r} is not one of {', '.join(sorted(JURISDICTIONS))}")
        elif level in EU_LEVELS and jurisdiction != "eu" or level in NATIONAL_LEVELS and jurisdiction == "eu":
            self.fail(where, f"level {level!r} does not fit jurisdiction {jurisdiction!r}")
        if authority is not None:
            if authority not in self.ref["authorities"]:
                self.fail(f"{where}.authority", f"{authority!r} is not a seeded authority ({', '.join(sorted(self.ref['authorities']))})")
            elif f"{authority}:{jurisdiction}" not in self.ref["authority_jurisdiction"]:
                self.fail(f"{where}.authority", f"{authority!r} is not an authority of {jurisdiction!r}")
        if payload.get("regime") not in self.ref["regimes"]:
            self.fail(f"{where}.regime", f"{payload.get('regime')!r} is not a regime ({', '.join(sorted(self.ref['regimes']))})")
        start = self.day(f"{where}.inForceFrom", payload.get("inForceFrom"))
        end = self.day(f"{where}.inForceTo", payload.get("inForceTo"))
        if start and end and end <= start:
            self.fail(f"{where}.inForceTo", "must be after inForceFrom")
        for field in ("inForceFromPrecision", "inForceToPrecision"):
            if field in payload and payload[field] not in PRECISIONS:
                self.fail(f"{where}.{field}", f"must be one of {', '.join(sorted(PRECISIONS))}")
        if "binding" in payload and not isinstance(payload["binding"], bool):
            self.fail(f"{where}.binding", "must be true or false, or left out for the level's default")
        return key, jurisdiction, start

    def obligation(self, where: str, entry: object, instrument: str | None, start: date | None) -> None:
        payload = self.entry(where, entry, OBLIGATION_FIELDS)
        if payload is None:
            return
        key = payload.get("key")
        if not isinstance(key, str) or not KEY.match(key) or len(key) > 120 or not key.startswith("obl-"):
            self.fail(f"{where}.key", "must start obl- and be lowercase words joined by hyphens, at most 120 characters")
        elif key in self.ref["sample_obligations"]:
            self.fail(f"{where}.key", f"{key!r} is a sample library obligation's key: choose another")
        elif key in self.obligation_keys:
            self.fail(f"{where}.key", f"{key!r} is already used in {self.obligation_keys[key]}")
        else:
            self.obligation_keys[key] = where
        if "instrument" in payload and payload["instrument"] != instrument:
            self.fail(f"{where}.instrument", "must be left out or name the instrument it sits under")
        original = payload.get("originalLanguage")
        self.languages(f"{where}.titles", payload.get("titles"), original, MAX_TITLE)
        self.languages(f"{where}.summaries", payload.get("summaries"), original, MAX_SUMMARY)
        self.text(f"{where}.refLabel", payload.get("refLabel"), MAX_REF_LABEL)
        if payload.get("dutyType") not in self.ref["duty_types"]:
            self.fail(f"{where}.dutyType", f"{payload.get('dutyType')!r} is not a duty type ({', '.join(sorted(self.ref['duty_types']))})")
        effective = self.day(f"{where}.effectiveFrom", payload.get("effectiveFrom"))
        if effective and start and effective < start:
            self.fail(f"{where}.effectiveFrom", "is before the instrument is in force")
        if "effectiveFromPrecision" in payload and payload["effectiveFromPrecision"] not in PRECISIONS:
            self.fail(f"{where}.effectiveFromPrecision", f"must be one of {', '.join(sorted(PRECISIONS))}")
        terms = payload.get("terms", [])
        if not isinstance(terms, list) or len(terms) > MAX_TERMS:
            self.fail(f"{where}.terms", f"must be a list of at most {MAX_TERMS} dimension:key terms")
            return
        if len(set(terms)) != len(terms):
            self.fail(f"{where}.terms", "names a term twice")
        for term in terms:
            if not isinstance(term, str) or term.split(":")[0] in REFUSED_DIMENSIONS or term.startswith("regime:"):
                self.fail(f"{where}.terms", f"{term!r} may not go on an obligation (no jurisdiction, standard or regime term)")
            elif term not in self.ref["terms"]:
                self.fail(f"{where}.terms", f"{term!r} is not a seeded term")

    def file(self, path: Path) -> None:
        name = path.name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            self.fail(name, f"cannot be read: {error}")
            return
        if data.get("tranche") != path.stem:
            self.fail(name, f"tranche must be the file's name, {path.stem!r}")
        self.day(f"{name}.researchedOn", data.get("researchedOn"))
        instruments = data.get("instruments")
        if not isinstance(instruments, list) or not instruments:
            self.fail(name, "instruments must be a non-empty list")
            return
        obligations = 0
        for i, entry in enumerate(instruments):
            key, _, start = self.instrument(f"{name}[{i}]", entry)
            label = key or str(i)
            for j, duty in enumerate(entry.get("obligations", []) if isinstance(entry, dict) else []):
                self.obligation(f"{name}[{label}].obligations[{j}]", duty, key, start)
                obligations += 1
        self.counts[path.stem] = (len(instruments), obligations)

    def provisions(self, folder: Path) -> None:
        """Every provisions file of `folder`, each against the tranche it is named after. A
        tranche with no file is not checked, and a folder with none passes."""
        tranches = {path.stem: path for path in folder.glob("*.json") if path.name != SOURCES_FILE}
        for path in sorted((folder / PROVISIONS_DIR).glob("*.json")):
            where = f"{PROVISIONS_DIR}/{path.name}"
            if path.stem not in tranches:
                self.fail(where, f"names no tranche: a provisions file carries its tranche's name ({', '.join(sorted(tranches))})")
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                self.fail(where, f"cannot be read: {error}")
                continue
            if not isinstance(data, dict) or not isinstance(data.get("provisions"), list):
                self.fail(where, "must be an object with provisions, a list")
                continue
            for stray in sorted(set(data) - PROVISIONS_FILE_FIELDS):
                self.fail(where, f"unknown field {stray!r}")
            if data.get("tranche") != path.stem:
                self.fail(where, f"tranche must be the file's name, {path.stem!r}")
            self.day(f"{where}.researchedOn", data.get("researchedOn"))
            # What the tranche holds: each instrument's jurisdiction, and each obligation's instrument.
            jurisdiction: dict[str, str] = {}
            under: dict[str, str] = {}
            for entry in json.loads(tranches[path.stem].read_text(encoding="utf-8"))["instruments"]:
                jurisdiction[entry["payload"]["key"]] = entry["payload"]["jurisdiction"]
                under.update({duty["payload"]["key"]: entry["payload"]["key"] for duty in entry.get("obligations", [])})
            cited: set[str] = set()
            for i, item in enumerate(data["provisions"]):
                label = item.get("key", i) if isinstance(item, dict) else i
                cited |= self.provision(f"{where}[{label}]", item, jurisdiction, under)
            excused = self.without_provision(where, data.get("withoutProvision", []), under)
            for key in sorted(set(under) - cited - excused):
                self.fail(where, f"{key} is cited by no provision: give the text it comes from, or name it in withoutProvision with the reason")

    def provision(self, where: str, item: object, jurisdiction: dict[str, str], under: dict[str, str]) -> set[str]:
        """One provision as the filer hands it to the door, and what only the baseline asks
        of it: where it was read, and which translations stand beside the original. Returns
        the obligations it cites."""
        if not isinstance(item, dict):
            self.fail(where, "must be an object")
            return set()
        for stray in sorted(set(item) - PROVISION_FIELDS):
            self.fail(where, f"unknown field {stray!r}")
        # A name that is not text names nothing, and is refused as an unknown one is.
        instrument, key, path, original = (str(item.get(name) or "") for name in ("instrument", "key", "path", "originalLanguage"))
        if instrument not in jurisdiction:
            self.fail(f"{where}.instrument", f"{instrument!r} is not an instrument of this tranche")
        if not PATH.match(path) or any(len(number) != 3 for number in NUMBER.findall(path)):
            self.fail(f"{where}.path", "must be lowercase words and numbers joined by hyphens, every number in three digits (009-006), so an instrument's provisions sort as it reads")
        if key != f"{instrument}/{path}" or len(key) > MAX_PROVISION_KEY:
            self.fail(f"{where}.key", f"must be the instrument's key, a slash and the path, at most {MAX_PROVISION_KEY} characters")
        elif key in self.provision_keys:
            self.fail(f"{where}.key", f"{key!r} is already used in {self.provision_keys[key]}")
        else:
            self.provision_keys[key] = where
        if item.get("provisionKind") not in PROVISION_KINDS:
            self.fail(f"{where}.provisionKind", f"{item.get('provisionKind')!r} is not a provision kind ({', '.join(sorted(PROVISION_KINDS))})")
        self.text(f"{where}.refLabel", item.get("refLabel"), MAX_REF_LABEL)
        if item.get("heading") is not None:
            self.text(f"{where}.heading", item["heading"], MAX_TITLE)
        legal = LEGAL_LANGUAGE.get(jurisdiction.get(instrument, ""))
        if legal is not None and original != legal:
            self.fail(f"{where}.originalLanguage", f"must be {legal!r}, the language {instrument} is written in: the original is the authority's own text, never a translation")
        texts = item.get("texts")
        self.languages(f"{where}.texts", texts, original, MAX_TEXT)
        held = set(texts) if isinstance(texts, dict) else set()
        beside = TRANSLATIONS.get(original, set())
        if beside - held:
            self.fail(f"{where}.texts", f"lacks {', '.join(sorted(beside - held))}: beside an original in {original!r} a provision carries {', '.join(sorted(beside))}")
        if held - beside - {original}:
            self.fail(f"{where}.texts", f"holds {', '.join(sorted(held - beside - {original}))}: beside an original in {original!r} a provision carries {', '.join(sorted(beside)) or 'nothing'}")
        official = OFFICIAL.get(original, set())
        if item.get("officialLanguages", []) != sorted(official):
            self.fail(f"{where}.officialLanguages", f"must be {sorted(official)}, the languages its authority itself publishes beside {original!r}, and left out when there are none")
        if item.get("isMachine", False) is not bool(held - {original} - official):
            self.fail(f"{where}.isMachine", "must be true when the entry holds a translation, which is a machine translation and is marked so, and left out when it holds none")
        obligations = item.get("obligations")
        if not isinstance(obligations, list) or not obligations or len(obligations) > MAX_OBLIGATIONS or not all(isinstance(duty, str) for duty in obligations):
            self.fail(f"{where}.obligations", f"must list the keys of the obligations that cite the provision, at least one and at most {MAX_OBLIGATIONS}")
            obligations = []
        if len(set(obligations)) != len(obligations):
            self.fail(f"{where}.obligations", "names an obligation twice")
        for duty in obligations:
            if under.get(duty) != instrument:
                self.fail(f"{where}.obligations", f"{duty!r} is not an obligation under {instrument!r} in this tranche")
        self.link(f"{where}.source", item.get("source"))
        self.text(f"{where}.sourceLabel", item.get("sourceLabel"), MAX_SOURCE_LABEL)
        if item.get("readOn") is None:
            self.fail(f"{where}.readOn", "must be the day the text was read, as an ISO date YYYY-MM-DD")
        self.day(f"{where}.readOn", item.get("readOn"))
        return set(obligations)

    def without_provision(self, where: str, items: object, under: dict[str, str]) -> set[str]:
        """The obligations a tranche says no provision is given for, each with its reason."""
        excused: set[str] = set()
        if not isinstance(items, list):
            self.fail(f"{where}.withoutProvision", "must be a list of objects with obligation and reason")
            return excused
        for i, item in enumerate(items):
            spot = f"{where}.withoutProvision[{i}]"
            if not isinstance(item, dict) or set(item) != WITHOUT_PROVISION_FIELDS or not isinstance(item["obligation"], str):
                self.fail(spot, "must be an object with obligation, a key, and reason")
            elif item["obligation"] not in under:
                self.fail(spot, f"{item['obligation']!r} is not an obligation of this tranche")
            elif self.text(f"{spot}.reason", item["reason"], MAX_TITLE):
                excused.add(item["obligation"])
        return excused


def sources(ref: dict[str, set[str]]) -> list[str]:
    """The source list: unique names, https pages, a seeded source kind and authority."""
    path = HERE / SOURCES_FILE
    if not path.exists():
        return []
    problems, names = [], set()
    kinds = set(json.loads(FIXTURE.read_text(encoding="utf-8"))["vocabularies"]["source_kind"])
    for i, spec in enumerate(json.loads(path.read_text(encoding="utf-8"))["sources"]):
        where = f"{SOURCES_FILE}[{i}]"
        if spec.get("name") in names or not spec.get("name"):
            problems.append(f"{where}: a name is given once and never empty")
        names.add(spec.get("name"))
        if not str(spec.get("url", "")).startswith("https://"):
            problems.append(f"{where}: url must be an https link")
        if spec.get("kind") not in kinds:
            problems.append(f"{where}: {spec.get('kind')!r} is not a source kind ({', '.join(sorted(kinds))})")
        if spec.get("authority") is not None and spec["authority"] not in ref["authorities"]:
            problems.append(f"{where}: {spec['authority']!r} is not a seeded authority")
    return problems


# Each tranche's instrument summaries (INV-09, D-124), in a file of the same name here.
SUMMARIES_DIR = "summaries"
SUMMARY_MIN, SUMMARY_MAX = 250, 600
# What the summaries never say: a dash for a pause, advice to the reader, or a purpose claim.
SUMMARY_REFUSED = re.compile(r"[\u2013\u2014]|\bshould\b|\baims to\b", re.IGNORECASE)


def summaries() -> list[str]:
    """Every tranche has a summary file with one English summary per instrument, its own
    https source, and plain text of the agreed length and style."""
    problems = []
    for path in sorted(path for path in HERE.glob("*.json") if path.name != SOURCES_FILE):
        keys = [entry["payload"]["key"] for entry in json.loads(path.read_text(encoding="utf-8"))["instruments"]]
        where = f"{SUMMARIES_DIR}/{path.name}"
        side = HERE / SUMMARIES_DIR / path.name
        if not side.exists():
            problems.append(f"{where}: missing; every instrument has a summary")
            continue
        data = json.loads(side.read_text(encoding="utf-8"))
        if data.get("tranche") != path.stem:
            problems.append(f"{where}: tranche must be {path.stem!r}")
        written = [item.get("key") for item in data.get("summaries", [])]
        if sorted(written) != sorted(keys):
            problems.append(f"{where}: one summary per instrument; missing {sorted(set(keys) - set(written))}, extra {sorted(set(written) - set(keys))}")
        for item in data.get("summaries", []):
            text = item.get("text", {})
            label = f"{where}[{item.get('key')}]"
            if list(text) != ["en"]:
                problems.append(f"{label}: text is written in English only, as {{\"en\": ...}}")
            english = str(text.get("en", ""))
            if not SUMMARY_MIN <= len(english) <= SUMMARY_MAX:
                problems.append(f"{label}: {len(english)} characters; a summary is {SUMMARY_MIN} to {SUMMARY_MAX}")
            if SUMMARY_REFUSED.search(english):
                problems.append(f"{label}: no dashes, no 'should', no 'aims to'")
            if not str(item.get("source", "")).startswith("https://") or not item.get("sourceLabel"):
                problems.append(f"{label}: an https source and its label")
    return problems


def main(argv: list[str]) -> int:
    files = [Path(arg) for arg in argv] or sorted(path for path in HERE.glob("*.json") if path.name != SOURCES_FILE)
    checker = Checker()
    if argv:
        # A single file is still checked against the rest, so a key is unique baseline-wide.
        for other in sorted(path for path in HERE.glob("*.json") if path.name != SOURCES_FILE):
            if other.resolve() not in {f.resolve() for f in files}:
                Checker.file(checker, other)
        checker.problems = [p for p in checker.problems if any(p.startswith(f.name) for f in files)]
    for path in files:
        checker.file(path)
    if not argv:
        checker.problems += sources(checker.ref)
        checker.problems += summaries()
        checker.provisions(HERE)
    for tranche, (instruments, obligations) in sorted(checker.counts.items()):
        print(f"{tranche}: {instruments} instruments, {obligations} obligations")
    if checker.problems:
        print(f"\n{len(checker.problems)} problems:")
        for problem in checker.problems:
            print(f"  {problem}")
        return 1
    total = [sum(n) for n in zip(*checker.counts.values(), strict=True)] if checker.counts else [0, 0]
    print(f"baseline: ok ({total[0]} instruments, {total[1]} obligations, {len(checker.provision_keys)} provisions)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
