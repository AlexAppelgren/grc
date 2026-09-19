# ADR 0026 — Markets are the regulatory scope's jurisdictions plus a watch list

**Date:** 2026-09-19 · **Status:** accepted by default (D-27 to D-33, PRD 0.3 FP-04; the owner confirms)

## Context

Alex asked for the markets the bank operates in, marked as where it pays extra
attention, for research to keep sweeping broadly, and for aspiring markets that
agents watch. The `jurisdiction` dimension already restricts the regulatory
scope and has no terms, so today it restricts nothing; `Jurisdiction.parent`
exists and only the reference read uses it. Matching is flat, so a scope naming
only Sweden would hide every EU-level record. The access log prints the full
request line and error reports keep the request URL, so a tenant fact in a path
leaks. Nothing here needs a person to see something they cannot see today.

## Decision

Operating markets are the regulatory scope's jurisdiction terms, changed only
through the FP-02 request with its preview, second person and step-up. Watched
markets are a separate tenant list on the same screen, written directly under
`footprint.request` and audited, hiding nothing. A market's level is computed,
operating first, so scope approval never writes a watch row. Jurisdiction terms
mirror the jurisdiction rows and cannot be proposed or tagged; a record's
jurisdiction is derived at match time from its instrument or its authority, and
`Jurisdiction.parent` means "the jurisdiction whose rules reach this one", with
Norway pointing at the EU under the EEA Agreement. The International
jurisdiction of ADR 0032 derives nothing and is not mirrored. Only the
jurisdictions the platform covers can be chosen, and only countries watched. A
market key travels in a request body, never in a path or query string.

Deliberately not done: a separate Markets screen, one table holding both
levels, a `rules_reach_from` column, a hook in scope approval, an extra
argument on the SQL matching function, and markets beyond EU, SE, DK, NO and FI.

## Consequences

Easier: each fact is stored once; four eyes stays on everything that hides
records; a bank operating only in Norway still sees EU law; the SQL function
and every footprint validation stay as built. Harder: the derivation lives
inside chunk 3's single scope rule, so that rule must land before any list
surface applies the scope, and a pending scope request blocks operating-market
edits. To remember: watching does little until the chunk 3 inventory view, the
chunk 5 feed view and chunk 11 agent scope exist, so screen copy must stay true
slice by slice; the watch list is sensitive and reaches every member, the audit
rows, the outbox and, from chunk 11, the runner.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Norway's reach, mirrored jurisdiction terms, the proposal and tagging refusal | Now, before chunk 3's list routes |
| 2 | Derived jurisdiction inside chunk 3's scope rule | Chunk 3, with that rule's first version |
| 3 | Watched markets: model, logic, routes, panel, seeds, isolation tests | Now (R1) |
| 4 | The watched-market view on the inventory and the feed | Chunks 3 and 5 |
| 5 | Tenant agents' default scope from the markets | Chunk 11 |
