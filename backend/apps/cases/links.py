"""This bank's own decision about a suggested obligation link (WAT-04, ruling C).

The contract is declared ahead of the logic (chunk 5 plan rule 1), so each function here
answers 501 `not_built` behind the route's real gate. `c5-cases-so-what-and-links` builds
them.

A library editor confirms a link for the shared library; a compliance officer accepts or
removes it on the bank's own case. The two are separate facts and this module writes only
the second: `change_obligation` is never touched from here, which `apps/cases/tests_models.py`
proves (AC-PRO1).
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def _not_built(detail: str) -> NoReturn:
    raise ProblemError(status=501, code="not_built", detail=detail)


def accept_obligation_link() -> NoReturn:
    """`POST /changes/{changeId}/case/obligation-links`. Built by `c5-cases-so-what-and-links`."""
    _not_built("Confirming an obligation link on your case is not built yet.")


def remove_obligation_link() -> NoReturn:
    """`DELETE /changes/{changeId}/case/obligation-links/{obligationId}`. Built by
    `c5-cases-so-what-and-links`."""
    _not_built("Removing an obligation link from your case is not built yet.")
