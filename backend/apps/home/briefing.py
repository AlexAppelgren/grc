"""The weekly briefing, live and from the snapshot (HOM-02, WAT-05, FP-03).

The running week is computed live and stored nowhere; a past week is read back from the
`briefing` row and its append-only `briefing_item` ranks, so a later change to the feed can
never alter what a person was sent. The contract is declared ahead of the logic (chunk 6
plan rule 3), so both functions answer 501 `not_built` behind the route's real gate until
`c6-briefing-backend` fills them.

Reads only. The snapshot itself is written by the weekly `@tenant_task` in `home/tasks.py`,
in the transaction that sends the mail and through `record()`, never from a request.
"""

from __future__ import annotations

from typing import NoReturn

from apps.home.logic import not_built


def current_briefing() -> NoReturn:
    """`GET /briefings/current`. Built by `c6-briefing-backend`."""
    not_built("The weekly briefing is not built yet.")


def briefing_for_week() -> NoReturn:
    """`GET /briefings/{weekStart}`. Built by `c6-briefing-backend`."""
    not_built("Reading a past briefing is not built yet.")
