#!/usr/bin/env python
"""The API performance report (NFR-02, playbook 10): every row of backend/perf/routes.py,
measured by the harness and judged against its budget and its recorded baseline.

    python scripts/perf_report.py            # judge every route
    python scripts/perf_report.py --record   # write backend/perf/baseline.json

Run it from backend/ with the task's slot loaded (`set -a; . ./.env.worktree; set +a`),
against a database seeded with `manage.py seed_e2e`, under `config.settings`: the app's own
role, the real middleware and row-level security. It refuses a deployed environment.

Without --record a route fails when the 95th percentile of its server time is over its
budget, when its median is more than PERF_REGRESSION_PCT per cent above the median in the
baseline, or when the baseline has no entry for it. The budget is read on the 95th
percentile because that is what one request in twenty waits; the regression on the median
because it is the number that holds still on a busy machine, so noise does not fail a route
nobody changed. It holds still only under the same load, though: record and judge back to
back on a machine nothing else is loading, because other work on it moves a 15 ms route by
more than 20 % on its own (measured 2026-09-23 beside four agents' test runs). Each line
names the route, the measured times, the budget and the query count, so the output says
where to look.

With --record the measurements become the baseline. A route that cannot be measured (a
wrong status, a principal the database does not hold) fails the run and nothing is written,
so a baseline never has a hole in it. Exit 0 when every route passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

BACKEND = Path(__file__).resolve().parent.parent
BASELINE = BACKEND / "perf" / "baseline.json"

if TYPE_CHECKING:
    from perf.harness import Measurement, PerfRoute


def report(routes: Sequence[PerfRoute], *, record: bool, baseline_path: Path) -> int:
    from django.conf import settings

    from perf.harness import PerfRefused, RouteFailed, measure

    baseline = {} if record else _read(baseline_path)
    measured: dict[str, dict[str, Any]] = {}
    failed = False
    for route in routes:
        try:
            result = measure(route)
        except PerfRefused as refusal:
            print(refusal)
            return 1
        except RouteFailed as failure:
            print(f"{route.operation}: FAIL {failure}")
            failed = True
            continue
        measured[result.operation] = {
            "medianMs": round(result.median_ms, 1),
            "p95Ms": round(result.p95_ms, 1),
            "queries": result.queries,
        }
        line = (
            f"{result.operation}: median {result.median_ms:.1f} ms, p95 {result.p95_ms:.1f} ms, "
            f"budget {result.budget_ms} ms ({result.budget}), {result.queries} queries"
        )
        if record:
            print(line)
            continue
        problems = _problems(result, baseline.get(result.operation), settings.PERF_REGRESSION_PCT)
        print(f"{line}: {'FAIL ' + '; '.join(problems) if problems else 'ok'}")
        failed = failed or bool(problems)
    if record and not failed:
        baseline_path.write_text(json.dumps(measured, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline written to {baseline_path}")
    return 1 if failed else 0


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _problems(result: Measurement, recorded: dict[str, Any] | None, regression_pct: int) -> list[str]:
    problems = []
    if result.p95_ms > result.budget_ms:
        problems.append(f"p95 is over the {result.budget_ms} ms budget")
    if recorded is None:
        problems.append("no baseline yet: record one with --record")
    elif result.median_ms > recorded["medianMs"] * (1 + regression_pct / 100):
        problems.append(
            f"median is more than {regression_pct} % above its baseline of {recorded['medianMs']} ms "
            f"(PERF_REGRESSION_PCT)"
        )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="perf_report", description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--record", action="store_true", help="write the measurements to backend/perf/baseline.json")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(BACKEND))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    from django.test.utils import setup_test_environment

    django.setup()
    # The harness drives the API through Django's in-process client, whose host is
    # `testserver`: this admits that host, and swaps the mailer for an in-memory one so that
    # nothing measured sends mail.
    setup_test_environment()
    from perf.routes import ROUTES

    return report(ROUTES, record=args.record, baseline_path=BASELINE)


if __name__ == "__main__":
    sys.exit(main())
