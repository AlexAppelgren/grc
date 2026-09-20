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
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.shared import tenancy
from apps.shared.adapters import embedder
from apps.shared.audit import Actor, record

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
    change that arrived through the outbox, or the full rebuild a command asked for."""
    if not reason.strip():
        raise ValueError("index_write() needs a reason naming the rebuild that is running")
    token = _index_write_reason.set(reason)
    try:
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
# cursor (`apps/search/tasks.py`), and a chunk without one is still found by the keyword
# leg, so a fresh approval is searchable the moment it commits.
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
    """Fill the embeddings of every chunk that has none, in batches, and say how many.

    Runs in the worker, from the outbox event a rebuild emitted, with no tenant active —
    the chunks are the shared library's and no bank session may write them. A chunk is
    read for embedding exactly once, because the pass that reads it is the pass that fills
    it, so a replayed event embeds nothing and asks the model nothing.

    `EMBEDDER_PROVIDER=none` is not a failure: D-09 has no model contracted yet, and a
    deployed environment runs the keyword leg alone until one arrives. Failing here would
    spend the outbox row's attempts waiting for a key.
    """
    from apps.search.models import SearchChunk

    with tenancy.platform_zone():  # the chunks are the shared library's, as in _write()
        pending = SearchChunk.objects.filter(embedding__isnull=True)
        if not pending.exists():
            return 0  # a replayed event, or a rebuild that changed no text: the model is not asked
        adapter = embedder.get_embedder()
        if isinstance(adapter, embedder.NoEmbedder):
            logger.info("no embedding model is configured; the search index keeps its keyword leg only")
            return 0
        embedded = 0
        while True:
            batch = list(pending[: settings.SEARCH_EMBED_BATCH_SIZE])
            if not batch:
                return embedded
            vectors = adapter.embed([f"{chunk.title}\n\n{chunk.body}" for chunk in batch])
            moment = timezone.now()
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_model = adapter.name
                chunk.embedded_at = moment
            with index_write(f"embedding {len(batch)} chunk(s) a rebuild left"):
                SearchChunk.objects.bulk_update(batch, ["embedding", "embedding_model", "embedded_at"])
            embedded += len(batch)


def _write(read: Any) -> IndexCounts:
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


def _fields(chunk: Any) -> dict[str, Any]:
    return {name: getattr(chunk, name) for name in REBUILT_FIELDS}


def _differs(row: Any, chunk: Any) -> bool:
    return any(getattr(row, name) != getattr(chunk, name) for name in REBUILT_FIELDS)
