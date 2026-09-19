# ADR 0010 — Search indexes the library only in R1

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-10; revisited at R2)

## Context

Embedding tenant text means sending it to a model endpoint, which D-07 does
not yet allow. The R1 questions (SRC-01 to SRC-03, J-7) are answered from
the library: instruments, provisions, obligations, versions and changes.

## Decision

Only library records are chunked, embedded and indexed in R1. Tenant
content (assessments, notes, comments, evidence) is not indexed and not
embedded. "As of" filtering works because chunks copy validity dates.
Deliberately not done: a tenant index behind a flag, because a flag that
sends tenant text to a model is the invariant weakened by configuration.

## Consequences

Easier: the D-07 data-flow statement holds without exceptions in search.
Harder: a search for one's own assessment text returns nothing in R1
(SRC-S11), which the empty state states plainly. To remember: at R2, once an
EU-pinned path exists, tenant indexing is a new ADR that supersedes this one.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Library chunks, hybrid query, Ask | Chunk 7 |
| 2 | Decide on tenant indexing | R2, after D-07 |
