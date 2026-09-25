"""Business logic of the search app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3)."""

from __future__ import annotations

import uuid

from apps.search import indexing


def reindex(obligation_id: uuid.UUID) -> None:
    """Bring the search index back in line with `obligation_id` (SRC-01, INV-04).

    The hook the approval transaction calls (`apps/proposals/apply.py`), so the index
    moves with the library or not at all: a reader never searches text the library has
    already replaced, and a failure here leaves the version unwritten and the proposal
    waiting.

    The rebuild itself lives in `apps/search/indexing.py`, which is the only module that
    may write a chunk, and it returns counts this hook has no use for.
    """
    indexing.reindex(obligation_id)


def reindex_provision(provision_id: uuid.UUID) -> None:
    """The same hook for a provision's versions (SRC-01, INV-02): called from the approval
    transaction that applies a new provision or a new text of one."""
    indexing.reindex_provision(provision_id)
