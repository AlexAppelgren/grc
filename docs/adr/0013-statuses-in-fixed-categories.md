# ADR 0013 — Tenant sub-statuses inside fixed categories, no workflow engine

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-13; nothing for the owner to confirm)

## Context

Banks want their own status names ("Waiting for legal") and auditors want
guards that do not move: no sign-off with an open action, a second person
to close, a reason to dismiss (CAS-06, CAS-08, VOC-04). A configurable
workflow engine gives the first and loses the second.

## Decision

Case status categories (`new`, `assigned`, `assessing`, `implementing`,
`signoff`, `closed`, `dismissed`) are a kind in code with fixed transition
guards. A tenant adds sub-statuses under a category as vocabulary rows; the
state machine, the reports and the pill tone read only the category, and a
category never goes empty. Deliberately not done: tenant-defined
transitions, guards or categories.

## Consequences

Easier: the guards auditors rely on are the same for every tenant and
tested once (CAS-S12, CAS-S13, VOC-S8). Harder: a tenant that wants a new
stage gets a sub-status, not a new gate. To remember: `allowedTransitions`
on every workflow response comes from the category, so the UI never guesses.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Category kind, guards, `allowedTransitions` | Chunk 9 |
| 2 | Sub-status vocabulary and screen | Chunk 8 |
