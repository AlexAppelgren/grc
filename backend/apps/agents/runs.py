"""Agent runs (AGT-01): open a run, close it, read the log of what ran.

The contract is declared ahead of the logic (chunk 5 plan rule 1), so each function here
answers 501 `not_built` behind the route's real gate. `c5-agent-runs` replaces them, and
with them the rule item 14 fixes: in R1 only a platform key opens a run, so a tenant-bound
key calling `open_run` is refused with the reason named, and a tenant reads the library's
runs and nothing else.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def _not_built(detail: str) -> NoReturn:
    raise ProblemError(status=501, code="not_built", detail=detail)


def open_run() -> NoReturn:
    """`POST /agent-runs`. Built by `c5-agent-runs`."""
    _not_built("Opening an agent run is not built yet.")


def finish_run() -> NoReturn:
    """`PATCH /agent-runs/{runId}`. Built by `c5-agent-runs`."""
    _not_built("Closing an agent run is not built yet.")


def list_runs() -> NoReturn:
    """`GET /agent-runs`. Built by `c5-agent-runs`."""
    _not_built("Reading agent runs is not built yet.")
