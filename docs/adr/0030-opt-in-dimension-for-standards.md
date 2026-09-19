# ADR 0030 — A standard is opted into through an opt-in dimension of the regulatory scope

**Date:** 2026-09-19 · **Status:** accepted by default (D-36, PRD 0.3 FP-01, AC-FP3; the owner confirms)

## Context

FP-01 says an empty dimension does not restrict, and the SQL twin counts a
dimension only where a scope term exists. Under that rule a new standards
dimension would make every standard, and every change to one, match every
tenant that follows no standard, and they would reach every feed and roadmap.
The inverse risk is worse: a standard term placed on a law's obligation would
hide binding law from every tenant that does not follow the standard, with no
preview and no second person.

## Decision

The dimension `standard` ("Standards followed") carries a new tier-1 kind,
`opt_in`. A record carrying one of its terms matches only when the regulatory
scope names that term, including when the scope holds no term in the dimension
at all. The rule lives in the matcher — the restricting set is
`restricts_footprint OR kind = 'opt_in'`, in the ORM and in the SQL join — so a
relabel, a seed or a migration that clears the flag changes nothing and no
guard is needed at proposal time. `opt_in` is a required keyword argument of
the pure rule, so no caller can forget it. There is one term per standard, not
per edition, so a tenant's choice survives a new edition. An opt-in term may
sit only on a standard's own obligation and on a change whose authority's
jurisdiction kind is international; both directions are checked at creation, at
a reviewer's correction and at apply. Opt-in dimensions gate at tenant level
only, so an entity's span leaves them out. On the page an empty opt-in group
reads "None followed", and ticking a standard reveals and never narrows.

## Consequences

Easier: a standard is invisible until a tenant asks for it, and the rule cannot
be switched off by data. Harder: this edits a built, SQL-mirrored rule, so both
mirror suites grow cases for a dimension missing from the scope and for the
flag set false. To remember: a standard shows only when both its standard term
and its regime are in the scope, which the usage note and the counted preview
must make visible.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The kind, the pure rule and its callers | Follow-up to chunk 2, buildable now |
| 2 | The replaced SQL function and the mirror suites | With it |
| 3 | The dimension and its first term as seed rows | With it |
| 4 | Opt-in groups on the Regulatory scope page | Chunk 2 or 3 screens |
