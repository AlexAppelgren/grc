"""The prototype fixture as the one source of seeded keys, labels and usage notes
(backend/apps/library/fixtures/prototype_data.json, `vocabularies`, `taxonomy_terms`,
`tags`), so chunk 3 loads the fixture's records against the same keys the seeds wrote
and nothing needs a mapping. The fixture names pill tones its own way; `TONES` maps
them to the six the design names (design/system/pills-and-labels.md)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).resolve().parents[2] / "library" / "fixtures" / "prototype_data.json"

# fixture tone -> the pill tone the row's kind carries
TONES: dict[str, str] = {
    "critical": "negative",
    "warning": "warning",
    "info": "notice",
    "neutral": "information",
    "positive": "positive",
}


@cache
def load() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def vocabulary(name: str) -> dict[str, dict[str, Any]]:
    """The fixture's rows of one list: key -> {label_en, label_sv, kind, usage_note, ...}."""
    rows: dict[str, dict[str, Any]] = load()["vocabularies"][name]
    return rows


def labels_of(row: dict[str, Any]) -> dict[str, str]:
    return {language: row[f"label_{language}"] for language in ("en", "sv") if row.get(f"label_{language}")}


def taxonomy_terms() -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = load()["taxonomy_terms"]
    return terms


def tags() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = load()["tags"]
    return rows
