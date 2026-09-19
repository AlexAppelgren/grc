# ADR 0022 — Two database roles so row-level security means something

**Date:** 2026-09-19 · **Status:** accepted by default (playbook 14, 11.1; the owner confirms)

## Context

PostgreSQL lets superusers and roles with `BYPASSRLS` skip every policy, and
a table's owner skips them too unless the table has
`FORCE ROW LEVEL SECURITY` (verified 2026-09-19 against the PostgreSQL
documentation, `Verification_Log.md`). A single application role that runs
migrations therefore owns the tables and can read every tenant. Tenant
isolation (NFR-01, AC-NFR2) has to hold against the role the app connects
with, not against good intentions.

## Decision

Two roles, created by `infra/db/init.sql` locally and by the role script in
`docs/runbooks/RAILWAY_DEPLOY.md` in production:

- `cw_migrator`: owns the schema and every table, runs migrations
  (`MIGRATOR_DATABASE_URL`). Locally it also has `CREATEDB` so the test
  runner and `migrate_from_zero` can create throwaway databases; production
  grants nothing of the kind.
- `cw_app`: runs the application (`DATABASE_URL`). `NOSUPERUSER`,
  `NOBYPASSRLS`, owns nothing; the first migration grants it table privileges
  and default privileges for later tables.

Every tenant table is `ENABLE` and `FORCE ROW LEVEL SECURITY` with a policy
reading `current_setting('app.tenant_id', true)`. The app refuses to boot
when its role is a superuser, owns the tables or has `BYPASSRLS`
(`apps/shared/db_role_guard.py`), and a structural guard proves it in tests.
Extensions `vector`, `citext`, `pg_trgm` are installed in the database and in
`template1` so throwaway test databases inherit them. Deliberately not done:
one role with `SET ROLE`, and RLS on library tables (they have no
`tenant_id`).

## Consequences

Easier: an isolation bug is a 404 in a test, not a breach in production;
the role check is one boot guard. Harder: two connection strings, and the
entrypoint must migrate as one role and serve as the other; test settings
must run tests as `cw_app` against a database `cw_migrator` created. To
remember: passwords are dev-only literals allowlisted in `.gitleaks.toml`;
production passwords live only in Railway variables.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | `init.sql`, boot guard, first migration grants, test settings | Phase 0 |
| 2 | Role script run in Railway by the owner | Before the first test deploy |
