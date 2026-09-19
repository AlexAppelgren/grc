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
Measured 2026-09-19, chunk 1 close: 190 tests (334 collected, 144 scenario stubs
skipped), aggregate 96% over 3696 statements.
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
    "apps/shared/permissions.py": (97, 99, 142, "2026-09-19"),
    "apps/shared/audit.py": (96, 100, 45, "2026-09-19"),
    "apps/shared/db_role_guard.py": (86, 90, 53, "2026-09-19"),
    "apps/shared/health_check.py": (88, 92, 65, "2026-09-19"),
    "apps/shared/middleware.py": (96, 100, 68, "2026-09-19"),
    # The code and invitation mail leaves through the worker after commit, so a code request
    # takes the same time whether or not it sends (security review F12).
    "apps/identity/tasks.py": (96, 100, 6, "2026-09-19"),
    "apps/shared/adapters/mailer.py": (96, 100, 38, "2026-09-19"),
    "apps/shared/sentry_scrub.py": (89, 93, 41, "2026-09-19"),
    "apps/shared/storage.py": (95, 99, 62, "2026-09-19"),
    "apps/shared/vocabulary.py": (91, 96, 55, "2026-09-19"),
    "apps/shared/e2e_seed.py": (96, 97, 93, "2026-09-19"),
    "config/settings.py": (85, 87, 166, "2026-09-19"),
    # Chunk 1 (identity and tenant admin basics): the modules that let the wrong person
    # through, measured at the chunk's close on 2026-09-19.
    "apps/identity/tokens.py": (94, 98, 84, "2026-09-19"),
    "apps/identity/rate_limit.py": (96, 100, 19, "2026-09-19"),
    "apps/identity/session_logic.py": (92, 95, 160, "2026-09-19"),
    "apps/identity/code_logic.py": (92, 96, 77, "2026-09-19"),
    "apps/identity/invitation_logic.py": (91, 94, 134, "2026-09-19"),
    "apps/identity/passkey_logic.py": (90, 93, 181, "2026-09-19"),
    "apps/identity/api_keys_logic.py": (92, 96, 67, "2026-09-19"),
    "apps/identity/roles_logic.py": (92, 95, 137, "2026-09-19"),
    "apps/identity/members_logic.py": (96, 99, 101, "2026-09-19"),
    "apps/identity/me_logic.py": (89, 93, 45, "2026-09-19"),
    "apps/identity/security_log.py": (89, 93, 22, "2026-09-19"),
    "apps/identity/mail.py": (96, 100, 20, "2026-09-19"),
    "apps/identity/api.py": (95, 98, 215, "2026-09-19"),
    "apps/tenants/logic.py": (87, 91, 91, "2026-09-19"),
    "apps/tenants/api.py": (96, 100, 31, "2026-09-19"),
    # Chunk 3 (library data layer): the "as of" rule and the loader that files the
    # prototype's library, measured 2026-09-19 over 426 tests (301 run, 125 scenario stubs
    # skipped), aggregate 97% over 6641 statements. seeds.py became the seeds/ package.
    "apps/library/seeds/__init__.py": (96, 100, 22, "2026-09-19"),
    "apps/library/seeds/library.py": (96, 100, 85, "2026-09-19"),
    "apps/library/logic.py": (96, 100, 9, "2026-09-19"),
    # Chunk 2 (vocabularies, taxonomy, footprint, proposals): footprint matching, vocabulary
    # retire and merge, four eyes and proposal apply, measured 2026-09-19 over 409 tests
    # (284 run, 125 scenario stubs skipped), aggregate 97% over 6221 statements.
    "apps/proposals/apply.py": (90, 93, 148, "2026-09-19"),
    "apps/proposals/logic.py": (97, 100, 123, "2026-09-19"),
    "apps/proposals/api.py": (96, 100, 44, "2026-09-19"),
    "apps/taxonomy/api.py": (96, 99, 216, "2026-09-19"),
    "apps/taxonomy/footprint_logic.py": (97, 100, 109, "2026-09-19"),
    "apps/taxonomy/http.py": (93, 96, 103, "2026-09-19"),
    "apps/taxonomy/library_lists_logic.py": (94, 98, 86, "2026-09-19"),
    "apps/taxonomy/matching.py": (96, 100, 31, "2026-09-19"),
    "apps/taxonomy/reading.py": (82, 86, 63, "2026-09-19"),
    "apps/taxonomy/registry.py": (96, 100, 38, "2026-09-19"),
    "apps/taxonomy/repoint.py": (96, 100, 19, "2026-09-19"),
    "apps/taxonomy/tenant_hooks.py": (96, 100, 37, "2026-09-19"),
    "apps/taxonomy/tenant_lists_logic.py": (94, 97, 304, "2026-09-19"),
    "apps/taxonomy/terms_logic.py": (94, 98, 72, "2026-09-19"),
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
