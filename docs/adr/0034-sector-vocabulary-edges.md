# ADR 0034 — The sector scope's edges: tax, AI and the licensed-activity dimension

**Date:** 2026-09-19 · **Status:** accepted by default (D-40, PRD 0.3 §1; the owner confirms)

## Context

PRD 0.2's scope sentence named neither tax nor AI, yet the seeded regimes
include both, for the tax duties a firm carries for its clients and for the AI
Act under ICT risk. The `licensed_activity` dimension ("The licence under which
the firm acts") exists and has no terms, although the PRD names six sectors.
A system term cannot be retired today, so adding a regime is hard to undo.

## Decision

Keep tax and AI inside the scope and name both in the PRD's scope sentence. The
PRD's six sectors become terms of the existing `licensed_activity` dimension,
added by proposal rather than invented here. Regime terms are added only for a
body of law an instrument actually needs, and no new legal entity types are
added until `licensed_activity` has been reviewed. The regulatory scope work
adds the Banking and Payments regimes; this decision adds no rows itself.

Deliberately not done: deciding whether sustainable-finance disclosure,
consumer credit and accessibility rules as applied to banking are in scope.
That is one question for the owner, asked once for both analyses.

## Consequences

Easier: the PRD sentence and the seeded data agree, and the dimension that was
designed for the sectors is the one that gets them. Harder: nothing until the
owner answers; until then the scope sentence carries the default. To remember:
a regime term, once seeded as a system row, cannot be retired without a new
proposal kind.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The PRD sentence | Now |
| 2 | The licensed-activity terms, by proposal | After the owner answers |
