"""The source registry and the coverage log (WAT-01).

The contract is declared ahead of the logic (chunk 5 plan rule 1), so each function here
answers 501 `not_built` behind the route's real gate. `c5-watch-sources-coverage` replaces
them with the registry, the cadence, the check log and the stale rule
(`SOURCE_STALE_AFTER_CHECKS`).
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def _not_built(detail: str) -> NoReturn:
    raise ProblemError(status=501, code="not_built", detail=detail)


def list_sources() -> NoReturn:
    """`GET /sources`. Built by `c5-watch-sources-coverage`."""
    _not_built("The source registry is not built yet.")


def create_source() -> NoReturn:
    """`POST /sources`. Built by `c5-watch-sources-coverage`."""
    _not_built("Adding a source is not built yet.")


def update_source() -> NoReturn:
    """`PATCH /sources/{sourceId}`. Built by `c5-watch-sources-coverage`."""
    _not_built("Changing a source is not built yet.")


def source_coverage() -> NoReturn:
    """`GET /sources/coverage`. Built by `c5-watch-sources-coverage`."""
    _not_built("The coverage log is not built yet.")


def record_check() -> NoReturn:
    """`POST /agent-runs/{runId}/source-checks`. Built by `c5-watch-sources-coverage`."""
    _not_built("Logging a source check is not built yet.")
