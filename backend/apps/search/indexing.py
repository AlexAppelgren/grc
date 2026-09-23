"""The one door into the search index (SRC-01, H7, owner item 4).

A search chunk is **derived data**: every word in it was copied from a library record that
a proposal already put there, and the index is rebuilt from the library rather than
edited. It is therefore not a `LibraryModel` — a chunk is not a fact anyone proposes —
and the library's own fence (`apps/shared/tenancy.py`, `library_write()`) is untouched by
it. What keeps a chunk honest instead is this module: `index_write()` is the only context
in which a `SearchChunk` may be saved, updated or deleted, and the AST guard in
`apps/search/tests_index_fence.py` refuses a `SearchChunk` write written anywhere but
here, the way the library fence refuses a library write outside `proposals/apply.py`.

Two fences, two reasons. The library fence keeps a fact out of the library until two
independent principals agreed to it. This one keeps the index a faithful copy of the
library: a chunk written by hand would answer a bank's search with something no proposal
ever approved, and nothing downstream could tell the difference.

`apps/search/models.py` imports `assert_index_write` from here, so nothing in this module
may import that model at the top level. `c7-search-index-apply` adds the rebuild functions
here and takes `SearchChunk` through a deferred import for the same reason.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.shared import tenancy
from apps.shared.adapters import embedder
from apps.shared.audit import Actor, record

if TYPE_CHECKING:
    # Types only. `apps/search/models.py` imports `assert_index_write` from this module and
    # `apps/search/sources.py` reads that model, so importing either at runtime here would
    # close the circle; every function below takes its own deferred import instead.
    from apps.search.models import SearchChunk
    from apps.search.sources import ChunkSource, RecordChunks

logger = logging.getLogger(__name__)

# Every rebuild is the system's act: it copies what a proposal already approved, and the
# person behind it is named on the library write the rebuild followed.
INDEX_ACTOR = Actor.system("search_index")

_index_write_reason: ContextVar[str | None] = ContextVar("index_write_reason", default=None)


class IndexWriteRefused(RuntimeError):
    """A search chunk was written outside index_write() (SRC-01, H7)."""


@contextmanager
def index_write(reason: str) -> Iterator[None]:
    """The only context in which a SearchChunk may be saved, updated or deleted. `reason`
    names the rebuild that is running: the approval that reindexed one obligation, the
    change that arrived through the outbox, or the full rebuild a command asked for.

    It also opens the index door in the database (H16, ADR 0058), which reaches
    `search_chunk` and no library table, and puts back the door it found — the approval's
    own, when a rebuild runs inside one."""
    if not reason.strip():
        raise ValueError("index_write() needs a reason naming the rebuild that is running")
    token = _index_write_reason.set(reason)
    try:
        with tenancy.library_door("index"):
            yield
    finally:
        _index_write_reason.reset(token)


def assert_index_write(model_name: str) -> None:
    if _index_write_reason.get() is None:
        raise IndexWriteRefused(
            f"{model_name} is derived data. The index is rebuilt from the library inside "
            "index_write(), from apps/search/indexing.py, and is never written by hand (SRC-01, H7)."
        )


class SearchChunkQuerySet(models.QuerySet):
    """The queryset half of the fence: a bulk write is a write (the library fence learned
    this the same way)."""

    def update(self, **kwargs: Any) -> int:  # compliance: allow-kwargs Django QuerySet signature
        assert_index_write(self.model.__name__)
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        assert_index_write(self.model.__name__)
        return super().delete()

    def bulk_create(self, objs: Any, *args: Any, **kwargs: Any) -> Any:  # compliance: allow-kwargs Django QuerySet signature
        assert_index_write(self.model.__name__)
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs: Any, fields: Any, *args: Any, **kwargs: Any) -> Any:  # compliance: allow-kwargs Django QuerySet signature
        assert_index_write(self.model.__name__)
        return super().bulk_update(objs, fields, *args, **kwargs)


# ---------------------------------------------------------------------------------------
# The rebuild (SRC-01, SRC-02). The index is derived data, so this is the whole of how it
# is filled: read the library through `apps/search/sources.py`, compare, write what
# differs, and remove what the library no longer says.
#
# **Nothing embeds here.** A rebuild runs inside the caller's transaction — for an
# approval, inside the transaction that files the version — and a model call inside a
# write transaction would hold a row lock for a network round trip and take the approval
# past its 250 ms budget (NFR-02). The embeddings are filled out of band by the one outbox
# cursor and the beat sweep beside it (`apps/search/tasks.py`), and a chunk without one is
# still found by the keyword leg, so a fresh approval is searchable the moment it commits.
#
# **No audit row per rebuild inside an approval.** `reindex()` writes none: the library
# write behind it is already audited, and every audit row an approval writes carries the
# reviewer's passkey assertion (`apps/proposals/tests_apply.py`), which a derived rebuild
# has no way to name. A full rebuild has no library write in front of it, so
# `reindex_all()` writes the one system row with its counts, and it is that row's outbox
# event that asks for the embeddings.
# ---------------------------------------------------------------------------------------
INDEX_REBUILT = "search.index_rebuilt"
# The columns a rebuild owns. `embedding` is not one of them: it is the worker's, and it
# is cleared only when the text it was made from changed.
REBUILT_FIELDS = ("title", "body", "hierarchy_path", "valid_from", "valid_to", "metadata")


@dataclass(frozen=True)
class IndexCounts:
    """What one rebuild did, for the audit row and for the command's report. Counts only:
    a chunk's text is a library record and never travels on an event (playbook 4.7)."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0

    def __add__(self, other: IndexCounts) -> IndexCounts:
        return IndexCounts(
            created=self.created + other.created,
            updated=self.updated + other.updated,
            unchanged=self.unchanged + other.unchanged,
            deleted=self.deleted + other.deleted,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "deleted": self.deleted,
        }


def reindex(obligation_id: uuid.UUID) -> IndexCounts:
    """Bring obligation `obligation_id`'s chunks back in line with the library (SRC-01).

    Called from the approval transaction that applies a new obligation version, so the
    index moves with the library or not at all: a reader never searches text the library
    has already replaced, and a failure here leaves the version unwritten and the proposal
    waiting.
    """
    from apps.search import sources

    return _write(sources.obligation_chunks(obligation_id))


def reindex_provision(provision_id: uuid.UUID) -> IndexCounts:
    """The same for one provision's versions, for the seed and the full rebuild."""
    from apps.search import sources

    return _write(sources.provision_chunks(provision_id))


def reindex_all() -> IndexCounts:
    """Rebuild the whole corpus and ask for the embeddings it now owes (SRC-01).

    One audit row with counts, never one per chunk: the library writes behind the chunks
    are audited already, and a row per chunk would bury them. The outbox event that row
    carries is what the worker embeds from.
    """
    from apps.search import sources

    counts = IndexCounts()
    for obligation_id in sources.obligation_ids():
        counts += reindex(obligation_id)
    for provision_id in sources.provision_ids():
        counts += reindex_provision(provision_id)
    record(
        action=INDEX_REBUILT,
        actor=INDEX_ACTOR,
        subject_type="search_index",
        subject_id=None,
        subject_title="The search index",
        summary=(
            f"Rebuilt the search index from the library: {counts.created} written, "
            f"{counts.updated} rewritten, {counts.unchanged} unchanged, {counts.deleted} removed."
        ),
        tenant_id=None,
        after=counts.as_dict(),
    )
    return counts


def embed_pending() -> int:
    """Fill at most one batch of the embeddings the index owes, and say how many.

    The outbox delivery's share. It runs inside `deliver_batch()`'s transaction, which
    holds `SELECT ... FOR UPDATE` on the single cursor row, so it embeds
    `SEARCH_EMBED_BATCH_SIZE` chunks and stops: a full-corpus rebuild that embedded its
    whole backlog here would make one model call after another with every other
    consumer's rows — every bank's case creation among them — waiting behind the lock
    (playbook 6: fan out, never chain). What is left over is drained by
    `embed_backlog()`, which holds nothing anyone waits on.

    An approval's own chunks are a handful, so in the ordinary case this is the one call
    that fills them and the vectors still follow the commit within seconds.

    The backlog is read before the model is: a replayed event, or a rebuild that changed
    no text, finds nothing owing and asks for no adapter at all.
    """
    ids = _unembedded_ids(settings.SEARCH_EMBED_BATCH_SIZE)
    adapter = _contracted_model() if ids else None
    if adapter is None:
        return 0
    return _embed(adapter, ids)


def embed_backlog() -> int:
    """Fill every chunk that still owes a vector, a batch and a transaction at a time.

    The beat sweep's share (`apps/search/tasks.py`), and the only thing that closes the
    two gaps a delivery cannot:

    - a rebuild whose outbox row spent its `OUTBOX_MAX_ATTEMPTS` is left failed and the
      cursor moves past it, so nothing would ever ask for those embeddings again;
    - a deployment running with `EMBEDDER_PROVIDER=none` (D-09) embeds nothing, and
      contracting a model later is a variable change with no library write behind it, so
      there is no event for the corpus to ride.

    The sweep looks at the chunks rather than at the events, so both are simply the
    backlog it finds on its next tick. The ids are read once and walked, never re-queried
    in a loop: what a sweep that started owes is a fixed list, and a chunk written after
    it started belongs to the next tick.
    """
    with transaction.atomic():
        ids = _unembedded_ids(None)
    adapter = _contracted_model() if ids else None
    if adapter is None:
        return 0
    size = settings.SEARCH_EMBED_BATCH_SIZE
    embedded = 0
    for start in range(0, len(ids), size):
        with transaction.atomic():
            embedded += _embed(adapter, ids[start : start + size])
    return embedded


def _contracted_model() -> embedder.EmbedderAdapter | None:
    """The embedding model, or None while no model is contracted.

    `EMBEDDER_PROVIDER=none` is not a failure: D-09 has chosen no model yet and a deployed
    environment runs the keyword leg alone until one arrives. Raising here would spend the
    outbox row's attempts waiting for a key.
    """
    adapter = embedder.get_embedder()
    if isinstance(adapter, embedder.NoEmbedder):
        logger.info("no embedding model is configured; the search index keeps its keyword leg only")
        return None
    return adapter


def _unembedded_ids(limit: int | None) -> list[uuid.UUID]:
    """The chunks still owing a vector, at most `limit` of them, in the shared zone where
    every chunk is. Ids and not rows: the text is read again under the lock in `_embed()`,
    by which time another worker may have filled some of them."""
    from apps.search.models import SearchChunk

    with tenancy.platform_zone():
        ids = SearchChunk.objects.filter(embedding__isnull=True).values_list("id", flat=True)
        return list(ids if limit is None else ids[:limit])


def _embed(adapter: embedder.EmbedderAdapter, ids: list[uuid.UUID]) -> int:
    """One model call for these chunks and one write of what came back.

    The rows are locked with `SKIP LOCKED` and re-read under the lock, so a delivery and a
    sweep running at the same moment divide the backlog between them instead of both
    paying the provider for the same chunks and then waiting on each other's row locks to
    write the same answer twice.
    """
    from apps.search.models import SearchChunk

    if not ids:
        return 0
    with tenancy.platform_zone():
        batch = list(
            SearchChunk.objects.filter(id__in=ids, embedding__isnull=True).select_for_update(skip_locked=True)
        )
        if not batch:
            return 0
        vectors = adapter.embed([f"{chunk.title}\n\n{chunk.body}" for chunk in batch])
        moment = timezone.now()
        for chunk, vector in zip(batch, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedding_model = adapter.name
            chunk.embedded_at = moment
        with index_write(f"embedding {len(batch)} chunk(s) a rebuild left"):
            SearchChunk.objects.bulk_update(batch, ["embedding", "embedding_model", "embedded_at"])
    return len(batch)


def _write(read: RecordChunks) -> IndexCounts:
    """Make the chunks of one record say what `read` says, and remove what it does not.

    In the shared zone, always. Every chunk in R1 belongs to no tenant, and since the write
    rules were split (H15) a session inside a bank's zone can write only that zone: it
    would read the shared chunks through the `FOR SELECT` policy and then write none of
    them. `index_write()` is this ledger's one door, as `record()` is the audit trail's, so
    the zone is stepped out of here and put back straight away, and nothing a bank owns can
    ride in with it — `sources.py` skips an owned record before a chunk is ever built.
    """
    from apps.search.models import SearchChunk

    wanted = {(chunk.source_id, chunk.language): chunk for chunk in read.chunks}
    created = updated = unchanged = 0
    with tenancy.platform_zone():
        existing = {
            (row.source_id, row.language_id): row
            for row in SearchChunk.objects.filter(source_type=read.source_type, source_id__in=read.source_ids)
        }
        stale = [row.id for key, row in existing.items() if key not in wanted]
        with index_write(f"rebuilding {read.source_type} chunks from the library"):
            for key, chunk in wanted.items():
                row = existing.get(key)
                if row is None:
                    SearchChunk(
                        source_type=read.source_type,
                        source_id=chunk.source_id,
                        language_id=chunk.language,
                        **_fields(chunk),
                    ).save()
                    created += 1
                elif _differs(row, chunk):
                    for name, value in _fields(chunk).items():
                        setattr(row, name, value)
                    # The vector was made from text this chunk no longer holds, so it goes
                    # with it and the worker fills a fresh one from the outbox event.
                    row.embedding, row.embedding_model, row.embedding_version, row.embedded_at = None, "", "", None
                    row.save()
                    updated += 1
                else:
                    unchanged += 1
            if stale:
                SearchChunk.objects.filter(id__in=stale).delete()
    return IndexCounts(created=created, updated=updated, unchanged=unchanged, deleted=len(stale))


def _fields(chunk: ChunkSource) -> dict[str, Any]:
    return {name: getattr(chunk, name) for name in REBUILT_FIELDS}


def _differs(row: SearchChunk, chunk: ChunkSource) -> bool:
    return any(getattr(row, name) != getattr(chunk, name) for name in REBUILT_FIELDS)
