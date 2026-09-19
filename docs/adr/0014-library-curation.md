# ADR 0014 — Library curation by a platform role in the console

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-14; the owner names the first library editors)

## Context

The library is shared by every tenant. The prototype shows the tenant's
compliance officer approving agent proposals into the inventory, which would
let one bank change facts every bank reads. `design/README.md` and
`INPUT_DELTAS.md` §5 record this as the one place the prototype is wrong.

## Decision

The proposal queue lives in the platform console and is reviewed by the
platform role `library_editor` (`proposals.review`, `library_vocab.manage`,
`sources.manage`, `eval.manage`). Tenants see library updates, report
problems ("This looks wrong") and may propose. Four eyes applies: the
proposer never approves. Deliberately not done: a per-tenant fork of library
records (tenant-private records are a separate mechanism with
`owner_tenant_id`, INV-07).

## Consequences

Easier: one curated library, one audit trail for facts. Harder: a tenant
cannot fix a library error itself; the problem report to proposal loop
(AUD-03) has to be fast. To remember: the console needs screens the
prototype lacks (`design/README.md`), designed as cards first.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Platform roles seeded, console shell | Chunk 1 |
| 2 | Queue, review screen, library updates, problem reports | Chunk 4 |
