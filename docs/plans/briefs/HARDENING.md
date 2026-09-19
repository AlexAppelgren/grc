# Hardening follow-ups found in review

Findings from the security reviews of 2026-09-19 that did not block their own merge, because
each existed before that branch or belongs to a later task. Each gets built, not forgotten.
The main agent adds a row here whenever a review turns up such a finding.

| # | Finding | Found in | Severity | Where it gets fixed |
|---|---|---|---|---|
| H1 | `PageQuery.offset` has no upper bound: a huge offset makes the database raise, and every paginated route answers 500 | chunk4-T3 review | low | Task H-A below |
| H2 | `build_principal` (`apps/identity/session_logic.py`) trusts the permissions stored on a tenant role row without limiting them to `TENANT_PERMISSIONS`; seeds and the role editor refuse `proposals.review`, but a row written around them would carry it | chunk4-T11 | low, defence in depth | Task H-A below |
| H3 | Nothing stops a future writer from recording a tenant-derived title under a library subject with no tenant, which `GET /audit-events` would show every tenant | chunk4-T3 review | low, future risk | Task H-A below: a guard test listing every `record(tenant_id=None, ...)` with a library subject type and its actor type |
| H4 | `cw.maintenance` rests on review alone | chunk3-rest-T1 review | low | chunk3-rest-T1 (compliance rule, in progress) |
| H5 | Seeded library-list rows get no audit row, and every deploy undoes an approved reorder, retire or default change | chunk4-T2 and its review | medium | REGULATORY_SCOPE.md T01 (cloud, in progress) |
| H6 | Under the append-only trigger a machine translation cannot be confirmed in place (INV-05, INV-S6) | chunk3-rest-T1 review | low, design | TODO_FOR_alex with a default; built with the screens that confirm (chunk3-rest-T12/T14 or chunk 4) |
| H7 | Child tables of tenant-private library records (titles, versions, summaries, terms, tags) have no RLS of their own; every read must reach them through the parent | chunk3-rest-T4 | low, future risk | Chunk 7's search index must carry the owner and its own RLS; the chunk 7 plan names it |
| H8 | Approval's audit rows carry `steppedUp: false` because `apply.py` does not pass the step-up id | chunk4-T3 review | low | chunk4-T6 (already in its task text) |
| H9 | The obligations count evaluates `taxonomy_in_footprint` for every visible obligation, so the cost grows with the whole library, not the page (about 200 ms per 1,000 obligations) | chunk3-rest-T4 review | low, future risk | A set-based anti-join replacing the per-row function call; before the library passes a few hundred obligations |
| H10 | Gunicorn's default access log writes every query string (`?q=` search text), client IP and user agent to stdout, and Sentry turns those lines into breadcrumbs whose message is not scrubbed | chunk3-rest-T4 review | high | Worktree `wt/log-no-query`, in progress; merges before chunk3-rest-T4 |
| H11 | The app role can set `cw.maintenance` itself (in any letter case, since PostgreSQL setting names are case-insensitive), which switches every append-only trigger off; only a source lint stands in the way | chunk3-rest-T1 verification | medium | Task H-B below |
| H12 | The `cw.maintenance` lint is case-sensitive; `LIBRARY_DIFF_MAX_SENTENCES` accepts 0, negatives and huge values (500 takes about 7 s per diff); library texts have no length limit, so a 200 KB text of short sentences costs about 0.5 s in version_diff | chunk3-rest-T1 verification | low | Task H-B below |
| H13 | Sessions carry platform grants even inside a bank, and a bank invitation does not refuse an address holding a platform role | chunk4-T4 review | medium | Task H-A (cloud, in progress) |
| H14 | Every deploy resets sort order, active and default on each tenant's own system list rows (`taxonomy/tenant_hooks.py` uses update_or_create), undoing a tenant admin's reorder | scope T01 review | medium | The T01 integration task (local, next) |
| H15 | `rls_operations(mixed=True)` gives `api_key`, `problem_report`, `ai_generation` and `outbox_event` one FOR ALL policy whose write check equals the mixed read rule, so a bank session can insert, change or delete platform rows at the database level (for example the platform agent's API key); two zones must hold in the database, not only in code | E5 fix, 2026-09-19 | high | Task H-C below, after H-B merges (both touch `migration_helpers.py`) |

## Task H-A: three small guards (after chunk3-rest-T3 merges, which owns `apps/shared/schemas.py`)

**Owned:** `backend/apps/shared/schemas.py` (the `PageQuery.offset` bound only),
`backend/config/settings.py` (one labelled setting), `backend/.env.example`,
`docs/runbooks/RAILWAY_VARIABLES.md`, `backend/apps/identity/session_logic.py` (the principal's
permissions only), `backend/apps/shared/tests_hardening.py` (new).

1. H1: bound `offset` with `le=settings.API_PAGE_OFFSET_MAX` (a setting with an env override;
   default 100000); a test that an offset above it answers 422 on a paginated route.
2. H2: the principal's permissions are the role rows' permissions intersected with
   `TENANT_PERMISSIONS` for a tenant session (and with the platform set for a platform
   session); a test that a role row carrying `proposals.review` does not give it.
3. H3: a guard test that walks every `record(` call in production code (AST), and fails when
   one passes `tenant_id=None` with a library subject type unless its actor is the system, an
   agent or a platform editor and its title is not tenant-derived; list today's calls in the
   test as the allowed set, so a new one must be looked at.

Gates: `apps.shared apps.identity apps.governance` tests, ruff, mypy, compliance lint,
requirements coverage. Security review before merge (authentication).

## Task H-B: the append-only guard the app role cannot switch off

**Owned:** a new migration in `backend/apps/shared/migrations/` that replaces `cw_append_only_guard`, `backend/apps/shared/migration_helpers.py`, `backend/scripts/compliance_check.py`, `backend/apps/shared/tests_compliance_lint.py`, `backend/config/settings.py` (the diff cap's bounds only), `backend/apps/shared/tests_audit_on_write.py` or a new `tests_append_only.py`.

1. H11: the guard function ignores `cw.maintenance` when `current_user` is the app role (compare against the role name the settings already know, never a hard-coded literal that could drift), so only the schema owner in a migration can use the hatch. Tests as `cw_app`: `SET LOCAL cw.maintenance = 'on'` and `SET LOCAL CW.MAINTENANCE = 'on'` still leave UPDATE and DELETE refused on every append-only table; the migration role can still use it inside a migration.
2. H12: the lint matches `cw\s*\.\s*maintenance|maintenance_setting` case-insensitively, with an upper-case plant in its test; the diff cap refuses to boot outside 1 to 200; a library text longer than a setting (`LIBRARY_TEXT_MAX_CHARS`, env override) is diffed as one delete and one insert, with a test.

Gates: `apps.shared apps.library` tests under coverage, ruff, mypy, compliance lint, migrate_from_zero. Security review before merge.

## Task H-C: mixed tables write only their own zone

**Owned:** `backend/apps/shared/migration_helpers.py` (`rls_operations`), one new migration per app that owns a mixed table (`api_key`, `problem_report`, `ai_generation`, `outbox_event`, and any other table the helper marks mixed), `backend/apps/shared/tests_rls.py`.

Split every mixed table's policy the way `agent_run` does since the E5 fix: a FOR SELECT policy with the mixed read rule (the tenant's rows and the rows without a tenant), and a FOR ALL policy whose USING and WITH CHECK are `tenant_id IS NOT DISTINCT FROM NULLIF(current_setting('app.tenant_id', true), '')::uuid`, so a bank session writes only its own rows and a session with no tenant writes only platform rows. Keep any narrower policy a table already has (the problem-report exception, if Alex approves it, is designed on top of this). Tests as the real cw_app role, per table: under tenant A, inserting, updating and deleting a platform row is refused or touches 0 rows, moving a row between zones is refused, and reads are unchanged. The RLS guard asserts the policy shape for every mixed table, so a new mixed table cannot get the old shape. Security review before merge.
