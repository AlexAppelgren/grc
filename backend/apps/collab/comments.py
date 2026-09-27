"""Comments on one record of one bank (COL-01): read, written, edited and deleted by their
author, and never logged.

The contract is declared ahead of the logic (CHUNK10_TASKS rule 3), so each function here
answers 501 `not_built` behind the route's real gate until `c10-comments-api-a` fills it,
with the subject registry in `collab/subjects.py` deciding who may read which record. The
route has already refused a caller without a member session in a bank, and `comments.write`
where the call writes.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def list_comments() -> NoReturn:
    """`GET /comments`. Built by `c10-comments-api-a`."""
    raise ProblemError(status=501, code="not_built", detail="Reading comments is not built yet.")


def add_comment() -> NoReturn:
    """`POST /comments`. Built by `c10-comments-api-a`."""
    raise ProblemError(status=501, code="not_built", detail="Writing a comment is not built yet.")


def edit_comment() -> NoReturn:
    """`PATCH /comments/{commentId}`. Built by `c10-comments-api-a`."""
    raise ProblemError(status=501, code="not_built", detail="Editing a comment is not built yet.")


def delete_comment() -> NoReturn:
    """`DELETE /comments/{commentId}`. Built by `c10-comments-api-a`."""
    raise ProblemError(status=501, code="not_built", detail="Deleting a comment is not built yet.")
