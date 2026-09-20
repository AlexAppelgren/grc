"""Registering a detected change and the pages it was found on (WAT-02, AGT-07).

The contract is declared ahead of the logic (chunk 5 plan rule 1), so each function here
answers 501 `not_built` behind the route's real gate. `c5-watch-registration` replaces
them with the idempotent register on `stableKey`, the duplicate merge of AC-WAT1 and the
content screen whose hits land in `change_document.risk_flags`.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def _not_built(detail: str) -> NoReturn:
    raise ProblemError(status=501, code="not_built", detail=detail)


def register_change() -> NoReturn:
    """`POST /changes`. Built by `c5-watch-registration`."""
    _not_built("Registering a change is not built yet.")


def add_document() -> NoReturn:
    """`POST /changes/{changeId}/documents`. Built by `c5-watch-registration`."""
    _not_built("Attaching a document to a change is not built yet.")
