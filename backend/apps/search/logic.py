"""Business logic of the search app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3)."""

from __future__ import annotations

import uuid
from collections.abc import Collection

from apps.search import indexing


def reindex(obligation_id: uuid.UUID) -> None:
    """Bring the search index back in line with `obligation_id` (SRC-01, INV-04): the hook
    the approval transaction calls, so the index moves with the library or not at all. The
    rebuild lives in `indexing.py`, the only module that may write a chunk.
    """
    indexing.reindex(obligation_id)


def reindex_obligations(obligation_ids: Collection[uuid.UUID]) -> None:
    """The same hook for many obligations at once: the approval of a batch that re-tags
    them (PRO-04) rebuilds their chunks in one pass rather than one per obligation."""
    indexing.reindex_obligations(obligation_ids)


def reindex_provision(provision_id: uuid.UUID) -> None:
    """The same hook for a provision's versions (SRC-01, INV-02): called from the approval
    transaction that applies a new provision or a new text of one."""
    indexing.reindex_provision(provision_id)
