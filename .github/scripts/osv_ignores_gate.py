#!/usr/bin/env python3
"""Every accepted advisory expires (CLAUDE.md section 7, D-119).

osv-scanner reads `osv-scanner.toml` beside each scanned lockfile and sets aside the
advisories listed there, until each entry's `ignoreUntil`. An entry without
`ignoreUntil` is accepted for ever, and osv-scanner says nothing about it, so this
refuses one (review 2026-11-11 L-11). Run before osv-scanner in ci.yml `cve` and in
scripts/prepush.sh.

    python3 .github/scripts/osv_ignores_gate.py             check every committed osv-scanner.toml
    python3 .github/scripts/osv_ignores_gate.py self-test   prove it still catches one

Stdlib only. Exit codes: 0 clean, 1 an entry without an expiry, 2 a file it cannot read.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SECTIONS = ("IgnoredVulns", "PackageOverrides")


def entries_without_expiry(text: str) -> list[str]:
    """The entries of one osv-scanner.toml that set something aside with no `ignoreUntil`."""
    config = tomllib.loads(text)
    return [
        str(entry.get("id") or entry.get("name") or entry)
        for section in SECTIONS
        for entry in config.get(section, [])
        if "ignoreUntil" not in entry
    ]


def self_test() -> int:
    cases = {
        'id = "x"': [],
        '[[IgnoredVulns]]\nid = "GHSA-a"\nignoreUntil = 2026-12-01\nreason = "r"': [],
        '[[IgnoredVulns]]\nid = "GHSA-a"\nreason = "r"': ["GHSA-a"],
        '[[PackageOverrides]]\nname = "braces"\nignore = true': ["braces"],
    }
    failed = [text for text, expected in cases.items() if entries_without_expiry(text) != expected]
    print(f"self-test: {len(cases)} cases, {len(failed)} failed")
    return 1 if failed else 0


def main() -> int:
    if sys.argv[1:] == ["self-test"]:
        return self_test()
    listed = subprocess.run(
        ["git", "ls-files", "*osv-scanner.toml"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    problems: list[str] = []
    for name in listed:
        try:
            missing = entries_without_expiry((REPO_ROOT / name).read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            print(f"osv_ignores_gate: cannot read {name}: {exc}", file=sys.stderr)
            return 2
        problems += [f"{name}: {entry} has no ignoreUntil" for entry in missing]
    for problem in problems:
        print(f"osv_ignores_gate: {problem}", file=sys.stderr)
    print(f"osv_ignores_gate: {len(listed)} file(s), {len(problems)} entry(ies) without an expiry")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
