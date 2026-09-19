#!/usr/bin/env python
"""Requirements coverage (playbook 9): a PRD requirement with no scenario, or a scenario
with no test, fails the build.

Sources and grammar (agreed with the docs agent, Appendix B):

- PRD.md requirement IDs: table rows `| <PREFIX>-<nn> | ... |` (ID-01, NFR-05, ...). The
  journey prefix `J-` is excluded: PRD §5's journey table has the same row shape, so
  from J-10 onwards a journey would otherwise be read as a requirement (2026-09-19).
- backend/apps/*/app.md scenario headings, exactly:
      ### <PREFIX>-S<n> — <Title> `@integration`[ `@e2e`] (<refs>)
  where <refs> is a comma-separated list of requirement IDs (ID-03), acceptance criteria
  (AC-ID1) and journeys (J-1). Prefix sequences are numbered globally, so one prefix can
  span two apps (ADM-S1..S3 in tenants, ADM-S4..S6 in governance). A scenario referencing
  a requirement hosted elsewhere is a cross-reference: a requirement is covered when ANY
  scenario in ANY app.md lists its ID.
- Every `@integration` scenario needs `def test_<id lowercased, hyphen -> underscore>(`
  in that app's tests_scenarios.py (skipped is fine).
- Every `@e2e` scenario needs a `test(` or `test.fixme(` whose title contains the ID in
  frontend/tests/e2e/*.spec.ts (fixme is fine). No spec files at all is reported as
  every @e2e scenario missing, never as a pass.

Also refused: a requirement ID in an app.md table that the PRD does not know, a scenario
ID used twice, a test method in tests_scenarios.py with no matching heading.

Proven to fail 2026-09-19 by renaming ID-S1 to ID-S99 in identity/app.md (exit 1, the
missing test named), then restored.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
PRD = ROOT / "PRD.md"
E2E_DIR = ROOT / "frontend" / "tests" / "e2e"

REQ_ROW = re.compile(r"^\|\s*(?!J-)([A-Z0-9]+-\d{2})\s*\|", re.M)
HEADING = re.compile(
    r"^###\s+(?P<id>[A-Z0-9]+-S\d+)\s+—\s+(?P<title>.+?)\s+(?P<tags>(?:`@\w+`\s*)+)\((?P<refs>[^)]*)\)\s*$",
    re.M,
)
LOOSE_HEADING = re.compile(r"^###\s+([A-Z0-9]+-S\d+)\b.*$", re.M)
TEST_METHOD = re.compile(r"^\s*def (test_[a-z0-9_]+)\(", re.M)
E2E_TITLE = re.compile(r"test(?:\.fixme)?\(\s*(['\"`])(.*?)\1", re.S)


@dataclass
class Scenario:
    id: str
    app: str
    title: str
    tags: set[str]
    refs: list[str] = field(default_factory=list)

    @property
    def method_name(self) -> str:
        return "test_" + self.id.lower().replace("-", "_")


def prd_requirements() -> set[str]:
    return set(REQ_ROW.findall(PRD.read_text(encoding="utf-8")))


def parse_app(app_md: Path) -> tuple[set[str], list[Scenario], list[str]]:
    text = app_md.read_text(encoding="utf-8")
    app = app_md.parent.name
    table_ids = set(REQ_ROW.findall(text))
    problems: list[str] = []
    scenarios: list[Scenario] = []
    strict = {m.group("id") for m in HEADING.finditer(text)}
    for m in LOOSE_HEADING.finditer(text):
        if m.group(1) not in strict:
            problems.append(f"{app}/app.md: heading for {m.group(1)} does not match the grammar: {m.group(0).strip()}")
    for m in HEADING.finditer(text):
        tags = set(re.findall(r"@\w+", m.group("tags")))
        refs = [r.strip() for r in m.group("refs").split(",") if r.strip()]
        scenarios.append(Scenario(m.group("id"), app, m.group("title"), tags, refs))
    return table_ids, scenarios, problems


def main() -> int:
    problems: list[str] = []
    requirements = prd_requirements()
    if not requirements:
        print("requirements_coverage: no requirement IDs found in PRD.md")
        return 1
    app_mds = sorted(BACKEND.glob("apps/*/app.md"))
    if not app_mds:
        print("requirements_coverage: no backend/apps/*/app.md found; the docs agent has not landed them")
        return 1

    all_scenarios: list[Scenario] = []
    seen_ids: dict[str, str] = {}
    table_ids_all: set[str] = set()
    for app_md in app_mds:
        table_ids, scenarios, app_problems = parse_app(app_md)
        problems.extend(app_problems)
        table_ids_all |= table_ids
        for rid in sorted(table_ids - requirements):
            problems.append(f"{app_md.parent.name}/app.md lists {rid}, which PRD.md does not know")
        for scenario in scenarios:
            if scenario.id in seen_ids:
                problems.append(f"scenario {scenario.id} appears in both {seen_ids[scenario.id]} and {scenario.app}")
            seen_ids[scenario.id] = scenario.app
            if not scenario.tags & {"@integration", "@e2e"}:
                problems.append(f"{scenario.id}: neither @integration nor @e2e")
            for ref in scenario.refs:
                if re.fullmatch(r"(?!J-)[A-Z0-9]+-\d{2}", ref) and ref not in requirements:
                    problems.append(f"{scenario.id} references {ref}, which PRD.md does not know")
        all_scenarios.extend(scenarios)

    # 1. Every PRD requirement has a scenario somewhere and a row in some app.md.
    covered = {ref for s in all_scenarios for ref in s.refs}
    for rid in sorted(requirements):
        if rid not in covered:
            problems.append(f"{rid}: no scenario in any app.md references it")
        if rid not in table_ids_all:
            problems.append(f"{rid}: no app.md requirement table lists it")

    # 2. Every @integration scenario has its test method; no orphan test methods.
    for app_md in app_mds:
        app = app_md.parent.name
        tests_path = app_md.parent / "tests_scenarios.py"
        app_scenarios = [s for s in all_scenarios if s.app == app and "@integration" in s.tags]
        methods = set(TEST_METHOD.findall(tests_path.read_text(encoding="utf-8"))) if tests_path.exists() else set()
        if app_scenarios and not tests_path.exists():
            problems.append(f"{app}: tests_scenarios.py missing ({len(app_scenarios)} @integration scenarios)")
            continue
        expected = {s.method_name: s.id for s in app_scenarios}
        for name, sid in sorted(expected.items()):
            if name not in methods:
                problems.append(f"{sid}: no {name}() in {app}/tests_scenarios.py")
        for name in sorted(methods - set(expected)):
            problems.append(f"{app}/tests_scenarios.py: {name}() matches no @integration heading in app.md")

    # 3. Every @e2e scenario has a spec title carrying its ID.
    e2e_scenarios = [s for s in all_scenarios if "@e2e" in s.tags]
    spec_titles: list[str] = []
    for spec in sorted(E2E_DIR.glob("*.spec.ts")) if E2E_DIR.exists() else []:
        spec_titles.extend(t for _, t in E2E_TITLE.findall(spec.read_text(encoding="utf-8")))
    if e2e_scenarios and not spec_titles:
        problems.append(f"no frontend/tests/e2e/*.spec.ts titles found; {len(e2e_scenarios)} @e2e scenarios unmatched")
    else:
        for scenario in e2e_scenarios:
            if not any(re.search(rf"\b{re.escape(scenario.id)}\b", title) for title in spec_titles):
                problems.append(f"{scenario.id}: no test(...) or test.fixme(...) title in frontend/tests/e2e carries it")

    print(
        f"requirements_coverage: {len(requirements)} requirements, {len(all_scenarios)} scenarios "
        f"({sum('@integration' in s.tags for s in all_scenarios)} @integration, {len(e2e_scenarios)} @e2e), "
        f"{len(problems)} problem(s)"
    )
    for problem in problems:
        print("  " + problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
