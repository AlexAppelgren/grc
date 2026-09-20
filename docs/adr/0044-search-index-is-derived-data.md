# ADR 0044 — The search index is derived data with its own write fence

**Date:** 2026-09-20 · **Status:** accepted (D-51, Alex 2026-09-19)

## Context

`schema.sql` labels `search_chunk` as a LIBRARY table. Making it a
`LibraryModel` would put a second writer behind the proposal door, because the
indexer writes chunks outside any proposal; allowlisting `search/indexing.py`
on the library fence would let that module write any library table and would
stop the fence watching it. A chunk is neither a sourced public fact nor
something anybody proposes: it is derived from a record that was already
approved and already audited.

## Decision

`SearchChunk` is a plain model, not a `LibraryModel`. It carries
`owner_tenant_id`, copied from the indexed record and always NULL in R1, and
forced row-level security in the agents 0001 shape: FOR SELECT on shared rows
or the session's tenant, FOR ALL within its own zone, so no bank session can
write or delete a shared chunk. A runtime fence, `index_write()`, covers save,
delete and queryset writes, and an AST guard allows `index_write(` and
`SearchChunk` writes only in `search/indexing.py`, which names no library
model. Library rows are read in `search/sources.py`, which makes no write call,
so the library fence is unchanged and keeps watching both modules. Only shared
rows are indexed until an ADR supersedes ADR 0010. Inside the approval
transaction `apply.py` writes the text and the tsvector, and the worker fills
embeddings from outbox events dispatched with no tenant active, so keyword
search works before an embedding lands. There is no audit row per chunk,
because the library write behind it is already audited; a full rebuild writes
one system row with counts only.

Deliberately not done: a `LibraryModel` with the indexer allowlisted, a plain
model with no fence, no owner column, and deciding a hit's visibility with a
join at query time.

## Consequences

Easier: the library fence keeps its short allowlist, and the index half of the
tenant-content risk closes structurally rather than by review. Harder: two
fences to understand instead of one, and a rebuild command that must run with
no tenant active. To remember: `tests_rls` OTHER_POLICIES gains the chunk
policy with its reason, and a planted breach must fail both the AST guard and
the runtime fence.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The model, migration, fence, guard and RLS tests | `c7-search-index` (a) |
| 2 | The `apply.py` hook, `sources.py` and the rebuild command | `c7-search-index` (b) |
