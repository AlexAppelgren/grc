"""Business logic of the search app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3)."""

from __future__ import annotations

import uuid


def reindex(obligation_id: uuid.UUID) -> None:
    """Bring the search index back in line with `obligation_id` (SRC-01, INV-04).

    Called from the approval transaction that applies a new obligation version, so the
    index moves with the library or not at all: a reader never searches text the library
    has already replaced, and a failure here leaves the version unwritten and the proposal
    waiting.

    Chunk 7 builds the chunking and the embeddings this will drive. Until then the hook is
    the whole contract: where the re-index happens, and that it happens inside the
    transaction.
    """
