"""The measured route list (NFR-02): one row per API operation, with the principal that
calls it, the fixture that fills its request and the setting that holds its budget
(`API_BUDGET_MS` unless the row names its own, as hybrid search and Ask do).

An append ledger: each performance pass adds its own rows under a comment naming the pass,
and records them with `python scripts/perf_report.py --record`.

A route behind a per-caller rate limit answers 429 once the requests in its window pass the
limit, and the harness fails a 429 rather than timing it. Every row makes PERF_SAMPLES + 1
requests (21 by default). The window is a fixed minute counted in Redis per caller, so it
spans runs: a --record followed at once by a check counts both. It also spans the routes
that share a bucket: POST /search and POST /search/similar spend one allowance of
SEARCH_RATE_PER_USER_PER_MINUTE (60), and Ask allows ASK_RATE_PER_USER_PER_MINUTE (10). A
pass that measures a limited route raises that limit through its env override for both the
record and the check, or waits out the minute between them.
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
