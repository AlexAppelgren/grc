# ADR 0031 — An optional instrument level kind says an instrument is a standard

**Date:** 2026-09-19 · **Status:** accepted by default (D-37, PRD 0.3 INV-01, INV-08; the owner confirms)

## Context

The five seeded instrument levels carry no kind, and the pills are decided by
`binding`. A standard is not binding, so it would render "Guidance, comply or
explain", which is wrong and misleading. The API contract already carries
`{key, kind, label}` for a level, and the vocabulary registry already supports
an optional kind.

## Decision

Add an optional tier-1 instrument level kind whose only value is `standard`,
with the registry entry marking the kind not required, and one level row with
`binding_default` false. The five existing levels keep a null kind and their
pills keep following `binding`. When the binding level's kind is `standard`,
the header's binding slot and the row's guidance slot both read "Standard" in
the `information` tone. No relabel guard is needed, because a relabel payload
carries no kind.

Deliberately not done: `law` and `guidance` kind values. They would have no
reader and would be a second source beside `binding_default` that could
disagree with it.

## Consequences

Easier: the change is additive, needs no contract change, and can land before
or after the chunk 3 reads. Harder: one more branch in the binding presentation
function, which its unit tests must cover for a null kind with binding true, a
null kind with binding false, and `standard`. To remember: the pill wording and
tone need a design card before the screen ships.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The kind, the registry entry, the level row and the provision trigger | Chunk 3 |
| 2 | The binding pill and the licensed-text empty state | Chunk 3 screens |
