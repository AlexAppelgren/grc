"""The library facts a change carries: its type, flags, scope terms, timeline and the
obligations it affects (WAT-03, WAT-04).

The contract is declared ahead of the logic (chunk 5 plan rule 1), so each function here
answers 501 `not_built` behind the route's real gate. `c5-watch-curation` replaces them:
an agent's key writes a suggestion with a confidence and never confirms one, and the
library editor's confirmation itself is the held task `c5-watch-curation-confirm`.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def _not_built(detail: str) -> NoReturn:
    raise ProblemError(status=501, code="not_built", detail=detail)


def update_change_facts() -> NoReturn:
    """`PATCH /changes/{changeId}`. Built by `c5-watch-curation`."""
    _not_built("Correcting a change's facts is not built yet.")


def add_event() -> NoReturn:
    """`POST /changes/{changeId}/events`. Built by `c5-watch-curation`."""
    _not_built("Adding a milestone to a change is not built yet.")


def update_event() -> NoReturn:
    """`PATCH /changes/{changeId}/events/{eventId}`. Built by `c5-watch-curation`."""
    _not_built("Changing a milestone is not built yet.")


def set_obligation_links() -> NoReturn:
    """`PUT /changes/{changeId}/obligations`. Built by `c5-watch-curation`."""
    _not_built("Setting the obligations a change affects is not built yet.")
