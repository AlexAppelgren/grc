# ADR 0009 — Embedding model and reranker chosen against the evaluation set

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-09; the owner supplies a key for the first candidate)

## Context

Search must cover `sv`, `da`, `nb`, `fi` and `en` (I18N-01, SRC-01). No
candidate covering all five at 1024 dimensions has been verified
(`Verification_Log.md`). pgvector's HNSW index supports `vector` up to 2,000
dimensions (verified earlier, 2026-09-18), so 1024 leaves room. pgvector
0.5.0 is the newest Python package on PyPI (verified 2026-09-19).

## Decision

An `embedder` adapter with a mock in tests, a fixed dimension of 1024, and
the real model chosen on evidence: `scripts/search_eval.py` runs the labelled
question set across candidates and the winner is recorded here. The reranker
is chosen the same way over the top 50. Deliberately not done: picking a
model by reputation, or storing vectors of more than one dimension.

## Consequences

Easier: the evaluation gate exists before the first real model, so a later
swap is a measured change. Harder: until a key arrives the test deploy
searches by keyword only. To remember: changing the model means re-embedding
every chunk (a worker job) and re-recording the baseline scores.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Adapter interface, mock, `search_eval.py` skeleton | Phase 0 |
| 2 | Evaluation set, candidates compared, winner recorded | Chunk 7 |
