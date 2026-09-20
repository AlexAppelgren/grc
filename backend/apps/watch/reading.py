"""The watch reads: the bank's feed, one change, an obligation's related changes and the
console's Change facts queue (WAT-02, WAT-03, WAT-04, CAS-01, FP-03, FP-04).

The contract is declared ahead of the logic (chunk 5 plan rule 1), so each function here
answers 501 `not_built` behind the route's real gate. `c5-watch-feed-read` builds the feed
and the console list, `c5-watch-change-reads` the change read and the obligation's related
changes.

A read module: nothing here writes, so it neither opens the watch door nor calls
`library_write()`. What it will join is two zones at once — the library's change beside
the reader's own case — and the tenant half is read under row-level security with the
caller's tenant activated, never by filtering in Python.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def _not_built(detail: str) -> NoReturn:
    raise ProblemError(status=501, code="not_built", detail=detail)


def list_changes() -> NoReturn:
    """`GET /changes`. Built by `c5-watch-feed-read`."""
    _not_built("The watch feed is not built yet.")


def list_console_changes() -> NoReturn:
    """`GET /console/changes`. Built by `c5-watch-feed-read`."""
    _not_built("The console's list of changes is not built yet.")


def get_change() -> NoReturn:
    """`GET /changes/{changeId}`. Built by `c5-watch-change-reads`."""
    _not_built("Reading one change is not built yet.")


def list_obligation_changes() -> NoReturn:
    """`GET /obligations/{obligationId}/changes`. Built by `c5-watch-change-reads`."""
    _not_built("An obligation's related changes are not built yet.")
