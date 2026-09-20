"""The roadmap by quarter (HOM-03, FP-03).

One module owns the roadmap query, so no second one is ever written: `c6-roadmap-backend`
fills `roadmap_items()` and `coming_up()`, and `home/logic.py` calls `coming_up()` for
Today rather than asking the same question a second way (chunk 6 ruling 5). The contract is
declared ahead of the logic (chunk 6 plan rule 3), so both answer 501 `not_built` behind the
route's real gate until then.

A read module: nothing here writes. What it will read is two zones at once — the library's
dated changes beside this bank's own cases — under row-level security with the caller's
tenant activated, and the quarter key is computed in the bank's own time zone so a date near
a quarter boundary lands where the bank reads it.
"""

from __future__ import annotations

from typing import NoReturn

from apps.home.logic import not_built


def roadmap_items() -> NoReturn:
    """`GET /roadmap`. Built by `c6-roadmap-backend`."""
    not_built("The roadmap is not built yet.")


def coming_up() -> NoReturn:
    """The first roadmap items and the count behind them, for Today's "Coming up" panel.
    Built by `c6-roadmap-backend` and called by `home/logic.py`."""
    not_built("The roadmap is not built yet.")
