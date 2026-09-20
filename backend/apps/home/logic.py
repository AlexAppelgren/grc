"""Business logic of the home app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3).

Today is the one screen that must not chain: `home_today()` fans out the reads it needs and
answers them in one object (HOM-01, playbook 10). The contract is declared ahead of the
logic (chunk 6 plan rule 3), so the function here answers 501 `not_built` behind the route's
real gate until `c6-home-backend` fills it.

A read module: nothing here writes, so no `record()` call belongs in it. What it will read
is two zones at once — the library's changes beside this bank's own cases and roadmap — and
the tenant half is read under row-level security with the caller's tenant activated, never
by filtering in Python.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def not_built(detail: str) -> NoReturn:
    """The one 501 the home app answers while a route is declared ahead of its logic. RFC
    9457 like every other refusal, with `not_built` as the code a caller branches on."""
    raise ProblemError(status=501, code="not_built", detail=detail)


def home_today() -> NoReturn:
    """`GET /home`. Built by `c6-home-backend`."""
    not_built("The timeline home is not built yet.")
