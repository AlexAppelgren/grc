#!/usr/bin/env python
"""Shape and reference check for the library baseline (backend/apps/library/baseline/*.json).

Every entry is a proposal the filing command files (`manage.py file_library_baseline`), so
this checks what the proposal door will ask of it, before any database is involved: the
payload's fields and their limits, every key in the seeded vocabularies and taxonomy, a
source on every entry, languages, dates and precisions, and stable keys unique across the
whole baseline and apart from the sample library's obligations. The authority is the
backend test that files and approves every entry through the real proposal code
(apps/proposals/tests_baseline.py); this script is the quick answer a researcher runs on one
file while writing it.

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

KEY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LANGUAGES = {"en", "sv", "da", "nb", "fi"}
JURISDICTIONS = {"eu", "se", "dk", "no", "fi"}
EU_LEVELS = {"eu_regulation", "eu_directive", "eu_guidance"}
NATIONAL_LEVELS = {"act", "authority_regulation"}
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


class Checker:
    def __init__(self) -> None:
        self.ref = load_reference()
        self.problems: list[str] = []
        self.instrument_keys: dict[str, str] = {}
        self.obligation_keys: dict[str, str] = {}
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
        sources = entry.get("fieldSources", {})
        if not isinstance(sources, dict):
            self.fail(f"{where}.fieldSources", "must be an object of field -> https link")
        else:
            for field, value in sources.items():
                self.link(f"{where}.fieldSources.{field}", value)
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            self.fail(f"{where}.payload", "must be an object")
            return None
        for stray in sorted(set(payload) - fields):
            self.fail(f"{where}.payload", f"unknown field {stray!r}")
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


def main(argv: list[str]) -> int:
    files = [Path(arg) for arg in argv] or sorted(HERE.glob("*.json"))
    checker = Checker()
    if argv:
        # A single file is still checked against the rest, so a key is unique baseline-wide.
        for other in sorted(HERE.glob("*.json")):
            if other.resolve() not in {f.resolve() for f in files}:
                Checker.file(checker, other)
        checker.problems = [p for p in checker.problems if any(p.startswith(f.name) for f in files)]
    for path in files:
        checker.file(path)
    for tranche, (instruments, obligations) in sorted(checker.counts.items()):
        print(f"{tranche}: {instruments} instruments, {obligations} obligations")
    if checker.problems:
        print(f"\n{len(checker.problems)} problems:")
        for problem in checker.problems:
            print(f"  {problem}")
        return 1
    total = [sum(n) for n in zip(*checker.counts.values(), strict=True)] if checker.counts else [0, 0]
    print(f"baseline: ok ({total[0]} instruments, {total[1]} obligations)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
