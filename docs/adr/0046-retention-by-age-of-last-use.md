# ADR 0046 — A record is deleted ten years after its last use, through one database-guarded path

**Date:** 2026-09-20 · **Status:** accepted (D-53, Alex 2026-09-19; PRD 0.4 AUD-04, CLAUDE.md §5)

## Context

AUD-04 asks for retention with a purge that respects append-only tables, and
the schema already names closed cases, removed evidence and the audit trail as
the three categories. `record()` keeps before and after values, so a purged
case would survive inside the audit trail unless the trail can be purged too.
Personal data may not be kept longer than it is needed, and a bank's own
instruction is what a processor acts on. The recommendation offered each bank
three periods of its own; Alex answered "10 yrs after last use", one age for
everyone, measured from when a record was last used rather than from closure.

## Decision

A record is deleted ten years after its last use. What goes: cases closed or
dismissed longer ago than that, with their children, files first, unless a live
record still references them; evidence removed longer ago than that, file
first, then the row; and the tenant's `audit_event` rows, their published
outbox rows and its `login_event` rows. `footprint_history` is kept for the
tenant's life, because it replays the regulatory scope as of a date, and
library tables are never touched. A pause switch for the whole tenant replaces
the designed per-record legal hold.

Ledger rows are only ever deleted whole, never updated, through one
`SECURITY DEFINER` function owned by `cw_migrator`, with `search_path` pinned,
EXECUTE revoked from PUBLIC and granted to `cw_app`. It sets `cw.maintenance`
only through its own SET clause, so the hatch closes when it returns; it
filters explicitly on `app.tenant_id`, does nothing for a paused tenant, never
uses a cutoff later than one year ago and deletes only from a fixed list of
tables. `cw_app` is still refused a direct UPDATE or DELETE and still cannot
set the hatch itself. A daily `@tenant_task` runs it in bounded batches, gives
the same result if run twice, and writes one run row and one audit row with
counts only. One lifecycle registry, with a guard test, maps every tenant table
to cases, evidence, audit, live or platform window, and tenant exit (ADR 0049)
shares it.

This is one of the two named exceptions to "Nothing overwritten" in CLAUDE.md
§5: deletion by age, never an update.

Deliberately not done: purging notifications only, as `AUD-S6` read; purging
cases but keeping the ledgers forever; letting `cw_app` set the hatch;
migrator credentials in the worker; pseudonymising ledgers in place; and a
per-record legal-hold table now.

## Consequences

Easier: one age is one number to explain to a bank and to test, with no notice
period, no shortening delay and no per-tenant matrix. Harder: a bank that wants
to keep a case longer cannot, and every table must say what "use" means for its
rows. Accepted risk: a compromised app role can erase tenant ledger rows older
than one year; the one-year floor is the only bound, and purged data leaves
backups only when they expire. To remember: two details are still open (D-53):
what counts as "use", and whether a bank may change the ten years.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The columns, the lifecycle registry and the routes that read the policy | `c12-retention-contract` |
| 2 | The owner-only purge function with its floor | `c12-ledger-purge-function` |
| 3 | The daily job, the run row and the Data screen | `c12-retention-purge`, `c12-fe-data-retention` |
