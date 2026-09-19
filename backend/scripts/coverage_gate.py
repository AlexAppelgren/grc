#!/usr/bin/env python
"""Per-module coverage floors (playbook 8.2). Run after `coverage run ... && coverage report`.

Floors sit just below measured coverage with a margin sized to the module: minus 2 at
400+ statements, minus 3 at 100 to 400, minus 4 below 100. Never lowered to go green;
raised when a module climbs away. The measured value, the test count and the date sit
beside each floor and are restated whenever this file is touched.

The gate refuses to judge a partial run: if the aggregate sits more than
PARTIAL_RUN_MARGIN points under the global floor in pyproject.toml, the suite was
subsetted and the question is wrong, so the answer is "cannot judge" (exit 2), not pass.

Proven to fail 2026-09-19 by setting the tenancy floor to 101 (exit 1, module named)
and by running one test module only (exit 2, partial run refused), then restored.

Measured 2026-09-19, Phase 0 close: 128 tests (296 collected, 168 scenario stubs
skipped), aggregate 97% over 1448 statements.
"""

from __future__ import annotations

import json
import sys
import tempfile
import tomllib
from pathlib import Path

import coverage

BACKEND = Path(__file__).resolve().parent.parent
PARTIAL_RUN_MARGIN = 15.0

# module path (as coverage reports it, forward slashes) -> (floor %, measured %, statements, date)
# Only the modules where a bug costs money, mis-states a statutory figure or lets the wrong
# person through: tenancy, authentication, permissions, audit, health, the role guard.
# Proposals, cases, register, footprint, vocabulary and search join as their chunks land.
FLOORS: dict[str, tuple[int, int, int, str]] = {
    "apps/shared/tenancy.py": (96, 100, 85, "2026-09-19"),
    "apps/shared/authentication.py": (96, 100, 55, "2026-09-19"),
    "apps/shared/permissions.py": (97, 100, 127, "2026-09-19"),
    "apps/shared/audit.py": (96, 100, 45, "2026-09-19"),
    "apps/shared/db_role_guard.py": (86, 90, 53, "2026-09-19"),
    "apps/shared/health_check.py": (88, 92, 65, "2026-09-19"),
    "apps/shared/middleware.py": (96, 100, 60, "2026-09-19"),
    "apps/shared/sentry_scrub.py": (89, 93, 41, "2026-09-19"),
    "apps/shared/storage.py": (95, 99, 62, "2026-09-19"),
    "apps/shared/vocabulary.py": (91, 95, 50, "2026-09-19"),
    "apps/shared/e2e_seed.py": (96, 100, 34, "2026-09-19"),
    "config/settings.py": (85, 88, 156, "2026-09-19"),
}


def global_floor() -> float:
    with (BACKEND / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    return float(data["tool"]["coverage"]["report"]["fail_under"])


def load_report() -> dict:
    cov = coverage.Coverage(data_file=str(BACKEND / ".coverage"), config_file=str(BACKEND / "pyproject.toml"))
    cov.load()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "coverage.json"
        cov.json_report(outfile=str(out))
        return json.loads(out.read_text(encoding="utf-8"))


def main() -> int:
    report = load_report()
    total = float(report["totals"]["percent_covered"])
    floor = global_floor()
    print(f"aggregate {total:.1f}% (global floor {floor:.0f}%)")
    if total < floor - PARTIAL_RUN_MARGIN:
        print(
            f"coverage_gate: refusing to judge a partial run: aggregate {total:.1f}% is more than "
            f"{PARTIAL_RUN_MARGIN:.0f} points under the global floor. Run the whole suite."
        )
        return 2
    files = {Path(name).as_posix(): data for name, data in report["files"].items()}
    # coverage reports paths relative to the run's cwd (backend/) on every platform.
    normalised = {name.replace("\\", "/"): data for name, data in files.items()}
    failures: list[str] = []
    for module, (module_floor, measured, statements, date) in FLOORS.items():
        data = normalised.get(module)
        if data is None:
            failures.append(f"{module}: not in the coverage report (renamed? deleted?)")
            continue
        percent = float(data["summary"]["percent_covered"])
        mark = "ok" if percent >= module_floor else "BELOW FLOOR"
        print(f"  {module}: {percent:.1f}% (floor {module_floor}, measured {measured} on {date}, {statements} stmts) {mark}")
        if percent < module_floor:
            failures.append(f"{module}: {percent:.1f}% < floor {module_floor}%")
    if total < floor:
        failures.append(f"aggregate {total:.1f}% < global floor {floor:.0f}%")
    if failures:
        print("coverage_gate: FAILED\n  " + "\n  ".join(failures))
        return 1
    print("coverage_gate: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
