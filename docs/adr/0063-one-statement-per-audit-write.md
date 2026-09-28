# ADR 0063 — One statement per audit write, and a savepoint only across the zones

**Date:** 2026-09-28 · **Status:** accepted (owner approval of the perf audit's wave B, 2026-09-28; PRD AUD-01, NFR-02; follows ADR 0058 and hardening H15)

## Context

The query audit of 2026-09-28 (`docs/plans/r2-waves/PERF_AUDIT.md`, finding 3) found that
`record()`, the only door into `audit_event` and `outbox_event`, cost 846 of the 6,450
queries the perf harness ran: 193 audit rows, 386 savepoint statements and 45 reads of the
zone. Every call went through `transaction.atomic()`, which is a `SAVEPOINT` and a
`RELEASE SAVEPOINT` inside a request, around two INSERTs, so one audit row was four
statements. Twelve writes recorded more than once without `batched()`, so they paid that
four times over.

Measured on origin/main at 55d804c (wave A on main), one warm-up and one sample per row of
`backend/perf/routes.py`, on a database seeded with `seed_e2e`, over the 283 rows that
answered: 5,167 queries, of which `record()` issued 763, 360 of them savepoint statements
and 43 zone reads.

## Decision

`record()` keeps its signature, its callers, its rows and its guarantees. Its mechanics
change in three ways, all in `backend/apps/shared/audit.py` and the twelve callers.

1. **One statement.** The audit rows and their outbox rows go in as one statement: the
   audit INSERT as a data-modifying `WITH`, the outbox INSERT as the main statement. Both
   INSERTs are built by Django's own insert compiler from the same model objects
   `bulk_create` used, so every column, default and `created` stamp is the one it was. The
   foreign key from the outbox row to its audit row is checked when the statement ends, when
   both rows exist.
2. **A savepoint only across the zones.** A write in the session's own zone runs no
   savepoint; a write that crosses the zones (a row of no tenant written from a bank's
   session, H15) still runs in `platform_zone()` and a savepoint, in that order, exactly as
   before.
3. **`batched()` in the twelve writes that recorded more than once:** re-issuing an
   enrolment, the console's re-issue, creating a bank, approving a footprint request,
   approving a proposal (library and a bank's own), removing a member, entering a bank
   under support access, opening an agent run, opening a research or re-tag request,
   applying a control, opening a scope item's research, and escalating overdue actions.
   Where the write opens its own transaction (proposal approval, member removal) the block
   sits inside it, so its rows are written before that transaction ends.

The zone is now read once per write, when the rows are written, and only when a row of no
tenant is among them, instead of once per `record()` call of such a row. For one call that
is the same moment; for a batch it is the zone the rows are actually inserted in, which is
what the row-level security checks.

### Why a write in its own zone needs no savepoint

A savepoint does two things: it lets the statements after a failure run, and it lets the
caller carry on as if the failed statements had never been sent.

- **Nothing in `record()` runs after the insert in the same zone.** The write is one
  statement. If it fails, PostgreSQL aborts the transaction and the error reaches the
  caller as the insert raised it. There is nothing left to clean up, and no zone to put back.
- **The change must not outlive its audit row.** The change the row records was written
  earlier in the same transaction. With a savepoint, a caller that caught the error could
  roll back to it and commit the change with no audit row, which AUD-01 forbids. Without
  one, the aborted transaction refuses every further statement until it rolls back, so the
  change and its missing row go together. This is stricter than before, and
  `AFailingWriteTakesItsRowsWithIt` proves it.
- **The caller's own savepoints are untouched.** A write that must survive a refusal (a
  unique key taken, a replay) opens its own `transaction.atomic()` around both the change
  and its `record()`. That savepoint takes the change and its rows back together, as it
  always did.

A write across the zones still needs its savepoint for the first reason. After the insert,
`platform_zone()` must put the bank's tenant back with one more statement, which an aborted
transaction would refuse, hiding the insert's own error behind "current transaction is
aborted". The savepoint is rolled back first, the tenant goes back on and the caller sees
the real error. `test_a_crossing_write_that_fails_rolls_back_to_its_savepoint_and_puts_the_bank_back`
pins that.

### What does not change

The rows: every column, the order they read back in (`created`, `id`), the default payload
(`auditEventId`, `subjectId`) and a caller's own payload, the outbox row's tenant.
`TheRowsAreTheRowsWrittenBefore` writes the same calls through the old two-statement
mechanics, kept in the test as the reference, and through `record()`, one by one and
batched, and compares them column by column. Also unchanged: one audit row per `record()`
call, the same transaction as the change, `NotInTransaction` outside one, the append-only
triggers on both tables (`TheTriggersStillRefuse`, and the existing `tests_append_only`),
the mixed-table write policies, and `record()` as the only door. The compliance lint's new
`audit-door` rule makes that last one a gate, since the door now sends SQL of its own: an
`AuditEvent` or `OutboxEvent` built, created or bulk-created, or SQL inserting into either
table, anywhere but `apps/shared/audit.py`, migrations and tests, fails the lint.

## Consequences

Measured the same way after the change, over the same 283 rows: 4,599 queries (-568, 11 %),
of which `record()` issued 195. Savepoint statements fell from 360 to 2, the one write in
the harness that crosses the zones, and zone reads from 43 to 29. The median write fell from
19 to 16 queries. No row's count rose. The twelve writes each lost 5 to 19 queries, for
example removeMember 72 to 53, createRetagRequest 35 to 22, createConsoleTenant 74 to 63.

Easier: every audited write is three statements cheaper, with a tighter guarantee than
before.

Harder, and accepted:

- A `batched()` block holds its rows until it ends. Code inside a block must not swallow an
  error from a savepoint of its own that recorded something. The savepoint takes the change
  back but the held row would still be written. This was already true of `batched()` before
  this ADR. The twelve writes were read for it and none does. Their own savepoints either
  record nothing (a tenant's short name) or re-raise (a stable key, a vocabulary merge).
- A block must end in the zone of its bank's rows, since those rows are inserted when it
  ends. A row of no tenant is now safe from any zone, because it is placed when written. A
  bank's row written from another bank's zone would still be refused by the row-level
  security, loudly.
- `test_many_events_are_one_audit_insert_and_one_outbox_insert_in_the_order_recorded` in
  `apps/shared/tests_audit_on_write.py` counted two INSERT statements. It now counts one
  statement inserting into both tables, in that order. It is the one guard assertion that
  changes, because it pinned the mechanics this ADR replaces.

Security review: `docs/security/PERF_AUDIT_WRITES_REVIEW_2026-09-28.md`.
