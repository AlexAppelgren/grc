"""The search app's entry in the outbox cursor's dispatch table (SRC-01, ruling 9).

Embedding is the one part of indexing that talks to a model, so it never happens inside
the transaction that wrote the chunks: an approval would hold its row locks for a network
round trip and miss its 250 ms budget, and a model that is slow or down would take the
library write with it. The chunks land first and are searchable by their words; the
vectors follow.

They follow through the one relay there is. `record()` wrote an outbox row in the
transaction of the library write, `apps/shared/outbox.py` delivers it in order and exactly
once, and this handler fills whatever embeddings the index owes. There is no
`transaction.on_commit` hand-off and no Celery relay of our own, so a rebuild that rolls
back asks for nothing and a delivery that fails is retried by the cursor with the rest.

**No tenant active.** Both topics below are library events, recorded with no tenant, so
the cursor delivers them in the shared zone — which is the only zone that may write a
chunk (`owner_tenant_id IS NULL`). The handler activates nothing of its own.

The handler is idempotent because the work is: `embed_pending()` fills the chunks that
have no embedding, so a replayed event finds none and asks the model nothing.
"""

from __future__ import annotations

import logging

from apps.search import indexing
from apps.shared import outbox
from apps.shared.models import OutboxEvent

logger = logging.getLogger(__name__)

# The outbox topics that mean the index moved and owes embeddings. `obligation.version_applied`
# is the approval's own row (`apps/proposals/apply.py`), which the rebuild rides rather
# than writing a second audit row an approval could not attribute to the reviewer's
# passkey; `search.index_rebuilt` is the full rebuild's own.
OBLIGATION_VERSION_APPLIED = "obligation.version_applied"
INDEX_TOPICS = (OBLIGATION_VERSION_APPLIED, indexing.INDEX_REBUILT)


def embed_rebuilt_chunks(event: OutboxEvent) -> None:
    """Fill the embeddings the library change behind `event` left owing."""
    embedded = indexing.embed_pending()
    if embedded:
        logger.info("search chunks embedded", extra={"chunks": embedded, "kind": event.topic})


for _topic in INDEX_TOPICS:
    outbox.register_handler(_topic, embed_rebuilt_chunks)
