# ADR 0052 — The console reads each bank's figures through one window on tables of numbers

**Date:** 2026-09-20 · **Status:** accepted (D-59, Alex 2026-09-19; PRD 0.4 ADM-02)

## Context

`NFR-S19` asks the platform to see the same usage figures for each bank,
`ADM-S5` asks for failed jobs with a retry action, and `INT-S4` asks for stream
lag in system health. Without a per-bank read, every stuck delivery would need
a support grant (ADR 0042) before anyone could look. The invariant to keep is
that tenant content never reaches the platform.

## Decision

Two tables hold numbers, kinds and times only. `usage_record` holds the tenant,
metric kind, month and an integer quantity, with money as integer minor units
and a currency kind. `job_run` holds the id, tenant or none, job kind, status,
attempts, times, an `error_code` kind — never an exception message — typed
integer stats, and a typed subject kind plus uuid so a retry can rebuild the
job. A structural test refuses a free-text or untyped JSON column on either
table while allowing kind columns. Only the worker writes these rows, under
`@tenant_task`.

Each table gets one SELECT-only policy keyed on `app.platform_counters`.
`tenancy.platform_counters(principal)` opens only for a platform principal
holding `tenants.manage` or `system.health`, refuses while a tenant is active
and clears afterwards; an AST guard limits the callers to
`billing/usage_logic.py` and `governance/health_logic.py`, and `tests_rls` pins
every window with its tables in one map. Each console read writes one platform
audit row, `platform_counters.read`, recording the screen and the filters,
never the figures. `POST /console/jobs/{id}/retry`, under `system.health`,
re-queues the job as a tenant task from its kind, tenant and subject, writes a
platform audit row, and the retried task records an audit row with a system
actor inside the tenant. Never in the window: `tenant_metric_daily`,
`usage_event`, audit rows, outbox payloads, `ai_generation`, webhook URLs,
members or names; the seat count comes from the seats metric, never from
reading membership. Banks keep seeing their own figures from the same rows.

Deliberately not done: figures for the tenant only, a usage table without
row-level security, a `SECURITY DEFINER` read function, and platform-wide
totals with no tenant attached.

## Consequences

Easier: support can see which bank's stream is lagging and retry a failed job
without entering the bank, and the structural test makes "no tenant content"
true by shape rather than by review. Harder: two tables that may never grow a
text column, so every future figure must arrive as a kind or a number. To
remember: the assurance pack's data-flow document must state that bleqq sees
these figures.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The window, the guard, the `job_run` policy, `error_code`, the typed stats and the subject reference | `c14-job-runs` |
| 2 | The `usage_record` policy and the console read | `c14-billing-usage` |
| 3 | Health inside the window, retry, and the access review of every window | `c14-health-backend`, `c14-owasp-access` |
