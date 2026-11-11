"""The search app's outbox consumers and the embedding sweep (SRC-01).

Embedding never happens inside the transaction that wrote the chunks: an approval would hold
row locks for a network round trip, and a down model would take the library write with it.
Chunks land first, searchable by their words; vectors follow through the outbox row
`record()` wrote, delivered in order exactly once by `apps/shared/outbox.py`.

- One batch per delivery: a delivery holds the single cursor row's lock, so draining a
  whole backlog there would stall every other consumer (playbook 6). The beat entry
  `embed_search_backlog` drains the rest, and also catches a rebuild whose outbox row spent
  its attempts and a model contracted after `EMBEDDER_PROVIDER=none`.
- No tenant active: these are library events, delivered in the shared zone, the only zone
  that may write a chunk. Idempotent: a replay finds nothing owing.
- A registered change reaches the index on the same cursor (WAT-01, AGT-02): `index_change`
  rebuilds its chunks from the watch's own events and embeds nothing, so a down model never
  holds back case creation sharing the savepoint. An event recorded in a bank's zone is
  skipped (D-10).
- Handlers register in `SearchConfig.ready()`, never on import: only the worker imports
  `tasks`, and `tests_outbox.py` refuses a top-level `register_handler`.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.search import indexing
from apps.shared import outbox
from apps.shared.models import OutboxEvent
from apps.watch import curation, registration

logger = logging.getLogger(__name__)

# The topics that mean the index moved and owes embeddings: the approval's own
# `obligation.version_applied` row, which the rebuild rides, and the full rebuild's.
OBLIGATION_VERSION_APPLIED = "obligation.version_applied"
INDEX_TOPICS = (OBLIGATION_VERSION_APPLIED, indexing.INDEX_REBUILT)
# The watch events that change what a registered change's chunks say.
CHANGE_TOPICS = (registration.REGISTERED, registration.UPDATED, curation.FACTS_UPDATED)


def register() -> None:
    """Put the handlers on the one cursor: embedding for the index's topics, the change
    rebuild for the watch's. Called from `SearchConfig.ready()`; safe to call twice.
    """
    for topic in INDEX_TOPICS:
        outbox.register_handler(topic, embed_rebuilt_chunks)
    for topic in CHANGE_TOPICS:
        outbox.register_handler(topic, index_change)


def embed_rebuilt_chunks(event: OutboxEvent) -> None:
    """Fill one batch of the embeddings the library change behind `event` left owing."""
    embedded = indexing.embed_pending()
    if embedded:
        logger.info("search chunks embedded", extra={"chunks": embedded, "kind": event.topic})


def index_change(event: OutboxEvent) -> None:
    """Rebuild the chunks of the change `event` names, in the shared zone the cursor put
    it in. A replay rewrites nothing, because the rebuild compares before it writes."""
    if event.tenant_id is not None:
        # The watch records change events with no tenant, so this row should not exist.
        logger.warning("a change event recorded in a bank's zone was not indexed", extra={"outboxEventId": str(event.id), "kind": event.topic})
        return
    change_id = event.audit_event.subject_id
    if change_id is None:
        return
    indexing.reindex_change(change_id)


@shared_task
def embed_search_backlog() -> None:
    """Fill whatever embeddings the index still owes, on beat's clock. A plain
    `@shared_task`: a chunk belongs to no tenant, and nothing waits on its locks.
    """
    embedded = indexing.embed_backlog()
    if embedded:
        logger.info("search backlog embedded", extra={"chunks": embedded})
