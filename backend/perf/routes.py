"""The measured route list (NFR-02): one row per API operation, with the principal that
calls it, the fixture that fills its request and the setting that holds its budget
(`API_BUDGET_MS` unless the row names its own, as hybrid search and Ask do).

An append ledger: each performance pass adds its own rows under a comment naming the pass,
and records them with `python scripts/perf_report.py --record`. A route behind a per-person
rate limit answers 429 once one run's requests pass the limit (Ask allows ten a minute), so
a pass raises that limit for its run through the limit's own env override; the harness
fails a 429 rather than timing it.
"""

from __future__ import annotations

from apps.shared.e2e_logins import TENANT_A_SLUG
from perf.harness import PerfRoute, person

READER = "reader@example-bank.test"  # tenant A's seeded reader (apps/shared/e2e_logins.py)

ROUTES: list[PerfRoute] = [
    # perf-harness: three reads every signed-in reader makes, which prove the harness end
    # to end on the seeded data. r1-perf and the chunk 14 passes add the rest.
    PerfRoute("getMe", person(READER, TENANT_A_SLUG)),
    PerfRoute("getHome", person(READER, TENANT_A_SLUG)),
    PerfRoute("listObligations", person(READER, TENANT_A_SLUG)),
]
