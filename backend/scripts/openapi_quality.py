#!/usr/bin/env python
"""OpenAPI quality (CONVENTIONS 1.8, playbook 4.8): the specification has to stand on its
own. Someone integrating from outside the bank reads openapi.json and nothing else, so
every request and response property says what the field means to a bank and when it is
used, every operation says what it is for, and every enumerated or keyed field says where
its values come from.

This gate reads the committed openapi.json (the contract-drift gate proves it matches the
code) and fails with a list of what is undocumented. It checks four things:

1. every property of every component schema carries a non-empty `description`;
2. a description is a sentence, not a label: at least MIN_WORDS words, of which at least
   MIN_MEANINGFUL_WORDS say something the field name and its type do not already say;
3. every operation carries a `description` of the same minimum length beside its summary;
4. an enumerated property names each of its values, and a `key`, `kind` or `*Keys` field
   says where its values come from, in one of the three documented ways (SOURCE_PHRASES):
   a vocabulary an admin manages, a set fixed in code, or a value the caller chooses.
   CLAUDE.md section 5 forbids enums in code for anything but kinds, so a vocabulary-backed
   field says "a key from the <name> list, which an admin manages" and never lists values.

scripts/openapi_quality_allowlist.txt exempts what genuinely needs nothing. Every line
carries its reason after `#`, and a line that suppresses nothing is reported as stale, so
the list shrinks as each app is documented instead of rotting into a mute.

Proven to fail 2026-09-20 by planting a schema with a bare `status` property and a
description repeating the field name (exit 1, both named), kept as the planted schema in
apps/shared/tests_openapi_quality.py.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
SPEC = ROOT / "openapi.json"
ALLOWLIST = BACKEND / "scripts" / "openapi_quality_allowlist.txt"
METHODS = frozenset({"get", "post", "put", "patch", "delete"})

MIN_WORDS = 6
MIN_MEANINGFUL_WORDS = 3
MIN_REASON_WORDS = 3

# The three documented ways a keyed field says where its values come from (CONVENTIONS 1.8).
SOURCE_PHRASES = ("which an admin manages", "fixed in code", "chosen by the")

# A field whose values come from somewhere: exactly `key` or `kind`, or a plural `*Keys`
# and `*Kinds`, or a `*Kind`. A singular `*Key` is not matched: `plainKey` and `keyPrefix`
# are secrets and identifiers, not list members.
KEYED_EXACT = frozenset({"key", "kind"})
KEYED_SUFFIXES = ("Keys", "Kinds", "Kind")

# Words that say nothing a reader does not already have from the field name and its type.
TYPE_WORDS = frozenset(
    """a an the of for to and or is are be this that it its value values field property
    string text integer number boolean flag true false list array object dict map uuid id
    identifier date datetime timestamp time null none optional required nullable type""".split()
)


@dataclass(frozen=True)
class Finding:
    target: str
    problem: str


@dataclass(frozen=True)
class Entry:
    """One allowlist line: `<target>  # <reason>`."""

    line_no: int
    target: str
    reason: str


def load_allowlist(path: Path) -> tuple[list[Entry], list[Finding]]:
    """Parse the allowlist. A line without a reason of at least MIN_REASON_WORDS words is
    a finding of its own, so the list cannot grow by a bare entry."""
    entries: list[Entry] = []
    findings: list[Finding] = []
    if not path.exists():
        return entries, findings
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        target, _, reason = line.partition("#")
        target, reason = target.strip(), reason.strip()
        if len(reason.split()) < MIN_REASON_WORDS:
            findings.append(
                Finding(
                    f"{path.name}:{line_no}",
                    f"the allowlist entry '{target}' carries no reason; add '# <why this needs no description>'",
                )
            )
            continue
        entries.append(Entry(line_no, target, reason))
    return entries, findings


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+", text.lower())


def name_words(name: str) -> set[str]:
    """`roleKeys` -> {role, keys}: the words a description may not live on alone."""
    return set(words(re.sub(r"(?<!^)(?=[A-Z])", " ", name)))


def enum_values(schema: dict[str, Any]) -> list[str]:
    """Every value a property is fixed to, through `enum` or `const`, including inside
    `items`, `anyOf`, `oneOf` and `allOf` (Pydantic wraps an optional field in `anyOf`)."""
    values: list[str] = []
    for value in schema.get("enum", []) or []:
        values.append(str(value))
    if "const" in schema:
        values.append(str(schema["const"]))
    for key in ("items", "additionalProperties"):
        nested = schema.get(key)
        if isinstance(nested, dict):
            values.extend(enum_values(nested))
    for key in ("anyOf", "oneOf", "allOf"):
        for nested in schema.get(key, []) or []:
            if isinstance(nested, dict):
                values.extend(enum_values(nested))
    return values


def is_keyed(name: str) -> bool:
    return name in KEYED_EXACT or name.endswith(KEYED_SUFFIXES)


def describe_problem(name: str, schema: dict[str, Any], description: str | None) -> str | None:
    """What is wrong with this property's documentation, or None when nothing is."""
    if not description or not description.strip():
        return "no description: say what the field means to a bank and when it is used"
    text = description.strip()
    if len(text.split()) < MIN_WORDS:
        return f"the description is {len(text.split())} words; say what it means to a bank, not what its type is"
    meaningful = {word for word in words(text) if word not in TYPE_WORDS} - name_words(name)
    if len(meaningful) < MIN_MEANINGFUL_WORDS:
        return f"the description repeats the field name or its type: {text!r}"
    values = enum_values(schema)
    missing = [value for value in values if value.lower() not in text.lower()]
    if missing:
        return f"the description does not name the values it is fixed to: {', '.join(sorted(missing))}"
    if not values and is_keyed(name) and not any(phrase in text.lower() for phrase in SOURCE_PHRASES):
        return (
            "the description does not say where its values come from: name the list "
            f"({SOURCE_PHRASES[0]}), say they are {SOURCE_PHRASES[1]}, or say they are {SOURCE_PHRASES[2]} caller"
        )
    return None


def check_schemas(schemas: dict[str, Any]) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    total = 0
    for schema_name, schema in sorted(schemas.items()):
        for property_name, property_schema in sorted((schema.get("properties") or {}).items()):
            total += 1
            if not isinstance(property_schema, dict):
                continue
            problem = describe_problem(property_name, property_schema, property_schema.get("description"))
            if problem is not None:
                findings.append(Finding(f"{schema_name}.{property_name}", problem))
    return findings, total


def check_operations(paths: dict[str, Any]) -> tuple[list[Finding], int, dict[str, list[str]]]:
    findings: list[Finding] = []
    total = 0
    tags: dict[str, list[str]] = {}
    for path, item in sorted(paths.items()):
        for method, operation in sorted(item.items()):
            if method not in METHODS or not isinstance(operation, dict):
                continue
            total += 1
            operation_id = operation.get("operationId") or f"{method.upper()} {path}"
            tags[operation_id] = list(operation.get("tags") or [])
            description = (operation.get("description") or "").strip()
            if not description:
                findings.append(
                    Finding(
                        operation_id,
                        "the operation has no description: name the permission or scope it needs, "
                        "the problem codes it can answer with, and what a bank uses it for",
                    )
                )
            elif len(description.split()) < MIN_WORDS:
                findings.append(Finding(operation_id, f"the operation's description is {len(description.split())} words"))
    return findings, total, tags


def allowed_by(entries: list[Entry], target: str, operation_tags: list[str] | None) -> Entry | None:
    """The first allowlist entry covering this finding, or None. `tag:<glob>` covers every
    operation carrying the tag, `op:<glob>` an operation by id, anything else matches
    `<Schema>.<property>`."""
    for entry in entries:
        pattern = entry.target
        if pattern.startswith("tag:"):
            if operation_tags is not None and any(fnmatch(tag, pattern[4:]) for tag in operation_tags):
                return entry
        elif pattern.startswith("op:"):
            if operation_tags is not None and fnmatch(target, pattern[3:]):
                return entry
        elif operation_tags is None and fnmatch(target, pattern):
            return entry
    return None


def run(document: dict[str, Any], entries: list[Entry]) -> tuple[list[Finding], list[Finding], int, int, int]:
    """Returns the findings, the stale allowlist entries, and the property, operation and
    allowlisted counts."""
    schema_findings, properties = check_schemas(document.get("components", {}).get("schemas", {}))
    operation_findings, operations, tags = check_operations(document.get("paths", {}))

    kept: list[Finding] = []
    used: set[str] = set()
    checked: list[tuple[Finding, list[str] | None]] = [(finding, None) for finding in schema_findings]
    checked += [(finding, tags.get(finding.target, [])) for finding in operation_findings]
    for finding, operation_tags in checked:
        entry = allowed_by(entries, finding.target, operation_tags)
        if entry is None:
            kept.append(finding)
        else:
            used.add(entry.target)
    allowlisted = len(schema_findings) + len(operation_findings) - len(kept)
    stale = [
        Finding(entry.target, "the allowlist entry covers nothing any more; delete the line")
        for entry in entries
        if entry.target not in used
    ]
    return kept, stale, properties, operations, allowlisted


def main() -> int:
    document = json.loads(SPEC.read_text(encoding="utf-8"))
    entries, findings = load_allowlist(ALLOWLIST)
    kept, stale, properties, operations, allowlisted = run(document, entries)
    findings = findings + kept + stale
    print(
        f"openapi_quality: {properties} properties, {operations} operations, "
        f"{allowlisted} allowlisted, {len(findings)} undocumented"
    )
    for finding in findings:
        print(f"  {finding.target}: {finding.problem}")
    if findings:
        print(
            "Document each in its Pydantic Field(description=..., examples=[...]) or the view's "
            f"docstring (CONVENTIONS 1.8), or allowlist it with a reason in {ALLOWLIST.relative_to(ROOT).as_posix()}."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
