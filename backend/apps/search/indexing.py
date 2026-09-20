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

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from django.db import models

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
