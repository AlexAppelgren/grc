"""The search app's entry in the outbox cursor's dispatch table, and the sweep beside it
(SRC-01, ruling 9).

Embedding is the one part of indexing that talks to a model, so it never happens inside
the transaction that wrote the chunks: an approval would hold its row locks for a network
round trip and miss its 250 ms budget, and a model that is slow or down would take the
library write with it. The chunks land first and are searchable by their words; the
vectors follow.

They follow through the one relay there is. `record()` wrote an outbox row in the
transaction of the library write, `apps/shared/outbox.py` delivers it in order and exactly
once, and `embed_rebuilt_chunks` fills one batch of whatever embeddings the index owes.
There is no `transaction.on_commit` hand-off and no Celery relay of our own, so a rebuild
that rolls back asks for nothing and a delivery that fails is retried by the cursor with
the rest.

**One batch per delivery, and a sweep for the rest.** A delivery runs inside the cursor's
transaction, which holds the lock on the single cursor row, so a full-corpus rebuild that
embedded its whole backlog there would make model call after model call with every other
consumer's rows — every bank's case creation among them — waiting behind it (playbook 6:
fan out, never chain). `embed_search_backlog` is the beat entry that drains the rest on
its own clock, holding nothing anyone waits on. It is also the only thing that notices two
backlogs the cursor cannot: a rebuild whose outbox row spent its attempts and was left
failed, and a deployment that ran with `EMBEDDER_PROVIDER=none` until a model was
contracted, where the change is a variable and there is no library write to emit an event.

**No tenant active.** Both topics below are library events, recorded with no tenant, so
the cursor delivers them in the shared zone — which is the only zone that may write a
chunk (`owner_tenant_id IS NULL`). Neither the handler nor the sweep activates one; the
sweep reaches the chunks through `tenancy.platform_zone()` inside `indexing.py`, as every
other write of the index does.

The handler is idempotent because the work is: the embedding passes fill chunks that have
none, so a replayed event finds none and asks the model nothing.

**A registered change reaches the index through the same cursor** (WAT-01, AGT-02). The
watch writers are not hooked: `index_change` consumes the events they already record —
a registration, a merge and a correction of the facts — and rebuilds that change's chunks,
so a correction or a withdrawal moves the index with it. It embeds nothing itself. The
first of those events also opens every bank's case (`apps/cases/creation.py`), and both
handlers share the row's savepoint, so a model that is down must never hold that back;
the chunks are found by their words at once and the sweep below gives them vectors within
`SEARCH_EMBED_SWEEP_INTERVAL_S`. Only shared changes are indexed in R1 (D-10, owner items
4 and 10): an event recorded in a bank's zone is skipped before anything is read, with no
chunk written and no model asked.

**Registration is `SearchConfig.ready()`'s, never this module's import.** Nothing imports
a `tasks` module in a running API process — only Celery's autodiscovery does, in the
worker — so a handler registered at import time is absent exactly where the write that
needs it happens. `apps/shared/tests_outbox.py` refuses a `register_handler` call at any
module's top level.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.search import indexing
from apps.shared import outbox
from apps.shared.models import OutboxEvent
from apps.watch import curation, registration

logger = logging.getLogger(__name__)

# The outbox topics that mean the index moved and owes embeddings. `obligation.version_applied`
# is the approval's own row (`apps/proposals/apply.py`), which the rebuild rides rather
# than writing a second audit row an approval could not attribute to the reviewer's
# passkey; `search.index_rebuilt` is the full rebuild's own.
OBLIGATION_VERSION_APPLIED = "obligation.version_applied"
INDEX_TOPICS = (OBLIGATION_VERSION_APPLIED, indexing.INDEX_REBUILT)
# The watch events that change what a registered change's chunks say.
CHANGE_TOPICS = (registration.REGISTERED, registration.UPDATED, curation.FACTS_UPDATED)


def register() -> None:
    """Put the handlers on the one cursor: the embedding pass for the index's own topics
    and the change rebuild for the watch's.

    Called from `SearchConfig.ready()`, which is where a consumer registers (the cursor's
    own rule, and what `apps/cases/apps.py` does). Safe to call twice: `register_handler`
    counts the same function once.
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
        # Nothing a bank owns is indexed in R1. The watch records every change event with
        # no tenant, so this is a row that should not exist: say so and hold nothing up.
        logger.warning("a change event recorded in a bank's zone was not indexed", extra={"outboxEventId": str(event.id), "kind": event.topic})
        return
    change_id = event.audit_event.subject_id
    if change_id is None:
        return
    counts = indexing.reindex_change(change_id)
    logger.info("change chunks rebuilt", extra={"kind": event.topic, **counts.as_dict()})


@shared_task
def embed_search_backlog() -> None:
    """Fill whatever embeddings the index still owes, on beat's clock.

    A plain `@shared_task`, not a `@tenant_task`: a chunk belongs to no tenant. It takes no
    lock any request or any other consumer waits on, so it may run for as long as the
    backlog it found takes.
    """
    embedded = indexing.embed_backlog()
    if embedded:
        logger.info("search backlog embedded", extra={"chunks": embedded})
