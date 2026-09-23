# ADR 0038 — Many pending applicability requests are decided in one call, with four eyes on every row

**Date:** 2026-09-19 · **Status:** superseded by D-75, which sets applicability through one person's confirmed, audited write, so no request exists to decide in bulk; a paste stays one call capped by `REGISTER_BULK_MAX`, one audit event per row (was: accepted by default, D-44, PRD 0.3 REG-01, AC-REG1)

## Context

A Statement of Applicability for one entity can hold about a hundred units,
each with its own applicability decision. Deciding them one at a time is a
hundred requests. The earlier worry that this meant a hundred passkey prompts
was wrong: the step-up check accepts any assertion younger than the freshness
window, so one ceremony covers a sitting.

## Decision

No batch table. One route, under `applicability.approve` and a step-up, takes a
list of request ids each with a decision and an optional note, and decides each
one through the single-request logic in one transaction, writing one audit row
per decision citing the assertion. A request the caller filed answers 409
`four_eyes_violation` and nothing at all is decided. `REGISTER_BULK_MAX`, the
page maximum, caps a call, which keeps it inside the response budget; a full
Statement of Applicability takes two calls. A pending request cannot be edited:
the requester withdraws it and files it again, so the approver decides exactly
the rows the call listed. The approver's preview is their queue, filtered by
standard, entity and requester.

## Consequences

Easier: four eyes and the audit trail hold unchanged, with no duplicated status
or decider. Harder: deciding ninety rows at once invites rubber-stamping, which
explicit request ids, uneditable requests, the filtered queue and one audit row
per decision mitigate but cannot remove. To remember: the applicability request
table joins the four-eyes guard list when chunk 8 builds it.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The route, the cap and the four-eyes refusal | Chunk 8 |
| 2 | The decide-selected queue screen | Chunk 8 screens |
