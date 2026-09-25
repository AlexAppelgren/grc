# ADR 0032 — International is a jurisdiction kind of its own

**Date:** 2026-09-19 · **Status:** accepted by default (D-38, PRD 0.3 INV-01, INV-08, I18N-01; the owner confirms)

## Context

`Instrument.jurisdiction` and `Authority.jurisdiction` are required, and the
jurisdiction kinds today are supranational and country. A standards body is
neither. Two rules must be able to tell an international issuer from the EU,
and both must do it by kind and never by key: the watch rule that allows a
standard term only on a change from an international issuer, and the markets
derivation of ADR 0026, which would otherwise give every standard a
jurisdiction term and hide it from any tenant with an operating market.

## Decision

Add a jurisdiction kind `international` and one seeded row, International, with
English as its default language and no parent. The jurisdiction list is seeded,
never proposed. A standard's obligations carry no jurisdiction term, the
markets derivation derives nothing for this kind, and no mirrored taxonomy term
is created for it. The standards authority is seeded with the first standard,
and the accreditation forum's authority arrives with the first change from it.
I18N-S1 and the test that asserts the exact jurisdiction set gain the row.

## Consequences

Easier: two unrelated rules read one fact, and neither names a key. Harder: the
exact-set test and the reference read must be amended together, and the markets
work must honour the exclusion. To remember: I18N-01 is unchanged — it asks for
jurisdictions as data, which one more row satisfies.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The kind, the row, the authority and the amended I18N-S1 | Chunk 3 |
| 2 | The exclusion in the markets derivation and the mirror | With the markets prerequisite |
