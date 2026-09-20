#!/usr/bin/env python3
"""CI tier drift (CLAUDE.md section 7, playbook Appendix D).

`scripts/prepush.sh` promises that a green local run predicts a green CI run. That
holds only while three lists say the same thing: the `changes` job in
.github/workflows/ci.yml, the `changes` job in .github/workflows/codeql.yml, and the
classification loop in scripts/prepush.sh. A pattern added to one and forgotten in
the others is silent: prepush would run gates CI skips, or skip gates CI runs, and
the first anyone hears of it is a red push.

This compares the three. Each pattern is reduced to a token first, because the files
say the same thing in two syntaxes (dorny/paths-filter extglob in the workflows,
`case` patterns in the shell):

    backend/**/!(*.md)                      -> backend/!md
    backend/*.md) ;;  backend/*) be=1 ;;    -> backend/!md
    infra/db/**   /   infra/db/*            -> infra/db/
    **/.dockerignore  /  */.dockerignore    -> .dockerignore
    **/*.py       /   *.py                  -> *.py

A tier is a promise about what a file can change, never a way to run less: a file may
skip a gate only when it cannot change what that gate measures.

    python scripts/check_ci_tiers.py             check this repository
    python scripts/check_ci_tiers.py self-test   prove it still catches drift

Stdlib only. Exit codes: 0 clean, 1 drift, 2 a file this guard can no longer read.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CODEQL = REPO_ROOT / ".github" / "workflows" / "codeql.yml"
PREPUSH = REPO_ROOT / "scripts" / "prepush.sh"

# The variable prepush.sh sets, and the filter name the workflows give that tier.
VARIABLE_TIER = {
    "full": "workflows",
    "be": "backend",
    "spec": "specs",
    "fe": "frontend",
    "lock": "lockfiles",
    "cont": "containers",
    "py": "python",
    "js": "javascript",
}

FILTERS_HEAD = re.compile(r"^(?P<indent> *)filters: *\| *$")
TIER_HEAD = re.compile(r"^ *(?P<name>[a-z][a-z0-9_-]*): *$")
TIER_ITEM = re.compile(r"^ *- +(?P<pattern>\S.*?) *$")
CASE = re.compile(r'case +"\$f" +in(?P<body>.*?)esac', re.S)
ARM = re.compile(r"^\s*(?P<patterns>[^)]*?)\)\s*(?P<body>.*)$", re.S)
ASSIGN = re.compile(r"^(?P<var>[a-z_]+)=1$")


class Unreadable(Exception):
    """A file no longer has the shape this guard reads; nothing is compared."""


def token(pattern: str) -> str:
    """One pattern in either syntax, reduced to the thing it actually selects."""
    text = pattern.strip().strip("'\"")
    if text.endswith("/**/!(*.md)"):
        return text[: -len("/**/!(*.md)")] + "/!md"
    for prefix in ("**/", "*/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    for suffix in ("/**", "/*"):
        if text.endswith(suffix):
            return text[: -len(suffix)] + "/"
    return text


def workflow_tiers(text: str, name: str) -> dict[str, set[str]]:
    """The `filters: |` block of a workflow's paths-filter step."""
    lines = text.splitlines()
    for start, line in enumerate(lines):
        head = FILTERS_HEAD.match(line)
        if head:
            break
    else:
        raise Unreadable(f"{name}: no `filters: |` block, so its tiers cannot be read")
    base = len(head.group("indent"))
    tiers: dict[str, set[str]] = {}
    current: str | None = None
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        if len(line) - len(line.lstrip(" ")) <= base:
            break
        if line.lstrip().startswith("#"):
            continue
        tier = TIER_HEAD.match(line)
        if tier:
            current = tier.group("name")
            tiers[current] = set()
            continue
        item = TIER_ITEM.match(line)
        if item is None or current is None:
            raise Unreadable(f"{name}: cannot read the filter line {line.strip()!r}")
        tiers[current].add(token(item.group("pattern")))
    return tiers


def prepush_tiers(text: str) -> dict[str, set[str]]:
    """The `case` arms of the loop that classifies each changed file."""
    loop = re.search(r"while IFS= read -r f; do(?P<body>.*?)\ndone <<<", text, re.S)
    if loop is None:
        raise Unreadable("prepush.sh: no `while IFS= read -r f` classification loop")
    tiers: dict[str, set[str]] = {}
    excludes_markdown: set[str] = set()
    for case in CASE.finditer(loop.group("body")):
        for arm in case.group("body").split(";;"):
            if not arm.strip():
                continue
            parsed = ARM.match(arm)
            if parsed is None:
                raise Unreadable(f"prepush.sh: cannot read the case arm {arm.strip()!r}")
            patterns = [p.strip() for p in parsed.group("patterns").split("|")]
            body = parsed.group("body").strip()
            if not body:
                # `backend/*.md) ;;` standing in front of `backend/*)`: the tier takes
                # the tree but not its markdown, which is `backend/**/!(*.md)` in YAML.
                for pattern in patterns:
                    if not pattern.endswith("/*.md"):
                        raise Unreadable(f"prepush.sh: the case arm {pattern!r} assigns no tier")
                    excludes_markdown.add(pattern[: -len("*.md")])
                continue
            assign = ASSIGN.match(body)
            if assign is None or assign.group("var") not in VARIABLE_TIER:
                raise Unreadable(f"prepush.sh: the case arm body {body!r} is not a known tier")
            tier = VARIABLE_TIER[assign.group("var")]
            for pattern in patterns:
                selected = token(pattern)
                if selected in excludes_markdown:
                    selected = selected[:-1] + "/!md"
                tiers.setdefault(tier, set()).add(selected)
    return tiers


def compare(ci: dict[str, set[str]], codeql: dict[str, set[str]], prepush: dict[str, set[str]]) -> list[str]:
    problems = []
    for name in sorted(set(ci) & set(codeql)):
        if ci[name] != codeql[name]:
            problems.append(
                f"tier '{name}': ci.yml selects {sorted(ci[name])}, codeql.yml selects {sorted(codeql[name])}"
            )
    workflows = {**ci, **codeql}
    for name in sorted(set(workflows) | set(prepush)):
        wanted, found = workflows.get(name), prepush.get(name)
        if wanted is None:
            problems.append(f"tier '{name}': prepush.sh classifies into it, no workflow filter defines it")
        elif found is None:
            problems.append(f"tier '{name}': a workflow filter defines it, prepush.sh classifies nothing into it")
        else:
            if wanted - found:
                problems.append(f"tier '{name}': the workflows select {sorted(wanted - found)}, prepush.sh does not")
            if found - wanted:
                problems.append(f"tier '{name}': prepush.sh selects {sorted(found - wanted)}, the workflows do not")
    return problems


def check() -> int:
    try:
        ci = workflow_tiers(CI.read_text(encoding="utf-8"), "ci.yml")
        codeql = workflow_tiers(CODEQL.read_text(encoding="utf-8"), "codeql.yml")
        prepush = prepush_tiers(PREPUSH.read_text(encoding="utf-8"))
    except (Unreadable, OSError) as unreadable:
        print(f"CI tiers: {unreadable}")
        return 2
    problems = compare(ci, codeql, prepush)
    if problems:
        print("CI tiers have drifted apart; a green prepush no longer predicts a green CI run:")
        for problem in problems:
            print(f"  - {problem}")
        print("Fix .github/workflows/ci.yml, .github/workflows/codeql.yml and scripts/prepush.sh together.")
        return 1
    listed = ", ".join(f"{name} ({len(patterns)})" for name, patterns in sorted({**ci, **codeql}.items()))
    print(f"CI tiers agree across ci.yml, codeql.yml and prepush.sh: {listed}")
    return 0


WORKFLOW_FIXTURE = """
      - uses: dorny/paths-filter@sha
        with:
          filters: |
            workflows:
              - '.github/**'
            backend:
              # a comment inside the block
              - 'backend/**/!(*.md)'
              - 'docker-compose.yml'
            specs:
              - 'PRD.md'
      - name: Next step
"""
CODEQL_FIXTURE = """
          filters: |
            workflows:
              - '.github/**'
            python:
              - '**/*.py'
"""
PREPUSH_FIXTURE = """
while IFS= read -r f; do
  case "$f" in .github/*) full=1 ;; esac
  case "$f" in PRD.md) spec=1 ;; esac
  case "$f" in docker-compose.yml) be=1 ;; backend/*.md) ;; backend/*) be=1 ;; esac
  case "$f" in *.py) py=1 ;; esac
done <<< "$(git diff --name-only)"
"""


def self_test() -> int:
    """Proven to fail 2026-09-20 by dropping `docker-compose.yml` from the backend
    filter (one problem naming it) and by adding an unknown tier to prepush.sh."""
    failures = 0
    ci = workflow_tiers(WORKFLOW_FIXTURE, "ci.yml")
    codeql = workflow_tiers(CODEQL_FIXTURE, "codeql.yml")
    prepush = prepush_tiers(PREPUSH_FIXTURE)
    cases: list[tuple[str, list[str], int]] = [
        ("agreeing lists", compare(ci, codeql, prepush), 0),
        ("a pattern only the workflow has", compare({**ci, "backend": ci["backend"] | {"extra.yml"}}, codeql, prepush), 1),
        ("a pattern only prepush has", compare(ci, codeql, {**prepush, "specs": prepush["specs"] | {"extra.md"}}), 1),
        ("a tier prepush never classifies", compare({**ci, "reports": {"x"}}, codeql, prepush), 1),
        # The workflows disagreeing is reported once for them and once per side
        # against prepush.sh, so nobody reads the first line and fixes only half.
        ("the two workflows disagreeing", compare(ci, {**codeql, "workflows": {"other/"}}, prepush), 3),
    ]
    for name, problems, expected in cases:
        if len(problems) != expected:
            failures += 1
            print(f"FAIL {name}: expected {expected} problems, got {problems}")
    equivalences = [
        ("backend/**/!(*.md)", "backend/!md"),
        ("infra/db/**", "infra/db/"),
        ("infra/db/*", "infra/db/"),
        ("**/.dockerignore", ".dockerignore"),
        ("*/.dockerignore", ".dockerignore"),
        ("**/*.py", "*.py"),
        ("backend/apps/*/app.md", "backend/apps/*/app.md"),
    ]
    for pattern, expected_token in equivalences:
        if token(pattern) != expected_token:
            failures += 1
            print(f"FAIL token({pattern!r}): expected {expected_token!r}, got {token(pattern)!r}")
    if prepush["backend"] != {"docker-compose.yml", "backend/!md"}:
        failures += 1
        print(f"FAIL the markdown exclusion did not survive the shell syntax: {prepush['backend']}")
    for name, text in (("workflow", "nothing: here\n"), ("prepush", "echo nothing\n")):
        try:
            workflow_tiers(text, "x") if name == "workflow" else prepush_tiers(text)
        except Unreadable:
            continue
        failures += 1
        print(f"FAIL an unreadable {name} file was not reported")
    print(f"self-test: {len(cases) + len(equivalences) + 3} cases, {failures} failed")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if not argv:
        return check()
    if argv == ["self-test"]:
        return self_test()
    print("usage: check_ci_tiers.py [self-test]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
