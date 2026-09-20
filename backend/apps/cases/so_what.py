"""This bank's own "So what?" on a case (WAT-05).

The contract is declared ahead of the logic (chunk 5 plan rule 1), so each function here
answers 501 `not_built` behind the route's real gate. `c5-cases-so-what-and-links` builds
them: the library's draft is copied into each bank's case, and a person with `cases.work`
confirms the wording or rewrites it, which marks the copy as that bank's own.

Tenant zone only. Nothing here reads or writes a library row, and the text a bank saves
never leaves its tenant: not to another bank, not to a log and not to a model endpoint
(NFR-01, NFR-04, D-07).
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def _not_built(detail: str) -> NoReturn:
    raise ProblemError(status=501, code="not_built", detail=detail)


def save_so_what() -> NoReturn:
    """`PUT /changes/{changeId}/so-what`. Built by `c5-cases-so-what-and-links`."""
    _not_built("Saving your own wording is not built yet.")


def confirm_so_what() -> NoReturn:
    """`POST /changes/{changeId}/so-what/confirm`. Built by `c5-cases-so-what-and-links`."""
    _not_built("Confirming the wording is not built yet.")
