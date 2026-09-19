#!/usr/bin/env python3
"""Dependency licence gate (playbook 9: "Dependency licences").

Stops two things:

1. A copyleft dependency in either tree: AGPL (in particular), GPL and SSPL.
   A dual-licensed package passes when at least one alternative is not
   copyleft ("MIT OR GPL-2.0" is fine; "GPL-2.0" is not). Weak copyleft
   (LGPL, MPL, EPL) is reported for information and does not fail: the
   product links against it as a library and never modifies it.
2. Missing Apache attribution for the SEB Green packages: every installed
   `@sebgroup/*` package must be named in frontend/THIRD_PARTY_NOTICES.md and
   that file must carry the Apache-2.0 notice.

A package whose licence cannot be determined (no metadata, "UNKNOWN",
"SEE LICENSE IN ...") also fails: an unclassified dependency is not a pass.
Exceptions live in scripts/licence_exceptions.json, per package, with the
licence actually verified, a reason and a date, so a review can read them.

Modes (see the CI `licences` job):

    backend   run INSIDE the Poetry environment (`bash ./run.sh run python
              ../scripts/check_licences.py backend` from backend/): inspects
              every installed distribution through importlib.metadata, the
              same data pip-licenses reads, without adding a dependency to
              the backend's pyproject.
    frontend  run from anywhere after `npm ci`: walks the packages recorded
              in frontend/package-lock.json and reads each installed
              package.json `license` field (or the legacy `licenses` array).

Stdlib only. Exit codes: 0 clean, 1 gate failed, 2 invalid input.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXCEPTIONS = REPO_ROOT / "scripts" / "licence_exceptions.json"
DEFAULT_NOTICES = REPO_ROOT / "frontend" / "THIRD_PARTY_NOTICES.md"
ATTRIBUTION_SCOPE = "@sebgroup/"

# Strong copyleft: a match anywhere in a single licence term fails it. The
# identifier must stand alone or carry a version suffix ("GPL-3.0", "GPLv2",
# "GPL 2"); the lookbehind keeps "LGPL" out of the "GPL" match.
STRONG_COPYLEFT = re.compile(
    r"(?<![A-Za-z])(AGPL|GPL|SSPL)(?:v?\d|(?![A-Za-z]))|GNU (?:Affero )?General Public|Server Side Public",
    re.I,
)
# Weak copyleft is removed from the term before the strong match runs.
WEAK_COPYLEFT = re.compile(
    r"(?<![A-Za-z])(LGPL|MPL|EPL|CDDL|OSL|EUPL)(?:v?\d|(?![A-Za-z]))|GNU Lesser|GNU Library|Mozilla Public|Eclipse Public",
    re.I,
)
UNKNOWN_MARKERS = re.compile(r"^\s*$|UNKNOWN|SEE LICEN[CS]E|UNLICENSED|LicenseRef-", re.I)


@dataclass
class Package:
    name: str
    version: str
    licences: list[str] = field(default_factory=list)  # alternatives, OR-semantics
    source: str = ""


@dataclass
class Verdict:
    package: Package
    status: str  # "ok" | "weak" | "copyleft" | "unknown" | "excepted"
    detail: str = ""


class GateError(Exception):
    """Invalid input: the gate cannot answer the question it was asked."""


# ---------------------------------------------------------------------------
# SPDX-ish expression evaluation
# ---------------------------------------------------------------------------


def _split_top_level(expression: str, operator: str) -> list[str]:
    """Split on a top-level SPDX operator (outside parentheses).

    Operators are the upper-case SPDX keywords only: free text such as
    "GPL v2 or later" must not be read as a dual licence.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    tokens = re.split(r"(\(|\)|\s+)", expression)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        if depth == 0 and token.strip() == operator:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(token)
        i += 1
    parts.append("".join(current).strip())
    return [p for p in parts if p]


def classify_term(term: str) -> str:
    """Classify one licence term: 'copyleft', 'weak', 'unknown' or 'ok'."""
    term = term.strip().strip("()").strip()
    if UNKNOWN_MARKERS.search(term):
        return "unknown"
    weak = WEAK_COPYLEFT.search(term) is not None
    # Strip the weak identifiers first so "GNU Lesser General Public" and
    # "LGPLv2" cannot be read as the strong family.
    if STRONG_COPYLEFT.search(WEAK_COPYLEFT.sub(" ", term)):
        return "copyleft"
    return "weak" if weak else "ok"


def classify_expression(expression: str) -> str:
    """Evaluate an SPDX expression: OR keeps the best alternative, AND the worst."""
    expression = expression.strip()
    if not expression:
        return "unknown"
    if expression.startswith("(") and expression.endswith(")") and _balanced_wrap(expression):
        return classify_expression(expression[1:-1])
    ors = _split_top_level(expression, "OR")
    if len(ors) > 1:
        return _best(classify_expression(part) for part in ors)
    ands = _split_top_level(expression, "AND")
    if len(ands) > 1:
        return _worst(classify_expression(part) for part in ands)
    withs = _split_top_level(expression, "WITH")
    return classify_term(withs[0])


def _balanced_wrap(expression: str) -> bool:
    depth = 0
    for index, char in enumerate(expression):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(expression) - 1:
                return False
    return depth == 0


_RANK = {"ok": 0, "weak": 1, "unknown": 2, "copyleft": 3}


def _best(statuses: Iterable[str]) -> str:
    return min(statuses, key=_RANK.__getitem__)


def _worst(statuses: Iterable[str]) -> str:
    return max(statuses, key=_RANK.__getitem__)


def classify_package(package: Package) -> str:
    if not package.licences:
        return "unknown"
    return _best(classify_expression(alt) for alt in package.licences)


# ---------------------------------------------------------------------------
# Backend: importlib.metadata inside the Poetry environment
# ---------------------------------------------------------------------------

_CLASSIFIER_NAMES = {
    "GNU Affero General Public License": "AGPL",
    "GNU General Public License": "GPL",
    "GNU Lesser General Public License": "LGPL",
    "GNU Library or Lesser General Public License": "LGPL",
    "Mozilla Public License": "MPL",
    "Eclipse Public License": "EPL",
    "Common Development and Distribution License": "CDDL",
}


def _licence_from_classifier(classifier: str) -> str:
    # "License :: OSI Approved :: MIT License" -> "MIT License"
    leaf = classifier.split("::")[-1].strip()
    for long_name, short in _CLASSIFIER_NAMES.items():
        if long_name in leaf:
            return short
    return leaf


def collect_backend() -> list[Package]:
    from importlib import metadata

    packages: list[Package] = []
    for dist in metadata.distributions():
        meta = dist.metadata
        name = meta.get("Name") or dist.name
        if not name:
            continue
        alternatives: list[str] = []
        expression = meta.get("License-Expression")
        if expression:
            alternatives.append(expression)
        classifiers = [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
        for classifier in classifiers:
            # "License :: Other/Proprietary License" carries no licence name.
            leaf = _licence_from_classifier(classifier)
            if leaf and "Other/Proprietary" not in classifier:
                alternatives.append(leaf)
        if not alternatives:
            free_text = (meta.get("License") or "").strip()
            first_line = free_text.splitlines()[0].strip() if free_text else ""
            # Whole licence texts pasted into the field start with a title line
            # that the classifier matcher understands ("MIT License", "Apache
            # License"); very long fields are truncated to that line.
            if first_line:
                alternatives.append(first_line[:120])
        packages.append(Package(name=name, version=dist.version, licences=alternatives, source="site-packages"))
    return packages


# ---------------------------------------------------------------------------
# Frontend: package-lock.json + installed package.json files
# ---------------------------------------------------------------------------


def _licences_from_package_json(data: dict) -> list[str]:
    licence = data.get("license")
    alternatives: list[str] = []
    if isinstance(licence, str) and licence.strip():
        alternatives.append(licence.strip())
    elif isinstance(licence, dict) and licence.get("type"):
        alternatives.append(str(licence["type"]))
    legacy = data.get("licenses")
    if isinstance(legacy, list):
        for item in legacy:
            if isinstance(item, dict) and item.get("type"):
                alternatives.append(str(item["type"]))
            elif isinstance(item, str):
                alternatives.append(item)
    return alternatives


def collect_frontend(frontend_root: Path) -> list[Package]:
    lock_path = frontend_root / "package-lock.json"
    if not lock_path.is_file() or lock_path.stat().st_size == 0:
        raise GateError(f"{lock_path} is missing or empty; the gate refuses to judge without the committed lockfile")
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"{lock_path} is not valid JSON: {exc}") from exc
    entries = lock.get("packages")
    if not isinstance(entries, dict):
        raise GateError(f"{lock_path} has no 'packages' map; lockfileVersion 2 or 3 is required")
    packages: list[Package] = []
    for rel_path, entry in entries.items():
        if rel_path == "" or entry.get("link"):
            continue  # the project itself, or a workspace symlink
        installed = frontend_root / rel_path / "package.json"
        name = entry.get("name") or rel_path.split("node_modules/")[-1]
        version = str(entry.get("version", "?"))
        if not installed.is_file():
            if entry.get("optional"):
                # Platform-specific optional packages (sharp's per-OS
                # binaries, esbuild's) are skipped by `npm ci` on every other
                # platform; nothing is shipped, so there is nothing to judge.
                continue
            raise GateError(f"{installed} is missing; run `npm ci` in {frontend_root} before this gate")
        try:
            data = json.loads(installed.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GateError(f"{installed} is not valid JSON: {exc}") from exc
        packages.append(Package(name=name, version=version, licences=_licences_from_package_json(data), source=rel_path))
    return packages


# ---------------------------------------------------------------------------
# Exceptions and attribution
# ---------------------------------------------------------------------------


def load_exceptions(path: Path, mode: str) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"{path} is not valid JSON: {exc}") from exc
    entries = data.get(mode, []) if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise GateError(f'{path}: expected an object with a "{mode}" array')
    result: dict[str, dict] = {}
    for index, entry in enumerate(entries):
        missing = [f for f in ("package", "licence", "reason", "acceptedOn", "acceptedBy") if not str(entry.get(f, "")).strip()]
        if missing:
            raise GateError(f"{path}: {mode}[{index}] is missing {', '.join(missing)}")
        try:
            dt.date.fromisoformat(str(entry["acceptedOn"]))
        except ValueError as exc:
            raise GateError(f"{path}: {mode}[{index}].acceptedOn must be YYYY-MM-DD") from exc
        result[_norm(str(entry["package"]))] = entry
    return result


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def check_attribution(packages: list[Package], notices: Path) -> list[str]:
    scoped = sorted({p.name for p in packages if p.name.startswith(ATTRIBUTION_SCOPE)})
    if not scoped:
        return []
    problems: list[str] = []
    if not notices.is_file():
        return [f"{notices} is missing; the {ATTRIBUTION_SCOPE}* packages need an Apache-2.0 attribution notice"]
    text = notices.read_text(encoding="utf-8")
    if not re.search(r"Apache License,? Version 2\.0|Apache-2\.0", text):
        problems.append(f"{notices} does not carry the Apache License 2.0 notice")
    for name in scoped:
        if name not in text:
            problems.append(f"{name} is installed but not attributed in {notices}")
    return problems


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def judge(packages: list[Package], exceptions: dict[str, dict]) -> tuple[list[Verdict], set[str]]:
    verdicts: list[Verdict] = []
    used: set[str] = set()
    for package in sorted(packages, key=lambda p: p.name.lower()):
        status = classify_package(package)
        exception = exceptions.get(_norm(package.name))
        if status in ("copyleft", "unknown") and exception is not None:
            used.add(_norm(package.name))
            verdicts.append(Verdict(package, "excepted", f"{exception['licence']} verified {exception['acceptedOn']} by {exception['acceptedBy']}: {exception['reason']}"))
            continue
        verdicts.append(Verdict(package, status, " OR ".join(package.licences) or "<no licence metadata>"))
    return verdicts, used


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("backend", "frontend", "self-test"))
    parser.add_argument("--frontend-root", type=Path, default=REPO_ROOT / "frontend")
    parser.add_argument("--notices", type=Path, default=DEFAULT_NOTICES)
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    args = parser.parse_args(argv)

    if args.mode == "self-test":
        return self_test()

    try:
        exceptions = load_exceptions(args.exceptions, args.mode)
        packages = collect_backend() if args.mode == "backend" else collect_frontend(args.frontend_root)
        if not packages:
            raise GateError(f"no packages found for {args.mode}; the gate refuses to judge an empty tree")
        verdicts, used = judge(packages, exceptions)
        attribution_problems = check_attribution(packages, args.notices) if args.mode == "frontend" else []
    except GateError as exc:
        print(f"::error::check_licences: {exc}")
        return 2

    failures = [v for v in verdicts if v.status in ("copyleft", "unknown")]
    weak = [v for v in verdicts if v.status == "weak"]
    excepted = [v for v in verdicts if v.status == "excepted"]
    stale = sorted(set(exceptions) - used)

    print(f"Licence gate ({args.mode}): {len(verdicts)} packages, {len(failures)} failing, {len(weak)} weak copyleft, {len(excepted)} excepted")
    for v in weak:
        print(f"  info  {v.package.name}=={v.package.version}: {v.detail}")
    for v in excepted:
        print(f"  note  {v.package.name}=={v.package.version}: exception, {v.detail}")
    for v in failures:
        label = "COPYLEFT" if v.status == "copyleft" else "UNKNOWN"
        print(f"::error::{label} licence: {v.package.name}=={v.package.version} ({v.detail}). Replace it, or record a verified exception in {args.exceptions}.")
    for name in stale:
        print(f"::error::stale licence exception for {name!r} in {args.exceptions}: the package is no longer installed or no longer needs it; remove the entry.")
    for problem in attribution_problems:
        print(f"::error::attribution: {problem}")

    return 1 if (failures or stale or attribution_problems) else 0


def self_test() -> int:
    cases = {
        "MIT": "ok",
        "Apache-2.0": "ok",
        "(MIT OR Apache-2.0)": "ok",
        "MIT OR GPL-2.0-only": "ok",
        "GPL-3.0-or-later": "copyleft",
        "AGPL-3.0": "copyleft",
        "SSPL-1.0": "copyleft",
        "MIT AND GPL-2.0": "copyleft",
        "(MIT AND (GPL-2.0 OR BSD-3-Clause))": "ok",
        "LGPL-2.1-or-later": "weak",
        "MPL-2.0": "weak",
        "GPL-2.0 WITH Classpath-exception-2.0": "copyleft",
        "": "unknown",
        "UNKNOWN": "unknown",
        "SEE LICENSE IN LICENSE.txt": "unknown",
        "UNLICENSED": "unknown",
        "GNU General Public License v3 (GPLv3)": "copyleft",
        "GNU Lesser General Public License v2 or later (LGPLv2+)": "weak",
        "GNU Affero General Public License v3": "copyleft",
        "BSD License": "ok",
        "Python Software Foundation License": "ok",
    }
    failed = 0
    for expression, expected in cases.items():
        got = classify_expression(expression)
        if got != expected:
            failed += 1
            print(f"FAIL {expression!r}: expected {expected}, got {got}")
    dual = Package("x", "1", ["GPL-2.0", "MIT"])
    if classify_package(dual) != "ok":
        failed += 1
        print("FAIL classifier dual licence should pass")
    print(f"self-test: {len(cases) + 1} cases, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
