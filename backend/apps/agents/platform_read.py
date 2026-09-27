"""What bleqq watches, as any member of a bank reads it (AGT-03, ruling 6): each platform
agent's name, purpose, jurisdictions, cadence, next run and how its last run ended, and
nothing else. Answers 501 `not_built` until `c11-platform-watch-read` fills it."""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def list_platform_watch(*, limit: int, offset: int) -> NoReturn:
    """`GET /agents/platform`. Built by `c11-platform-watch-read`."""
    raise ProblemError(status=501, code="not_built", detail="What bleqq watches is not built yet.")
