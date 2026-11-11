"""The one door into the search index (SRC-01, H7).

A search chunk is derived data copied from library records a proposal already approved, so
it is not a `LibraryModel`. `index_write()` is the only context in which a `SearchChunk` may
be written; `tests_index_fence.py` refuses a write anywhere else. The library fence keeps a
fact out until two principals agreed; this one keeps the index a faithful copy, so no search
answers with something no proposal approved.

`apps/search/models.py` imports `assert_index_write` from here, so this module imports that
model only inside its functions.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Collection, Iterator
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
    # Types only: a runtime import would close the circle with models.py and sources.py.
    from apps.search.models import SearchChunk
    from apps.search.sources import ChunkSource, RecordChunks

logger = logging.getLogger(__name__)

# A rebuild copies what a proposal approved; the person is named on that library write.
INDEX_ACTOR = Actor.system("search_index")

_index_write_reason: ContextVar[str | None] = ContextVar("index_write_reason", default=None)


class IndexWriteRefused(RuntimeError):
    """A search chunk was written outside index_write() (SRC-01, H7)."""


@contextmanager
def index_write(reason: str) -> Iterator[None]:
    """The only context in which a SearchChunk may be saved, updated or deleted. `reason`
    names the rebuild. It also opens the index door in the database (H16, ADR 0058), which
    reaches `search_chunk` and no library table, and restores the door it found."""
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
    """The queryset half of the fence: a bulk write is a write."""

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


# --- The rebuild (SRC-01, SRC-02) ---
# Read the library through `sources.py`, write what differs, remove what it no longer says.
# Nothing embeds here: a rebuild runs inside the caller's (often an approval's) transaction,
# and a model call there would hold row locks for a round trip (NFR-02); the outbox cursor
# and the beat sweep (`tasks.py`) fill embeddings, and the keyword leg finds a chunk
# meanwhile. No audit row inside an approval (its library write is audited with the passkey
# assertion); `reindex_all()` writes one system row whose outbox event asks for embeddings.
INDEX_REBUILT = "search.index_rebuilt"
# The columns a rebuild owns. `embedding` is the worker's, cleared only when its text changed.
REBUILT_FIELDS = ("title", "body", "hierarchy_path", "valid_from", "valid_to", "metadata")
# What a rebuild clears when a chunk's text changed.
EMBEDDING_FIELDS = ("embedding", "embedding_model", "embedding_version", "embedded_at")


@dataclass(frozen=True)
class IndexCounts:
    """What one rebuild did, as counts only: a chunk's text never travels on an event
    (playbook 4.7)."""

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
    """Bring obligation `obligation_id`'s chunks back in line with the library (SRC-01),
    inside the approval transaction, so the index moves with the library or not at all.
    """
    from apps.search import sources

    return _write(sources.obligation_chunks(obligation_id))


def reindex_obligations(obligation_ids: Collection[uuid.UUID]) -> IndexCounts:
    """The same for many obligations at once, in one rebuild: the approval of a batch that
    re-tags them (PRO-04) opens the index door once, not once per obligation."""
    from apps.search import sources

    return _write(sources.obligations_chunks(obligation_ids))


def reindex_provision(provision_id: uuid.UUID) -> IndexCounts:
    """The same for one provision's versions, for the seed and the full rebuild."""
    from apps.search import sources

    return _write(sources.provision_chunks(provision_id))


def reindex_change(change_id: uuid.UUID) -> IndexCounts:
    """The same for one registered change, from the outbox handler in `tasks.py` and the
    full rebuild. A withdrawn or superseded change loses its chunks here."""
    from apps.search import sources

    return _write(sources.change_chunks(change_id))


def reindex_all() -> IndexCounts:
    """Rebuild the whole corpus and ask for the embeddings it owes (SRC-01): one audit row
    with counts, whose outbox event the worker embeds from.
    """
    from apps.search import sources

    counts = IndexCounts()
    for obligation_id in sources.obligation_ids():
        counts += reindex(obligation_id)
    for provision_id in sources.provision_ids():
        counts += reindex_provision(provision_id)
    for change_id in sources.change_ids():
        counts += reindex_change(change_id)
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
    """Fill at most one batch of owed embeddings, and say how many.

    The outbox delivery's share, inside `deliver_batch()`'s transaction, which locks the
    cursor row: so at most `SEARCH_EMBED_BATCH_SIZE` chunks, never the whole backlog, or
    every other consumer would wait behind model calls (playbook 6). `embed_backlog()` drains
    the rest. Reads the backlog before the model, so a no-op asks for no adapter.
    """
    ids = _unembedded_ids(settings.SEARCH_EMBED_BATCH_SIZE)
    adapter = _contracted_model() if ids else None
    if adapter is None:
        return 0
    return _embed(adapter, ids)


def embed_backlog() -> int:
    """Fill every chunk still owing a vector, a batch and a transaction at a time: the beat
    sweep's share. It closes what a delivery cannot: a rebuild whose outbox row spent
    `OUTBOX_MAX_ATTEMPTS`, and a model contracted after a period of `EMBEDDER_PROVIDER=none`
    (D-09), with no event behind it. The ids are read once; later chunks are the next tick's.
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
    """The embedding model, or None while none is contracted (D-09): a keyword-only
    deployment is not a failure, and raising would spend outbox attempts waiting for a key.
    """
    adapter = embedder.get_embedder()
    if isinstance(adapter, embedder.NoEmbedder):
        logger.info("no embedding model is configured; the search index keeps its keyword leg only")
        return None
    return adapter


def _unembedded_ids(limit: int | None) -> list[uuid.UUID]:
    """Up to `limit` chunk ids still owing a vector; the text is re-read under the lock in
    `_embed()`. Shared chunks only, in the query as well as the policy (INV-07, D-57): a
    bank's own record never reaches a model."""
    from apps.search.models import SearchChunk

    with tenancy.platform_zone():
        ids = SearchChunk.objects.filter(embedding__isnull=True, owner_tenant__isnull=True).values_list("id", flat=True)
        return list(ids if limit is None else ids[:limit])


def _embed(adapter: embedder.EmbedderAdapter, ids: list[uuid.UUID]) -> int:
    """One model call for these chunks and one write of what came back. Rows are locked with
    `SKIP LOCKED` and re-read, so a delivery and a sweep split the backlog rather than pay
    twice for the same chunks.
    """
    from apps.search.models import SearchChunk

    if not ids:
        return 0
    with tenancy.platform_zone():
        batch = list(
            SearchChunk.objects.filter(id__in=ids, embedding__isnull=True, owner_tenant__isnull=True).select_for_update(
                skip_locked=True
            )
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
    """Make one record's chunks say what `read` says, and remove what it does not. Always in
    the shared zone: since H15 a bank session can write only its own zone, so the zone is
    stepped out of here and restored at once; `sources.py` skips owned records.
    """
    from apps.search.models import SearchChunk

    wanted = {(chunk.source_id, chunk.language): chunk for chunk in read.chunks}
    with tenancy.platform_zone():
        existing = {
            (row.source_id, row.language_id): row
            for row in SearchChunk.objects.filter(source_type=read.source_type, source_id__in=read.source_ids)
        }
        stale = [row.id for key, row in existing.items() if key not in wanted]
        new: list[SearchChunk] = []
        changed: list[SearchChunk] = []
        for key, chunk in wanted.items():
            row = existing.get(key)
            if row is None:
                new.append(SearchChunk(source_type=read.source_type, source_id=chunk.source_id, language_id=chunk.language, **_fields(chunk)))
            elif _differs(row, chunk):
                for name, value in _fields(chunk).items():
                    setattr(row, name, value)
                # The vector was made from text this chunk no longer holds; the worker refills it.
                row.embedding, row.embedding_model, row.embedding_version, row.embedded_at = None, "", "", None
                changed.append(row)
        # One statement per kind of write, however many chunks the rebuild touches.
        with index_write(f"rebuilding {read.source_type} chunks from the library"):
            if new:
                SearchChunk.objects.bulk_create(new)
            if changed:
                SearchChunk.objects.bulk_update(changed, [*REBUILT_FIELDS, *EMBEDDING_FIELDS])
            if stale:
                SearchChunk.objects.filter(id__in=stale).delete()
    return IndexCounts(created=len(new), updated=len(changed), unchanged=len(wanted) - len(new) - len(changed), deleted=len(stale))


def _fields(chunk: ChunkSource) -> dict[str, Any]:
    return {name: getattr(chunk, name) for name in REBUILT_FIELDS}


def _differs(row: SearchChunk, chunk: ChunkSource) -> bool:
    return any(getattr(row, name) != getattr(chunk, name) for name in REBUILT_FIELDS)
