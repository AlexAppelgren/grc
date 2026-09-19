# ADR 0035 — The Statement of Applicability's units live in the tenant zone

**Date:** 2026-09-19 · **Status:** accepted by default (D-41, PRD 0.3 REG-08, AC-REG2; the owner confirms)

## Context

A bank's Statement of Applicability lists the clauses and controls it works
with. Those numbers and titles exist only in the paid standard, so they are not
sourced public facts and cannot sit in the shared library (ADR 0029); the
library-side requirement table cannot hold them either, because its text
columns are library columns. The tenant holds the licence and already keeps
such a list. Units must not become extra register rows, because every count
that reads that table — the standing panel, the heatmap, the review roadmap
branch — would inflate.

## Decision

A tenant table, `soa_unit`, under forced row-level security, one row per unit
per legal entity, holding the tenant's own reference and title plus
applicability, reason, decision time, compliance status, note and version,
unique per scope row and reference. A unit may exist only under a scope row
whose obligation sits under a standard-level instrument (422
`units_only_under_standards`) and whose applicability is "applies" (422
`scope_not_applicable`), so a tenant cannot build a framework the library has
not admitted. Reference and title are fixed once the unit has a request, a
decision or a gap (409 `unit_has_history`); to correct one, add a new unit and
file "does not apply" for the old one. Applicability changes only through the
ordinary request, which gains a nullable unit, and gaps gain one too. Evidence
and internal links stay on the conformance row. The form asks for the tenant's
own words and offers no field for the standard's text. Nothing written under a
standard reaches a search chunk, an embedding input or a model input, proved by
a guard test written per row.

Deliberately not done: copying units forward to a new edition or another
entity, evidence per unit, and any roll-up across units.

## Consequences

Easier: the register keeps its shape and its counts, the tenant's own words
stay the tenant's, and the structure itself keeps the product out of
general-purpose GRC. Harder: a tenant with three certified entities pastes
three times, and the guard test must exist before the search scope decision is
relaxed at R2. To remember: if the lawyer says a bank's clause references in a
SaaS break its licence, chunk 8 ships without this table and the conformance
row per entity, with the tenant's own SoA as evidence, still works.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The table, its rules and the request and gap links | Chunk 8 |
| 2 | The paste with a dry run | Chunk 8 |
| 3 | The units list, the paste dialog and the filtered register view | Chunk 8 screens |
| 4 | The per-row index and model guard test | Chunk 8, before the search scope is widened |
