# ADR 0049 — Tenant exit needs two people, and execution deletes every tenant row

**Date:** 2026-09-20 · **Status:** accepted (D-56, Alex 2026-09-19; PRD 0.4 REP-04, §6, CLAUDE.md §5)

## Context

REP-04 promises a full export in open formats and verified deletion, and
`REP-S5` read as one admin with a step-up. Deleting a bank's tenant cannot be
undone, so one stolen passkey must not be enough. A processor that returns the
data at the end of a contract is then asked to delete it, and keeping the audit
rows afterwards would need a legal basis we do not have. `cw_app` must stay
unable to wipe ledgers, which means the deletion cannot run in the app's own
role.

## Decision

Two different people holding `security.manage` request and approve the exit,
each with a passkey; a CHECK keeps `approved_by` from being `requested_by`,
`tenant_exit_request` joins FOUR_EYES_TABLES, approving your own request
answers 409, and every active admin is emailed at the request, at approval and
seven days before execution. On approval the tenant becomes `closing`: mutating
routes answer 409 `tenant_closing`, while sign-in, refresh, sign-out, step-up,
revoking sessions and keys, exports, downloads and cancel keep working, and
agents, reminders, digests and webhooks stop. The final export covers the
register, cases, evidence files, configuration and the audit log in open
formats, and its SHA-256 is recorded. Execution waits
`TENANT_EXIT_DELAY_DAYS` (30), and any `security.manage` holder may cancel with
a step-up until then.

The platform operator confirms out of band with the bank's contract contact and
runs `manage.py execute_tenant_exit <id>` as `cw_migrator` in a one-off
container. The command refuses unless the request is approved and not
cancelled, the delay has passed and the export has been downloaded. The
deletion itself is a SQL function created by a migration, owned by
`cw_migrator` and never granted to `cw_app`. It deletes every table in the
lifecycle registry, including the audit log, outbox, security log and footprint
history; the tenant's rows in mixed tables, its problem reports included, while
a proposal that resolved one stays; its private instruments and obligations
with their append-only children; memberships, then users left with no
membership and no platform role, with their step-up assertions, passkeys and
sessions. A former member still named by a library record keeps a user row with
the name only and a unique placeholder email. The command verifies zero rows
and an empty storage prefix. What remains is the tenant row with status
`deleted` and a `TenantExitReport`: counts before and after, the export hash,
the requester, approver and operator, the assertion ids and the date backups
age out, kept for `TENANT_EXIT_RECORD_YEARS`. Afterwards sign-in answers 404.

This is the second named exception to "Nothing overwritten" in CLAUDE.md §5:
at exit the ledgers go with everything else.

Deliberately not done: one admin with a step-up, keeping the audit rows after
exit, pseudonymising ledgers in place, a deletion function callable by
`cw_app`, deletion by the platform alone, and a new `tenant.exit` permission.

## Consequences

Easier: a bank can be told exactly what leaving does, and the assurance pack
can point at a command and a report. Harder: the deletion is a manual operator
step by design, and the runbook must re-apply exits after any database restore
and check regularly for approved exits past their date. To remember: the
tombstone rests on the platform's own legitimate interest, for counsel to
confirm, and the contract's transition period, with full service, comes before
the request.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The `closing` and `deleted` statuses | `c12-tenant-deleted-status` |
| 2 | The request table, the four-eyes CHECK and the routes | `c12-exit-request` |
| 3 | The owner-only function, the command, the report, the storage list and the runbook | `c12-exit-execute` |
