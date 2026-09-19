# ADR 0018 — Reuse the playbook's structure from the last repo

**Date:** 2026-09-19 · **Status:** accepted by default (playbook Appendix C; the owner confirms)

## Context

`docs/PLAYBOOK.md` started as the Eden OS playbook and keeps what made that
repo good: gates that block, tests against the real thing, structural
guards, the document chain, whole slices. Everything specific to a booking
and payments product was replaced with what this product needs. The
playbook's Appendix A, B and C prescribe the shape of `CLAUDE.md`, the app
specs and the ADRs.

## Decision

Adopt the playbook's structure as is: the repo shape of Section 2.1, the
document chain of 2.5 (`CLAUDE.md`, `docs/CONVENTIONS.md`, `docs/adr/`,
`docs/plans/*`, `docs/runbooks/*`, `docs/TODO_FOR_alex.md`), one `app.md` per
app with exactly four sections, scenario IDs `<PREFIX>-S<n>` mapped to
`tests_scenarios.py` and journey specs, the twelve-step feature loop of
Section 3, and the pre-push checklist of Appendix D. Deliberately not done:
a second spec format, a wiki, or issue-tracker-driven scope.

## Consequences

Easier: an agent that read the last repo's conventions is at home here, and
`scripts/requirements_coverage.py` can parse every spec the same way.
Harder: the document chain must be kept true at every chunk, which the
definition of done requires. To remember: `PLAYBOOK.md` stays the reference
that `CLAUDE.md` and `CONVENTIONS.md` point back to; when they drift, fix
them, not the playbook.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The chain created from the PRD | Phase 0 |
| 2 | `docs/reviews/`, `docs/security/`, `docs/assurance/` as they are needed | Chunks 1 to 14 |
