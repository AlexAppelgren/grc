"""A person's own comments and mentions for My work's "Comments and mentions" panel (COL-01,
HOM-05), filtered by each record's read permission.

The contract is declared ahead of the logic (CHUNK10_TASKS rule 3), so the function here
answers 501 `not_built` behind the route's real gate until `f03-T80a` fills it. The route
has already refused a caller without a member session in a bank.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def list_my_comments() -> NoReturn:
    """`GET /me/comments`. Built by `f03-T80a`."""
    raise ProblemError(status=501, code="not_built", detail="Your comments and mentions are not built yet.")
