# ADR 0036 — A legal entity follows a standard through approved applicability

**Date:** 2026-09-19 · **Status:** accepted by default (D-42, PRD 0.3 REG-01, TEN-02; the owner confirms); amended by D-75: the "applies" is set by one person holding `applicability.approve` after a confirmation dialog, with one audit event and no four eyes or step-up, and there is no request table, so the scope row is created in the transaction of the write that sets it

## Context

PRD 0.2 already says standards are worked through applicability per legal
entity. Something has to record that a particular entity follows a particular
standard, and that fact decides which entities the conformance duty spans. A
second record — a standard term on the entity's licence row, say — could
disagree with applicability and would move a span-deciding fact out from behind
four eyes.

## Decision

The approved per-entity applicability of the standard's one conformance
obligation is the only record that an entity follows it: "applies" with a
reason such as "Certified" or "Required by contract", through the existing
request with four eyes and a step-up, keeping its history. The conformance
obligation carries no entity term, so it spans every legal entity, and an
entity's span leaves opt-in dimensions out (ADR 0030). The applicability
request gains a nullable scope row and the one-pending index covers it; the
scope row gains an applicability reason and a decision time. A scope row is
created, through `record()`, inside the transaction of the request that needs
it — reads never write. Removing a standard from the regulatory scope hides the
conformance obligation and its rows and deletes nothing.

## Consequences

Easier: one fact, one door, one history, and any regulation that spans several
entities needs the same per-entity request anyway. Harder: the register's
applicability path grows a nullable dimension that every query must respect.
To remember: the counted preview shows the conformance obligation as hidden
when a standard leaves the scope, so nobody thinks the data was deleted.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Per-entity applicability requests and the scope row's reason | Chunk 8 |
| 2 | Unit-level applicability on the same request | Chunk 8, with ADR 0035 |
