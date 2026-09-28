# Security review: perf-audit-writes, `record()` in one statement (2026-09-28)

## Question

Does the change to `record()`'s mechanics (ADR 0063) keep every CLAUDE.md section 5
invariant it touches? The audit row and the outbox row must go in the same transaction as
every write, through `record()` alone. The ledgers must stay append-only under their
triggers. The two zones must hold under forced row-level security. Nothing may be
overwritten.

## Standard

OWASP ASVS 5.0.0 chapters V8 (authorization, here the zone of a row), V15 (secure coding:
injection) and V16 (security logging), read against CLAUDE.md section 5, playbook 4.3, and
hardening H3 and H15.

## Scope

`git diff origin/main...HEAD` on `claude/perf-audit-writes`: `backend/apps/shared/audit.py`,
the `@batched()` or `with ..., batched():` added to twelve writes, `backend/scripts/compliance_check.py`
(the new `audit-door` rule), the tests, and lowered query pins.

## Findings

### 1. Injection: none

`_insert_both` composes one statement from two strings Django's `SQLInsertCompiler`
produced (`WITH audit_rows AS (<audit INSERT>) <outbox INSERT>`). The strings hold only
quoted table and column names from the model's `_meta` and `%s` placeholders. Every value,
the actor's label, the summary, the before and after JSON and the payload included, goes
in the parameter tuple and is bound by the driver. No caller input reaches the SQL text.

### 2. Same transaction: kept, and tightened

The combined statement runs on the caller's connection inside its open transaction.
`NotInTransaction` still guards both `record()` and `_write()`. A same-zone write no longer
opens a savepoint of its own. A failed audit insert therefore aborts the caller's
transaction, and no statement, `COMMIT` included, can persist the change without its row.
Before, a caller that caught the error could roll back to `record()`'s savepoint and commit
the change unaudited. Proven by `AFailingWriteTakesItsRowsWithIt`, which fails against the
old mechanics.

Callers that catch `IntegrityError` were read (15 sites). Each wraps its own
`transaction.atomic()` around the change and any `record()`, so its savepoint still takes
both back together.

### 3. Two zones: kept

- A row is still inserted in the zone its `tenant_id` names. The mixed-table write policy
  (`WITH CHECK`, H15) checks every row of the combined statement, as it checked each
  `bulk_create` before.
- A row of no tenant written from a bank's session still goes through `platform_zone()` with
  its savepoint inside it, so a failed insert puts the bank's tenant back before the error
  surfaces. `OneStatementAndASavepointOnlyAcrossTheZones` pins the order: savepoint,
  combined insert, release, then the tenant is back on. It also proves that a failure
  leaves the bank's zone active.
- The zone is read with `current_setting` (the GUC the policies read) when the rows are
  written, not when `record()` is called. For a single call that is the same moment. For a
  batch it is the zone of the actual insert. That is more exact: before, a batch that
  recorded a platform row outside any bank and then activated one would have tried to
  insert that row in the bank's zone and been refused.
- Which caller may pass `tenant_id=None` is still the guard's question (H3,
  `tests_hardening.LibraryAuditRowsCarryNoTenantWords`), unchanged.

### 4. Append-only and nothing overwritten: kept

The combined statement is two INSERTs. Row triggers fire for each row as before, and the
append-only triggers (`cw_append_only_guard` on `audit_event`, `cw_outbox_guard` on
`outbox_event`) act on UPDATE and DELETE, which this change never sends. `TheTriggersStillRefuse`
proves UPDATE and DELETE are refused on rows written by a single, a crossing and a batched
write, and `tests_append_only` passes unchanged. The Python guard (`AppendOnlyModel.save`)
still refuses a returned row, whose `_state.adding` is set to False as `bulk_create` did.

### 5. `record()` the only door: kept, now a lint gate

The door now sends raw SQL, so a grep for `bulk_create` no longer finds every writer. The
`audit-door` rule in `scripts/compliance_check.py` refuses these outside
`apps/shared/audit.py`, migrations and `tests_*`, with no suppression:

- building an `AuditEvent` or `OutboxEvent`;
- calling `.objects.create`, `bulk_create`, `get_or_create` or `update_or_create` on either;
- SQL that inserts into either table, in any letter case, through quotes and with the
  schema named.

`TheLintStillRefusesAWriteOutsideRecord` plants each form. The full tree has no finding.
The AuditAssertingClient guard, which fails a mutating route that writes no audit row,
passes unchanged.

### 6. `batched()` in twelve writes: rows identical, one residual risk

`batched()` holds rows until its block ends, and a block that raises writes nothing. Each
wrapped write was read for:

- a use of `record()`'s return value inside the block: none. The only caller that uses it,
  `support_access.record_read`, is not wrapped;
- a read of `audit_event` inside the block: none;
- an inner savepoint whose error is swallowed after a `record()`: none. The savepoints in
  the approval path re-raise, and the tenant slug retry records nothing;
- where the write opens its own transaction (proposal approval, member removal), the block
  sits inside it.

Residual (low, pre-existing, documented in ADR 0063): future code inside a `batched()` block
that swallows an error from its own savepoint after recording would keep an audit row for a
change that was rolled back. This is not new to this change, and it could not drop an audit
row. Review catches it.

### 7. Tenant content in logs: none

No logging was added. The tests carry fixture strings only.

## Result

No finding above low. The invariants hold, and a failed audit insert now dooms its change,
which is stricter than before. Gates: `apps.shared` (with the new
`tests_audit_writes`), the suites of every touched app, compliance_check (0 findings),
ruff, mypy.
