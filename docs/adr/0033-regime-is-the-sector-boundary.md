# ADR 0033 — Every instrument and every change carries a regime, and the regime list is the boundary

**Date:** 2026-09-19 · **Status:** accepted by default (D-39, PRD 0.3 §1, INV-01, WAT-03, AC-AGT1; the owner confirms)

## Context

PRD 0.2 limits the product to regulated financial services, but nothing
enforced it. `schema.sql` has the instrument regime NOT NULL while the model
made it nullable, and an instrument with no regime matches every tenant.
Chunk 3 already plans to fold the instrument's regime into obligation matching.
The regime list is the one closed list that grows only through a reviewed
proposal, which makes it the natural boundary.

## Decision

Make the instrument regime NOT NULL. The seed-integrity test and the instrument
proposal's apply check that it is a term of the regime dimension, answering 422
`not_a_regime`. Obligation matching folds in the instrument's regime, and
FP-S1's clause about an obligation with no scope terms is amended to say so.
Change registration refuses a change with no regime term, answering 422
`regime_required` with the valid keys. A standard takes the regime of the
family of law it serves. The reviewer rejects an out-of-scope proposal with the
reason row "Outside the sector scope".

## Consequences

Easier: one closed, reviewed list decides what may enter the library, and the
same fold serves the markets derivation. Harder: a standard becomes visible
only when both its standard term and its regime are in a tenant's scope, which
the usage note and the counted preview must explain. To remember: private paths
(tenant-requested sources, tenant-private records) have no editor, so the
required regime, the provision trigger and the prompt rule are their scope
checks.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The NOT NULL migration and the seed-integrity assertion | Chunk 3 |
| 2 | The instrument-proposal check and the out-of-scope rejection reason | Chunks 4 and 5 |
| 3 | The change-registration check | Chunk 5 |
