# ADR 0040 — The Statement of Applicability is a filtered register view in R2 and an export in R3

**Date:** 2026-09-19 · **Status:** accepted by default (D-46, PRD 0.3 REG-08, REP-02; the owner confirms)

## Context

A bank needs its Statement of Applicability as a document at a certification
audit. It also needs to read and work it every day. Exports are R3, and every
new export kind is a new code path with its own job, step-up and audit.

## Decision

In R2 the register filtered by standard and legal entity is the Statement of
Applicability: per unit the reference, the tenant's title, applicability, the
reason, the status, the approver and the decision date, with each unit's
decided requests as its history. There is no "as of" in R2. The dated document
is R3's filtered inventory export, with no new export kind. An existing
Statement of Applicability enters through the chunk 8 paste, and the
spreadsheet import stays generic.

## Consequences

Easier: filters need no new code path and units keep one entry path. Harder: a
bank at an audit before R3 has to read the screen or copy it. To remember: the
owner may want a CSV pulled into chunk 8 for exactly that reason, which is an
open question, not a default.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The filters and the unit rows | Chunk 8 |
| 2 | The dated export | Chunk 12 |
