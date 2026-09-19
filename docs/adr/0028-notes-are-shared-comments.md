# ADR 0028 — Notes are shared comments, and one recipient check serves every notification

**Date:** 2026-09-19 · **Status:** accepted by default (D-22, D-34, PRD 0.3 COL-01, COL-02; the owner confirms)

## Context

Alex asked for "notes on my work". Every role holds `audit.read`, `record()`
stores before and after values, and the outbox feeds webhooks and the audit
stream, so nothing written through the ordinary path is private. Notifications
were about to grow three new kinds, each of which would otherwise decide its
own recipients, and team rows would keep reaching deactivated members and
people who lost read permission.

## Decision

Notes are the existing shared comments. On My work they appear in a panel named
"Comments and mentions", never "Notes", whose composer says that everyone in
the organisation can read them, and the read is filtered by the subject's read
permission. Comment text never reaches logs, error reports, audit after values,
outbox payloads, webhooks, notification titles or emails. One recipient check
serves every notification kind, mentions included: active members whose roles
can read the record's kind at send time, one notification per person per event
whatever the number of reasons, with a team expanding to its active members.
Removing a member also ends their team memberships.

Deliberately not done: private notes. They would need a per-user row-level
policy, audit and outbox rows without the text, exclusion from exports, and
they would hide compliance work from the tenant's own auditors. That is a
product-invariant change and an open question for the owner, not a default.

## Consequences

Easier: one place decides who hears about anything, so a new kind cannot leak
by forgetting a check; the panel's name and its visibility line match what the
system actually guarantees. Harder: every notification kind must route through
the resolver, and the per-subject filter costs a permission read per kind. To
remember: if the owner does want private notes, this ADR is superseded and the
invariant question is reopened before any code is written.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The recipient check, the three new kinds, participant and linked-change notices | Chunk 10 |
| 2 | Review reminders, escalation to department heads, the digest on My work | Chunk 10 |
| 3 | The comments and mentions panel and its read | Chunk 10 |
