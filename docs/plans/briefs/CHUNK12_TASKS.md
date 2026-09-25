# Chunk 12: tasks

Written 2026-09-20 by the planning workflow (read, plan, parallelism and coverage
critiques, revise). Each task runs in its own worktree or cloud session
(`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on
`main`. The task ids are the `c12-` package ids of `docs/plans/PARALLEL_PLAN.md`
section 3.3, plus `f03-T83` from `docs/plans/briefs/FEATURES_0_3_TASKS.md`; nothing is
renamed or dropped. Six ids are added or split, each for a reason the owner's decisions
of 2026-09-19 give (ADR 0046, ADR 0049) or a critique found; they are listed under
**Changes from `PARALLEL_PLAN.md`**.

**Revised 2026-09-20** to close the plan review's findings. Each fix is in the file, not
only here:

| Finding | What changed |
|---|---|
| HIGH — a configuration import carried tenant roles and their permissions behind `vocab.manage` alone, with no step-up, against CLAUDE.md §5 | `commitImport` for `kind=configuration` now needs `roles.manage` and `@requires_step_up`, declared beside the route in `c12-imports-contract` and built in `c12-config-jobs`, with the assertion id on the audit row and a done-condition in both; the default under **Defaults taken** and the note in `c12-config-logic` say the same, and `c12-fe-data-configuration`'s Commit asks for a passkey |
| HIGH — ruling 1 dropped H-C's guard that no foreign key into an append-only table carries a delete or update action, which is what `c12-exit-execute`'s cascades need | The guard is re-homed, not dropped: ruling 1 and `c12-ledger-purge-function` build it beside the `SECURITY DEFINER` guard, with a planted constraint and a done-condition, and the `HARDENING.md` row says where it went |
| MEDIUM — AUD-S8 already exists in PRD 0.4 as the ledger-purge scenario, so the retention screen would have taken a used id | `c12-ledger-purge-function` un-skips PRD 0.4's AUD-S8 and its existing stub; the retention screen's scenario is the new AUD-S9, written with its own new stub by `c12-retention-contract-b` and un-fixmed by `c12-fe-data-retention`. The ownership table carries both |
| MEDIUM — `cw_delete_tenant` is not `SECURITY DEFINER`, so it runs as `cw_migrator`, which is `NOBYPASSRLS` under forced RLS and, after ruling 1, also needs the hatch; "verifies zero rows" would have passed vacuously | `c12-exit-execute` states that the command sets `app.tenant_id` and `cw.maintenance` for its own session and that the function refuses a mismatched tenant; `NO FORCE` and `BYPASSRLS` are forbidden and searched for; and row counts are asserted before as well as after, table by table |
| MEDIUM — `ExportJobOut` lacked the `contentHash` and `downloadedAt` the Data screen, the exit export and the exit command all read | Both are in the schema in `c12-exports-contract-b`, with their null rules and two done-conditions |
| MEDIUM — VOC-S13's journey sat in `reports.journey.spec.ts` although the scenario is `taxonomy`'s (CLAUDE.md §10) | The block and the owned path move to `frontend/tests/e2e/taxonomy.journey.spec.ts` in `c12-fe-data-configuration` |
| MEDIUM — nothing said what happens to platform security-log rows naming the deleted users (recommendation 9) | `c12-exit-execute` deletes them with the tenant, in the same transaction, counted in the tombstone, with the reason and a done-condition; a row naming the kept name-only user stays |
| LOW — no per-task minute estimates and no stopping points | Every task carries `**Minutes:**`, and new rule 14 names the stopping point and the follow-on package for the seven longest, as `CHUNK8_TASKS.md` rule 11 does |
| Questions for Alex — three of the five were already decided | Only `TENANT_EXIT_RECORD_YEARS` with counsel's confirmation and the seven-day export life remain, beside q-retention-use and q-retention-period. Imported applicability as requests and the no-PDF committee pack are decided in `PARALLEL_PLAN.md` §7.2, the auditor's `exports.create` in `PRD.md` §6; the open-questions section says so |

**Moved into R2, 2026-09-25 (x-exports-contract, R2 wave 1).** The case file must export
(CAS-07), so the export half of `c12-exports-contract-a` and all of
`c12-exports-contract-b` are built ahead of the chunk: `ExportJob` and its migration
(`reports/0001_reports.py`), the four export operations, the runner in `reports/tasks.py`
and the registry in `reports/exporters/__init__.py` (not `reports/exports/`), with the
logic in `reports/jobs.py`. Three corrections: the storage seam is the existing
`apps/shared/storage.py`, which gained a streaming `open()`, and no
`apps/shared/adapters/storage.py` is added; `ImportJob`, `ImportKind` rows and the import
routes stay here for `c12-imports-contract` (REP-03, R3), which writes `ImportJob` in a
migration of its own; `export_job` is in the RLS guard's tenant-only list and `ExportKind`
and `JobStatus` were already in `apps/shared/kinds.py`. REP-S3 is un-skipped; REP-02 stays
pending and R3. What the chunk still does with these two tasks is nothing but the import
half of `-a`.

## Scope, rules and defaults

Chunk 12 plan: reports and exports, the spreadsheet register import, tenant
configuration, retention, and tenant exit. `Build_Plan.md` gives the chunk REP-01 to
REP-04, AUD-04 and VOC-09; PRD 0.4 rewrites AUD-04 (a record is deleted ten years after
its last use, D-53, ADR 0046) and REP-04 (two people, a read-only period, then deletion
of every tenant row including the audit trail, D-56, ADR 0049), and both are the only
named exceptions to "Nothing overwritten" in CLAUDE.md §5. The plan has 38 tasks in 11
waves, about 23 agent-hours of task work plus review, and no task above 40 minutes; each
task carries its estimate, and the seven above thirty minutes carry a stopping point
(rule 14).

PRECONDITIONS: WHAT MUST BE ON MAIN BEFORE WAVE 1
- **PRD 0.4.** `PRD.md` 0.4 with REP-04 and AUD-04 as rewritten, `docs/DECISIONS.md`
  D-48 to D-61, ADR 0046 and ADR 0049, the CLAUDE.md §5 exception lines, the reports and
  tenants `app.md` rewrites (REP-S5 rewritten, REP-S7, REP-S8, TEN-S12) and their
  scenario stubs. Everything in this brief is planned against that text, not against
  0.3. It is on `origin/claude/prd-0-4-consolidation-ueuqak` and merges before wave 1.
- **Hardening H-B and H-C.** H-B (the append-only hatch the app role cannot use) is on
  main (f336cce). H-C (mixed tables write only their own zone, and the hatch's
  allowlist) must be on main before `c12-ledger-purge-function`, because both change
  `migration_helpers.py` and the hatch predicate. If H-C has not landed when wave 3
  starts, `c12-ledger-purge-function` builds the allowlist itself, under the same
  security review, and says so; it never runs beside H-C.
- **Chunk 9** for what the exports and the dashboard read: `c9-case-contract`,
  `c9-assessment`, `c9-actions`, `c9-evidence` (the evidence rows and their files),
  `c9-signoff`, `c9-case-file`, `c9-scanner-adapter` (the upload scan `c12-imports-contract`
  calls) and `c9-e2e-seed`.
- **Chunk 8** for the register the inventory export, the dashboard and the import write:
  `c8-reg-status`, `c8-reg-entity-status`, `c8-reg-applicability`, `c8-reg-gaps`,
  `c8-ten-teams`, `c8-tenants-contract`, `c8-e2e-seed-register`, and `f03-T72` for the
  Statement of Applicability columns `f03-T83` exports.
- **Chunks 10 and 11** for what the configuration export carries and the exit mail uses:
  `c10-workflow-policy`, `c10-notifications-api`, `c10-comments-api`, `c10-mail-catalog`,
  `c11-security-policy`.
- **Chunks 3 to 7** for the library reads, the audit read, the AI log and the watch feed:
  `c3-provision-read`, `c3-no-tone`, `c4-close-a`, `c4-fe-audit-log`,
  `c5-cases-so-what-and-links`, `c5-watch-feed-read`, `c5-watch-sources-coverage`,
  `c5-ai-log-contract`, `c6-roadmap-backend`, `c7-ai-log-backend`.
- **`r1-readiness`**, before `c12-tenant-deleted-status` alone (parallel plan rule 11:
  it changes `authentication.py`, `tenancy.py` and `middleware.py`).
- Why it cannot wait: every number on the dashboard, every row in an export and every
  table the purge and the exit walk is a chunk 8, 9 or 10 table. An export built against
  a stub would ship a file with a bank's compliance figures missing from it, and the exit
  guard's job is to fail on a tenant table nobody covered.

WHAT IT DELIVERS
- **REP-01, the dashboard:** `GET /reports/summary`, `GET /reports/gaps` and
  `GET /reports/overdue-actions`, each a fan-out of independent queries under the 250 ms
  budget, filtered by the regulatory scope and by the reader's own permissions, in keys
  and counts and never a phrase.
- **REP-02, exports:** one `ExportJob` with `POST /exports` behind `exports.create` and a
  step-up, a status endpoint, and a download that streams through the API with an audit
  row (INPUT_DELTAS §4 removed `DownloadLink`). Builders for the inventory (with the
  dated Statement of Applicability, `f03-T83`), changes, cases, the audit log, the
  committee pack, the tenant configuration and the full tenant export.
- **REP-03, the register import:** `POST /imports` with a scanned upload, a dry run
  reporting creates, updates, conflicts and unknown values, a mapping asked once per
  value, and a commit in one audited transaction that files applicability as requests for
  a second person.
- **REP-04, tenant exit:** `tenant_exit_request` with a CHECK that the approver is not
  the requester, `closing` and `deleted` tenant statuses, the final export with its
  SHA-256, and `manage.py execute_tenant_exit` run by the operator as `cw_migrator`,
  which deletes every tenant row through an owner-only function and leaves a tombstone
  report.
- **AUD-04, retention:** the lifecycle registry with its guard, the ten-year age, the
  tenant's pause switch, one `SECURITY DEFINER` purge function owned by `cw_migrator`
  with a one-year floor, and a daily `@tenant_task` that writes one run row and one audit
  row with counts only.
- **VOC-09:** the tenant configuration snapshot with its version stamp, exported and
  imported with a dry run.
- The Reports screen, and the Admin data screen with its import, configuration, retention
  and exit panels; the chunk's own design cards, security review, fix task and close.

RULINGS WHERE THE SOURCES DISAGREE
1. **The hatch the purge uses is `current_user`, and the allowlist is structural.** ADR
   0046 wants a `SECURITY DEFINER` function owned by `cw_migrator` that opens the
   append-only hatch for its own statements; `HARDENING.md`'s H-C addendum would narrow
   the hatch to `session_user = <the migrator role>`, which a `SECURITY DEFINER` function
   called by the worker never satisfies (`session_user` stays `cw_app`; only
   `current_user` becomes the owner). Today's predicate on main is
   `current_setting('cw.maintenance') = 'on' AND current_user <> 'cw_app'`, which is too
   wide for the same reason H-C names. `c12-ledger-purge-function` sets it to
   `current_setting('cw.maintenance', true) = 'on' AND current_user = <the migrator
   role>` **and** adds the structural guard H-C asked for in its stronger form: a test
   that enumerates every `SECURITY DEFINER` function in the database and fails on any not
   in a named allowlist, and that each allowlisted one is owned by the migrator, has
   `search_path` pinned, has EXECUTE revoked from PUBLIC, and is granted only where this
   brief says. **H-C's second structural guard is re-homed here, not dropped:** the same
   task also proves that no foreign key into an append-only table carries a delete or
   update action (`ON DELETE CASCADE`, `SET NULL`, `SET DEFAULT` or any `ON UPDATE`
   action), because `c12-exit-execute` deletes whole tenant trees and a cascade into a
   ledger is exactly the silent rewrite the append-only guard exists to refuse. Only the
   `session_user` predicate of H-C's addendum is replaced, for the reason above. That is a
   guard change under parallel plan rule 8, so one task owns it and it gets a security
   review. The H-C row in `HARDENING.md` is updated with both facts — the predicate
   replaced, the foreign-key guard moved and where to — in that task's commit.
2. **The exit function is not `SECURITY DEFINER`.** `manage.py execute_tenant_exit` runs
   as `cw_migrator` in a one-off container, so `current_user` is already the owner and
   ruling 1's predicate lets it through. The function is owned by `cw_migrator`, EXECUTE
   is never granted to `cw_app`, and a test proves `cw_app` cannot call it. Nothing in the
   API or the worker holds migrator credentials, and `c12-ledger-purge-function` adds the
   `HARDENING.md` row that `MIGRATOR_DATABASE_URL` is unset before gunicorn and the worker
   start, with the boot test that proves it.
3. **Retention is one age, not three periods.** INPUT_DELTAS §7 plans `retentionYears`
   as `{cases, evidence, audit}` columns of the workflow policy, and the designed
   `TenantSettings.retentionYears` is an open map. D-53 replaces both: ten years after a
   record's last use, for everyone. The tenant carries a pause switch and nothing else,
   and there is no per-record legal hold, so `legal_hold` (`schema.sql` §15) is not built.
   `PUT /tenant/retention` takes `{paused, reason}` only.
4. **The pause is a governance row, not a column on `Tenant`.** The workflow policy sits
   behind chunk 10's `mig:shared` key and `c12-retention-contract-a` holds
   `mig:governance`; two packages may not write one app's migration directory (rule 7).
   The pause, the paused reason, who paused and when live on a `RetentionPolicy` row per
   tenant in `governance`, which is also where the screen and the audit row read them.
   INPUT_DELTAS gets the delta row with this reason.
5. **The lifecycle registry is one shared ledger, and it is a guard.** Ruling 36 of the
   parallel plan gives `c12-exit-export` and `c12-exit-deletion` a shared exception list.
   One registry serves retention and exit both (ADR 0046): `backend/apps/shared/lifecycle.py`
   maps every tenant table to `cases`, `evidence`, `audit`, `live` or `platform window`,
   with a kept-on-purpose list where each entry carries its reason. It is an append ledger
   (one row per table, never another task's row), and its guard test fails on any model
   carrying `tenant_id` or `owner_tenant_id` that is not in it, exactly as `tests_rls`
   does. The guard runs in every backend suite; `c12-close` and `c14-close` check it.
6. **`export_kind` gains `cases`, `configuration` and `tenant_export`, and a kind
   without a builder answers 501.** `schema.sql` lists five kinds; REP-S2 asks for a list
   of cases beside the single `case_file`, VOC-09 for the configuration and REP-04 for the
   full tenant export, so R3 needs eight. The contract declares all eight; `POST /exports`
   for a kind whose builder has not registered answers 501 `not_built` **before** a job row
   is written, naming the task that builds it, which is rule 3's stub shape for a job.
   `import_kind` gains `configuration` alongside `obligation_register`.
   The contract also adds `GET /exports`, which the designed contract lacks: without a list
   a person who reloads the page loses the job they started, and the Data screen could not
   find the final export again. It is paginated like every other list, gated by
   `exports.create`, and carries an INPUT_DELTAS row.
7. **Each export and import builder is a module the registry names, not an edit to
   `api.py`.** `reports/exports/__init__.py` and `reports/imports/__init__.py` hold one
   registry line per kind and are append ledgers. Only the four contract tasks hold
   `reportscore`; eight builder tasks run beside each other without it.
8. **`shared/adapters/storage.py` is built here.** Solution_Design names it the fifth
   seam and nothing has built it. `c12-exports-contract-a` is the first package that needs
   it and starts in wave 2 of the global plan, twenty-six waves before `c9-evidence`, so it
   builds the seam (`STORAGE_BACKEND`: local, s3; mock refused in production) and
   `c9-evidence` and `c9-case-file-export` use it. `c12-exit-execute` adds its list and
   delete operations.
9. **Ruling 7 of the parallel plan stands:** `c12-exports-contract-b` owns the job
   framework and `c9-case-file-export` is one builder on top of it, registered by chunk 9.
   `c9-case-file-export` therefore depends on `c12-exports-contract-b`, not on the whole
   chunk.
10. **REP-S5 is the PRD 0.4 text.** The 0.3 line "append-only tables keep their rows under
    retention" is gone: at exit the ledgers go with everything else (D-56). No task may
    re-add it, and `c12-exit-execute`'s test asserts zero rows in the audit table for the
    deleted tenant.

DEFAULTS TAKEN (each stated in its commit body, and copied into `docs/TODO_FOR_alex.md`
by `c12-close`)
- "Last use" is the latest of: the record's closure or dismissal, its removal, its last
  change, or a reference to it from a record that is still live. A read is not a use. It
  is computed by one function, `governance/last_use.py::last_use_at`, so a different
  answer is one function and its tests (open question 1).
- The ten years are one fixed period for every bank, from `RETENTION_YEARS` (a setting
  with an env override, so a test can pin it), not a per-tenant column (open question 2).
- The purge's cutoff may never be younger than `RETENTION_FLOOR_YEARS` (1), enforced
  inside the database function, not only in Python.
- `footprint_history` is kept for the tenant's life (it replays the regulatory scope as of
  a date) and library tables are never touched by the purge. Both are entries in the
  lifecycle registry with those reasons.
- Exports are gated by `exports.create` with a step-up on creation, and the download
  repeats the permission check and writes its own audit row; a download does not need a
  fresh step-up, because the file was already authorised and playbook 4.2 lists the
  export, not the download.
- An export file lives for `EXPORT_RETENTION_DAYS` (7) and is then deleted by the same
  daily job, with its row kept; the download of an expired export answers 409
  `export_expired`.
- The import is gated by `register.edit` **and** `vocab.manage` (the UI plan's row): it
  writes register rows and may create vocabulary values. It needs no step-up (playbook 4.2
  does not list it, and the dry run plus the commit is the second look).
- Imported applicability becomes applicability requests for a second person (parallel plan
  §7.2), never a decided applicability.
- An unknown value in the import is mapped to an existing key or suggested as a new
  vocabulary value; a suggestion is created through the vocabulary's own creation path so
  its near-duplicate check (AC-VOC3) still runs.
- The configuration export and import are export and import kinds, not new routes.
  Exporting the configuration needs `exports.create`. Importing it needs `vocab.manage`
  **and** `roles.manage` with a step-up, because the snapshot carries the tenant's roles
  and their permissions and committing it is a role and permission change, which
  CLAUDE.md §5 and playbook 4.2 put behind a passkey. The assertion id goes on the
  import's audit row. The register import keeps `register.edit` and `vocab.manage` with
  no step-up: it writes no role.
- The committee pack is the dashboard's figures plus the roadmap, the coverage and the
  open cases, rendered from `c10-mail-catalog`'s text in the tenant's default language,
  and exported as `txt` or `json`. No PDF library is added (parallel plan §7.2).
- Exit request, approval and cancellation are gated by `security.manage` with a step-up on
  each, and approving your own request answers 409 `four_eyes_violation`; the database
  CHECK refuses the row either way.
- While a tenant is `closing`, every mutating route answers 409 `tenant_closing` except
  sign-in, refresh, sign-out, step-up, revoking a session or an API key, exports,
  downloads and cancel (ADR 0049). The allowlist is a list in one module with a test that
  every route outside it is refused.
- The operator's out-of-band confirmation with the bank's contract contact is a runbook
  step, not a field: the command takes `--confirmed-with` and records the text in the
  tombstone.
- `TENANT_EXIT_DELAY_DAYS` is 30, `TENANT_EXIT_NOTICE_DAYS` is 7 (the second admin mail),
  and `TENANT_EXIT_RECORD_YEARS` is 10 with the figure marked for counsel.
- A former member still named by a library record keeps a user row with the name only and
  a unique placeholder email (`deleted+<uuid>@invalid`); every other user left with no
  membership and no platform role goes.
- The dashboard's tiles are each filtered by the reader's own permissions: a reader
  without `register.read` gets no gap figures, as null and not as zero, and the screen
  says the panel is permission-limited rather than showing a false zero.
- Every job is idempotent: a second run of the same export, import commit, purge or exit
  produces the same result and writes no second audit row.

CUT, WITH REASONS
- `legal_hold` and the per-record hold: ruling 3; D-53 replaces it with the tenant pause.
- `DownloadLink` and presigned downloads for exports: INPUT_DELTAS §4 removed them;
  downloads stream.
- Per-tenant retention periods, the 30-day shortening notice and the admin mail about a
  shortened period: all three belong to the recommendation Alex replaced with one fixed
  age (D-53).
- `TenantSettings.retentionYears`: ruling 3.
- A PDF export and a spreadsheet writer for the committee pack: no scenario asks for one,
  and no dependency is added beyond the reader `c12-deps-spreadsheets` needs.
- A scheduled rotation of export files into cold storage, an export archive list, and a
  "re-run this export" button: nothing asks for them.
- An automatic exit at the delay's end: ADR 0049 makes execution a deliberate operator
  step. A scheduled job that deletes a bank is exactly what two people are for.
- `POST /imports` from a URL, and an import of anything but the obligation register and
  the configuration: `import_kind` has two values.
- A console surface for exports, retention or exit: platform staff read a bank only
  through a support grant (D-49), and nothing here is a platform screen.
- A per-tenant export of another tenant's rows, "export everything for support": no
  route, ever.

PLAN-WIDE RULES
1. **Slots.** Every backend and E2E gate runs inside the task's slot: `set -a; . ./.env.worktree; set +a`.
   A cloud session runs `bash scripts/cloud-setup.sh` (with `--e2e` where the gates
   include E2E) instead.
2. **Generated files.** No task commits `openapi.json`, `frontend/src/types/api.generated.ts`
   or `frontend/tests/e2e/support/e2e-passkeys.generated.ts`. A task regenerates them
   locally to run `contract_drift.py` and the typecheck, then reverts them. The main agent
   regenerates and commits them at the merge, and regenerates the navigation and pill
   snapshot baselines when `registry.ts` or `tone-by-kind.ts` changed.
3. **The reports backend chain.** One task at a time owns `backend/apps/reports/api.py`,
   `schemas.py` and `tasks.py` (key `reportscore`), in this order:
   `c12-exports-contract-b`, `c12-dashboard-contract`, `c12-imports-contract`,
   `c12-exit-request`. Each writes its own operations once and sends each to a named
   function in the module that will build it, which answers 501 `not_built`. A logic task
   owns only its own module and its tests, never `api.py`. A logic task that finds the
   contract wrong stops and reports.
4. **Screens call no stub.** Each screen task depends on every backend task whose routes
   it calls, and every route it calls was declared by a contract task in an earlier wave.
5. **The admin data screen chain.** One task at a time owns `frontend/src/features/data/`
   and the `data` catalog namespace (key `datafe`), in this order:
   `c12-fe-data-retention`, `c12-fe-data-import`, `c12-fe-data-exit`,
   `c12-fe-data-configuration`. The reports screens hold `reportsfe` in the order
   `c12-fe-reports-dashboard`, `c12-fe-exports`.
6. **Append ledgers** (parallel plan rule 5, plus this chunk's own):
   `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`,
   `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`,
   `docs/plans/briefs/HARDENING.md`, `design/README.md` rows, the UI plan's ledger rows
   and status cells,
   `backend/config/settings.py` setting banners, `backend/.env.example`,
   `docs/runbooks/RAILWAY_VARIABLES.md`, router mounts in `backend/config/api.py`,
   `backend/apps/shared/kinds.py`, the route lists in `permissions.py`, the guarded-table
   lists in `tests_rls.py`, `tests_four_eyes.py` and `tests_seed_integrity.py`,
   `backend/apps/shared/e2e_seed.py`, `e2e_logins.py` and `e2e_passkeys.py` (one seed call
   or login per task), `frontend/src/shared/navigation/registry.ts` entries,
   `frontend/src/features/shared/tone-by-kind.ts` entries, each app's `app.md` status
   cells, each app's `tests_scenarios.py` skip lines (own line only),
   each `frontend/tests/e2e/*.journey.spec.ts` (own test blocks only), and this chunk's
   three registries: `backend/apps/shared/lifecycle.py`,
   `backend/apps/reports/exports/__init__.py` and `backend/apps/reports/imports/__init__.py`
   (one line per task). Adding a table to a guarded list or a registry is an append;
   adding an entry to an allowlist is a guard change under rule 8.
7. **Coverage floors.** `backend/scripts/coverage_gate.py` gets the chunk 12 floors once,
   from `c12-close`, measured at the close with the date beside each. A task states its
   own `coverage report --include` threshold in its done-condition and never lowers an
   existing floor.
8. **Security review before merge** for every task marked **Security review: yes**. A
   security-review sub-agent reads `git diff main...<branch>` with `tests_rls`,
   `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`,
   `tests_audit_on_write`, `tests_four_eyes`, `tests_database_role` and
   `tests_append_only`. `c12-security-review` is the chunk-wide sweep after the last
   backend merge, and `c12-review-fixes` closes its findings.
9. **Merge at once.** Each task is squash-merged and the full checklist run as soon as it
   passes review (WORKTREES step 5). Finished work never waits for the rest of the chunk.
10. **Clocks.** Everything dated is anchored to the tenant-local date plus a fixed wall
    time (CLAUDE.md §8.3 and §11). A retention test freezes the clock and moves it; no
    seed, fixture, test or journey may depend on the real "today", because a ten-year
    cutoff computed from the real clock makes a fixture pass this year and fail next.
11. **Cloud sessions stop on invariant questions** (parallel plan rule 12).
    `c12-tenant-deleted-status`, `c12-ledger-purge-function` and `c12-exit-execute` change
    a guard or the database's own refusals and carry that instruction explicitly.
12. **Nothing runs as the migrator inside a request.** No task adds `MIGRATOR_DATABASE_URL`
    to the API or the worker, and no task reads a tenant table from a platform session.
    Two shapes are refused outright in review: a policy on a tenant table keyed on a
    session flag, and a second database alias in `settings.DATABASES` for anything the API
    calls.
13. **Scenario ownership.** Exactly one task un-skips each integration test and one
    un-fixmes each journey (the table below).
14. **Minutes, and where to stop.** Every task carries a `**Minutes:**` estimate of its
    own work, excluding review and merge; they total about 23 agent-hours and none is
    above 40. A task past about thirty minutes is the one likely to run out of room, so
    the seven longest — each estimated at 40, each with two halves that separate cleanly —
    name the green point they stop at and the package the rest becomes, exactly as
    `CHUNK8_TASKS.md` rule 11 does. A sub-agent that reaches a stopping point commits what
    is green, opens the named package and reports; it never carries an unfinished guard,
    an unfinished migration or an un-run gate past it. Any other task that overruns stops
    at its own last green gate and reports under the same rule:
    - `c12-exports-contract-a`: stop once `ExportJob` and `ImportJob` are green with
      their RLS and audit tests; the storage seam (`shared/adapters/storage.py`, ruling 8)
      becomes `c12-exports-contract-a-b` and keeps `mig:reports` free.
    - `c12-exports-contract-b`: stop once the four operations, the registry and the 501
      answer are green; the runner in `tasks.py`, the streamed download and its audit row
      become `c12-exports-contract-c`.
    - `c12-tenant-deleted-status`: stop once `closing` and its allowlist are green over
      the whole route table; `deleted` (the 404 sign-in and the refused sessions) becomes
      `c12-tenant-deleted-status-b`.
    - `c12-ledger-purge-function`: stop once the hatch allowlist and the two structural
      guards (`SECURITY DEFINER` and the foreign-key actions, ruling 1) are green; the
      purge function itself and AUD-S8 become `c12-ledger-purge-function-b`. Both halves
      keep the security review and the stop-and-report instruction.
    - `c12-exit-request`: stop once the table, its CHECK, the four routes and REP-S7 are
      green; the three admin mails and TEN-S12 become `c12-exit-request-b`.
    - `c12-e2e-seed`: stop once the exports, the retention rows and the logins are seeded
      and idempotent; the spreadsheet fixture and the approved exit request on the second
      tenant become `c12-e2e-seed-b`.
    - `c12-exit-execute`: stop once the function, its session rules and the before-and-
      after row counts are green; the command, the tombstone, the storage prefix and the
      runbook become `c12-exit-execute-b`. The deletion never ships half-built: if the
      stop falls here, no operator path exists yet, which is the safe half to leave.

SCENARIO OWNERSHIP

| Scenario | `@integration` | `@e2e` |
|---|---|---|
| REP-S1 | `c12-dashboard-workload` (`c12-dashboard-summary` contributes) | `c12-fe-reports-dashboard` |
| REP-S2 | `c12-committee-pack` | `c12-fe-exports` |
| REP-S3 | `c12-exports-contract-b` | — |
| REP-S4 | `c12-import-register-commit` (`c12-import-register-dryrun` contributes) | `c12-fe-data-import` |
| REP-S5 | `c12-exit-execute` | `c12-fe-data-exit` |
| REP-S6 | `f03-T83` | — |
| REP-S7 | `c12-exit-request` | — |
| REP-S8 | `c12-exit-execute` | — |
| AUD-S6 (rewritten) | `c12-retention-purge` | — |
| AUD-S8 (in PRD 0.4, ledger purge) | `c12-ledger-purge-function` | — |
| AUD-S9 (new, the retention screen) | `c12-retention-contract-b` | `c12-fe-data-retention` |
| VOC-S13 (gains `@e2e`) | `c12-config-jobs` (`c12-config-logic` and `c12-config-policies` contribute) | `c12-fe-data-configuration` |
| TEN-S12 | `c12-exit-request` | — |

`c12-exports-contract-a`, `c12-dashboard-contract`, `c12-imports-contract`,
`c12-retention-contract-a`, `c12-tenant-deleted-status`,
`c12-deps-spreadsheets`, `c12-e2e-seed`, the two design cards and the four export
builders contribute to scenarios and un-skip none. AUD-S8 is PRD 0.4's own ledger-purge
scenario with a stub already in `governance/tests_scenarios.py`; AUD-S9 is the one new
scenario this chunk writes, for the retention screen. AUD-S5 (the problem-report loop) is
chunk 5's re-check under D-50 and is not touched here. CAS-S11 (the case file) stays
chunk 9's.

CHANGES FROM `PARALLEL_PLAN.md`, WITH REASONS
- **`c12-exit-deletion` becomes `c12-exit-request` and `c12-exit-execute`**, as ADR 0049's
  implementation plan says. One task cannot hold the four-eyes request table, the routes,
  the mail, the owner-only function, the management command, the tombstone, the storage
  list and the runbook inside sixty minutes, and the two halves have different reviews:
  one is a four-eyes API, the other is a deletion that cannot be undone.
- **`c12-ledger-purge-function` is added**, as ADR 0046's tranche 2 says, and it is the
  chunk's only guard change (ruling 1). Splitting it out keeps the purge job itself an
  ordinary Python task.
- **`c12-exports-contract` splits into `-a` (the data layer and the storage seam) and
  `-b` (the routes and the runner)**, and **`c12-retention-contract` into `-a` (models,
  the lifecycle registry and its guard) and `-b` (the policy routes)**. Both were 60 and
  45 minutes with two unrelated review surfaces; the split also lets `-a` take
  `mig:reports` and `mig:governance` early while `-b` waits for the contract chain.
- **`c12-dashboard-api` becomes `c12-dashboard-contract`, `c12-dashboard-summary` and
  `c12-dashboard-workload`.** Sixty minutes across eight tiles reading five apps is two
  tasks of work and one contract; the contract also has to land before
  `c12-fe-reports-dashboard` can be planned against real routes (rule 4).
- **`c12-import-register` becomes `c12-import-register-dryrun` and
  `-commit`.** The dry run (parse, match, report) and the commit (one audited
  transaction, applicability as requests) are separately testable and were 60 minutes
  together.
- **`c12-card-data` becomes `-a` (import and configuration) and `-b` (retention and
  exit).** One 60-minute card gating four screens is the coupling the chunk 8 review
  called out; the split lets the retention panel start two waves earlier.
- **`c12-e2e-seed` is added.** Four journeys need a spreadsheet fixture, a finished export,
  an approved exit request and a purgeable record, and `c9-e2e-seed` and
  `c8-e2e-seed-register` seed none of them. Without it each screen task would extend the
  seed in its own wave, which rule 6 allows only one call at a time and which would put
  three journey tasks on `e2e_seed.py` at once.
- **`c12-imports-contract` loses its migration.** `ImportJob` lands in
  `c12-exports-contract-a` with `ExportJob`, because rule 7 allows one task at a time in
  an app's migration directory and two tables in one first migration cost nothing.
  `c12-imports-contract` keeps `reportscore` and the routes.
- **`c12-config-logic` loses `c3-no-tone` from its depends-on** (that package only owns
  `shared/schemas.py` and the proposal tone rule, neither of which the configuration
  snapshot reads) and gains `c10-workflow-policy` for the policy shape it stamps.
- **`c14-assurance-exit-controls` reads `c12-exit-request` and `c12-exit-execute`** where
  `PARALLEL_PLAN.md` gives it `c12-exit-deletion`. The chunk 14 planner takes the two ids
  from here.
- **`GET /exports` is added to the contract** (ruling 6), which the designed contract and
  the parallel plan's package list both lack.
- **`f03-T83` owns only `reports/exports/inventory.py` and its tests.** Under ruling 7 it
  needs no route and no schema change, so it loses `reportscore` and runs beside the other
  builders.

CHANGES FROM THE TWO CRITIQUES
- Parallelism: the builder registries and the `reports/exports/` module per kind, so only
  four tasks hold `reportscore` instead of nine; the `datafe` and `reportsfe` chains
  written out in order, because six frontend tasks would otherwise have collided on one
  feature directory and one catalog namespace; `c12-card-data` split, so the retention
  panel does not wait for the exit card; `mig:shared` given to `c12-tenant-deleted-status`
  in wave 2 and `c12-ledger-purge-function` in wave 3, never the same wave;
  `c12-export-inventory` and `f03-T83` put in different waves because both write
  `exports/inventory.py`; `c12-e2e-seed` added and placed before the first journey.
  The second pass then moved `c12-fe-data-retention` from wave 5 to wave 6, because it
  depended on `c12-e2e-seed` in its own wave, which the start rule forbids; added
  `design/README.md` to the ledger list, since both design cards add a row to it in wave 1;
  and confirmed that the three tasks appending to `reports/exports/__init__.py` in wave 6
  and the three touching `reports/tests_scenarios.py` in wave 5 are appends by rule 6 and
  not collisions.
- Coverage: nothing owned the `tenant_export` and `configuration` export kinds (ruling 6);
  nothing built `shared/adapters/storage.py` (ruling 8); the lifecycle registry had two
  owners and no guard (ruling 5); the retention pause had nowhere to live that did not
  collide with chunk 10's key (ruling 4); the purge could not have deleted an audit row
  under H-C's hatch (ruling 1); REP-S5's 0.3 wording contradicts D-56 (ruling 10); the
  retention and configuration screens had no scenario to prove them, so AUD-S9 is added
  and VOC-S13 gains an `@e2e` half; the download of an expired export had no answer; and
  no task proved that a `closing` tenant still lets its people sign in and download, which
  TEN-S12 now covers. The second pass found three more: `export_kind` had no `cases` value
  although REP-S2 exports a list of cases beside the single case file; no route listed a
  tenant's exports, so a reloaded page lost a running job and the Data screen could not
  find the final export again (both ruling 6); and `c12-exit-execute` would have added its
  function to the `SECURITY DEFINER` allowlist, a guard change it does not need, because
  `cw_delete_tenant` is not `SECURITY DEFINER` (ruling 2) — it asserts that instead. It
  also gave the expiry of an export file an owner in `c12-retention-purge`, which nothing
  had.

## Waves

Tasks in one wave have disjoint owned paths and share no serialization key.

1. `c12-exports-contract-a`, `c12-card-reports`, `c12-card-data-a`, `c12-deps-spreadsheets`, `c12-config-logic`
2. `c12-exports-contract-b`, `c12-card-data-b`, `c12-retention-contract-a`, `c12-tenant-deleted-status`
3. `c12-dashboard-contract`, `c12-retention-contract-b`, `c12-export-audit-log`, `c12-ledger-purge-function`
4. `c12-imports-contract`, `c12-dashboard-summary`, `c12-export-inventory`, `c12-config-policies`, `c12-retention-purge`
5. `c12-dashboard-workload`, `c12-export-changes-cases`, `c12-exit-request`, `c12-e2e-seed`, `f03-T83`
6. `c12-import-register-dryrun`, `c12-committee-pack`, `c12-exit-export`, `c12-fe-reports-dashboard`, `c12-fe-data-retention`
7. `c12-import-register-commit`, `c12-exit-execute`, `c12-config-jobs`, `c12-fe-exports`
8. `c12-fe-data-import`, `c12-security-review`
9. `c12-fe-data-exit`, `c12-review-fixes`
10. `c12-fe-data-configuration`
11. `c12-close`

If H-C has not merged when wave 3 starts, `c12-ledger-purge-function` runs alone in its
wave (ruling 1) and `c12-retention-purge` moves to wave 5. Nothing else moves.

## Open questions

Both questions below are the details `docs/DECISIONS.md` D-53 marks open. Everything else
in this chunk is answered by D-49 to D-56, ADR 0046 and ADR 0049, and is taken as written.

- **q-retention-use (a product invariant is at stake: the exception to "nothing
  overwritten" is bounded by this definition, so it is Alex's).** What counts as a
  record's "use", after which the ten years run?

  Option A (recommended, and D-53's own proposal): the latest of the record's closure or
  dismissal, its removal, its last change, or a reference to it from a record that is
  still live. A read is not a use. It keeps a case that a live obligation still cites out
  of the purge, it needs no new column on anything but the tables that already carry
  `closed_at`, `removed_at` and `updated_at`, and it cannot be extended by a person
  opening a record, which would make retention unpredictable.

  Option B: closure alone. Simpler to compute and to explain, but a closed case that a
  live gap still points at would be deleted under the live record's feet, and the
  reference would dangle.

  Option C: any touch, reads included. It makes the period unbounded in practice: one
  auditor opening a case resets ten years, which is the opposite of keeping personal data
  no longer than necessary.

  **Nothing waits.** The build takes Option A, confined to one function,
  `governance/last_use.py::last_use_at`, with one test per table. A different answer is a
  change to that function and its tests, not to the job, the database function or the
  screen.

- **q-retention-period (a product invariant: it is the number CLAUDE.md §5's exception is
  written around).** May a bank change the ten years?

  Option A (recommended, and D-53's own proposal): no. One fixed period for every bank,
  from `RETENTION_YEARS`, which a deployment can set and a test can pin but no tenant route
  can. It is one number to explain in the DPA and to test, and it keeps a bank from
  setting a period that outlives the purpose the data was kept for.

  Option B: a per-tenant period inside fixed bounds (1 to 30 years), which is what the
  recommendation offered before Alex answered "10 yrs after last use". It brings back a
  column, a step-up route, the shortening notice and the revert, all of which this plan
  cuts.

  **Nothing waits.** The build takes Option A. If Alex later wants Option B, the change is
  the setting becoming a column on the `RetentionPolicy` row that ruling 4 already builds,
  plus the notice; no ledger, function or job changes.

- Non-blocking, to confirm (defaults are taken and the build does not wait), written into
  `docs/TODO_FOR_alex.md` by `c12-close`: that `TENANT_EXIT_RECORD_YEARS` is 10 and that
  counsel confirms the tombstone's legitimate-interest basis (ADR 0049 already lists it);
  and that an export file is deleted after seven days while its row and audit trail stay.
  Nothing else on this list: three items an earlier draft carried are already decided and
  are not asked again. Imported applicability becomes requests for a second person and the
  committee pack is text and JSON with no PDF, both decided in `PARALLEL_PLAN.md` §7.2;
  a bank's own auditor may create exports, decided in `PRD.md` §6, which grants the
  `auditor` role `exports.create`. Each is a default of this brief, not a question.
- Rejected, from the parallelism critique: merging `c12-dashboard-summary` and
  `c12-dashboard-workload` into one task because both read cases. They own different
  modules, read different apps and together exceed the sixty-minute limit; the contract
  task removes the only file they would have shared.
- Rejected, from the coverage critique: giving the purge a "dry run" mode on a deployed
  environment so an admin can see what would go. It would need a second code path through
  the same function with the hatch open, and the run row plus the counts already say what
  went. The Data screen shows the last run instead.
- Rejected, from the coverage critique: having `c12-exit-execute` keep the audit rows of
  the deleted tenant "for the platform's own assurance". D-56 and ADR 0049 decided the
  opposite, and the tombstone's counts are what the assurance pack points at.

## Tasks

### c12-exports-contract-a: the job tables and the storage seam

**Requirements:** REP-02, REP-03
**Scenarios:** none
**Depends on:** `c8-tenants-contract`
**Security review:** yes (two new tenant tables and a new outbound seam)
**Minutes:** 40 (stopping point in rule 14)

Add `backend/apps/reports/models.py` and `migrations/0001_reports.py` from
`docs/inputs/schema.sql` §10 and `data-model.md`:
- `ExportJob(TenantModel)`: `kind` (`ExportKind`), `subject_id` (nullable uuid),
  `format`, `filters` (`JSONField` with the named `ExportFilters` schema and the inline
  suppression naming it), `status` (`JobStatus`), `storage_key` (nullable),
  `content_hash` (nullable, the SHA-256 of the produced file), `requested_by`,
  `created_at`, `completed_at`, `expires_at`, `downloaded_at`, `error`,
  `Meta.ordering = ["-created_at"]`.
- `ImportJob(TenantModel)`: `kind` (`ImportKind`), `storage_key`, `mapping`
  (`JSONField` with the named `ImportMapping` schema), `dry_run`, `status`, `result`
  (`JSONField` with the named `ImportResult` schema), `requested_by`, `created_at`,
  `completed_at`, `Meta.ordering = ["-created_at"]`.
The migration applies `migration_helpers.rls_operations()` to both tables. Neither is
append-only: a job row moves through its statuses.

Add `backend/apps/shared/adapters/storage.py`, the fifth seam of `Solution_Design.md`:
one interface (`put`, `open`, `delete`, `exists`) with a deterministic in-memory mock and
a local-directory and an S3 provider chosen by `STORAGE_BACKEND` (`mock`, `local`, `s3`),
with `STORAGE_BUCKET`, `STORAGE_PREFIX` and `STORAGE_REGION` as settings with env
overrides. The production boot refuses `mock` through the guard that already refuses the
other mocks; this task adds the entry, not a new guard. A key is built from the tenant id
and the job id and never from anything a person typed.

Also: add `ExportKind` (`case_file`, `cases`, `committee_pack`, `inventory`, `changes`,
`audit_log`, `configuration`, `tenant_export`) and `ImportKind`
(`obligation_register`, `configuration`) rows to `apps/shared/kinds.py` with the
INPUT_DELTAS reason (ruling 6); add both tables to the guarded-table list in
`apps/shared/tests_rls.py`; write the INPUT_DELTAS rows for ruling 6 and ruling 8.

**Owned paths:**

- `backend/apps/reports/models.py`
- `backend/apps/reports/migrations/0001_reports.py`
- `backend/apps/reports/tests_models.py`
- `backend/apps/shared/adapters/storage.py`
- `backend/apps/shared/tests_storage.py`
- `backend/apps/shared/kinds.py` (its own entries)
- `backend/apps/shared/tests_rls.py` (the guarded-table list only)
- `backend/config/settings.py` (its own setting banner)
- `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the whole graph.
- The RLS guard lists `export_job` and `import_job` as forced tenant-only, and a
  cross-tenant read returns nothing under `cw_app`.
- The storage mock round-trips a file, `delete` is idempotent, and a key for tenant A can
  never be produced for tenant B (a test over the key builder).
- A boot with `STORAGE_BACKEND=mock` outside `test` is refused by the production guard.
- No filename, path or key carries text a person typed; a test plants a traversal
  attempt and proves the key is unchanged.
- `JSONField` carries its named schema and its suppression; the compliance lint is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.reports apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/*,apps/shared/adapters/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Tenant tables carry `tenant_id` under enabled and forced row-level security; `cw_app`
  cannot bypass it.
- snake_case columns; `Meta.ordering` on anything `.first()`ed; `JSONField` only with a
  named schema.
- Tenant content never reaches a log, Sentry or an unapproved endpoint: the storage
  provider logs a key and a byte count, never a file name or its contents.
- Enums in code are for kinds only.

### c12-card-reports: the Reports screen card

**Requirements:** REP-01, REP-02
**Scenarios:** none
**Depends on:** `c4-console-shell` (the shell the card is cut against)
**Minutes:** 30

Cut `design/screens/tenant-reports.html` from `design/prototype/index.html`'s `vReports()`
(playbook Section 7, step 4), in the foundations of `design/system/foundations.md` and the
rail and tab bar of `system/navigation.md`. The card shows: the four figures (open
changes, overdue actions, obligations with a gap, unconfirmed AI drafts), open changes by
urgency, the regime-by-account heat table, source coverage, compliance status of
applicable obligations, the gap rows, overdue actions, and the two controls "Show
committee pack" and the export menu (inventory, changes, cases, audit log, configuration).

The card decides look, wording and flow only, never the rules. It states in its header
comment: every figure is a count from its own endpoint; a panel the reader's permissions
do not cover is absent with a one-line notice, never a zero; the pills are the six tones
through their kinds; and the export controls lead to a step-up.

**Owned paths:**

- `design/screens/tenant-reports.html`
- `design/README.md` (its own row)
- `docs/plans/UI_Implementation_Plan.md` (its own ledger row)

**Done when:**

- The card renders in light and dark at 375 px and at desktop width with no horizontal
  scroll, and every pair passes WCAG AA.
- Every pill on it is one of the six tones and is chosen by slot or kind.
- Every string is screen copy: no requirement id, no restated invariant, no key.
- The UI plan's `tenant-reports.html` row moves from "card pending" to "designed", naming
  this task.

**Gates:**

- Open the card in a browser at both widths and both themes (the card is static HTML; no
  backend gate applies).
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- The prototype decides how things look, read and flow, never what the rules are.
- Six pill tones, chosen by slot or kind, never by a person.
- Typography roles only; screen copy says what the user is doing.

### c12-card-data-a: the Admin data card, import and configuration

**Requirements:** REP-03, VOC-09
**Scenarios:** none
**Depends on:** `c4-console-shell`
**Minutes:** 30

Create `design/screens/admin-data.html` with the shell, the page head and the first two
panels (the prototype has no Data screen, so this is designed from the requirements and
the existing admin cards, `admin-security-log.html` and `admin-footprint.html`, for
structure):
- **Import a register:** the file field with what is accepted and the size cap, the dry
  run's summary (created, updated, conflicts, unknown values), the one-question-per-value
  mapping list with "use an existing value" and "suggest a new one", the row errors with
  their line numbers, and Commit with what it will write spelled out.
- **Configuration:** what a configuration export contains in plain words, Export, and an
  import with its dry run and its conflicts.
It states in its header comment that the import asks each unknown value once, that a
commit writes applicability as requests for a second person, and that nothing on the
screen shows another tenant's data.

**Owned paths:**

- `design/screens/admin-data.html` (the shell, the head and the two panels only)
- `design/README.md` (its own row)
- `docs/plans/UI_Implementation_Plan.md` (its own ledger row)

**Done when:**

- The card renders in light and dark at 375 px and at desktop width.
- The mapping question reads as one question about one value, not a spreadsheet of them.
- The card leaves the retention and exit panels to `c12-card-data-b`, marked with one
  comment line, so the two tasks never edit the same block.
- Every string is screen copy, and the file-size and type limits are named in words.

**Gates:**

- Open the card in a browser at both widths and both themes.
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- The design decides look and flow, never the rules.
- Six pill tones by slot or kind; typography roles only.

### c12-deps-spreadsheets: the spreadsheet reader

**Requirements:** REP-03
**Scenarios:** none
**Depends on:** `r1-readiness`
**Lane:** local only (key `deps`; a cloud session may not change dependencies)
**Minutes:** 30

Add exactly one runtime dependency for reading `.xlsx`, pinned exactly, chosen by reading
the provider's own current documentation and recording it in
`docs/plans/Verification_Log.md` with the URL and the date. Nothing else changes: no
writer, no PDF library, no pandas.

Also add the parsing limits as settings with env overrides: `IMPORT_FILE_MAX_MB` (10),
`IMPORT_MAX_ROWS` (5000), `IMPORT_MAX_COLUMNS` (60), so a crafted file cannot exhaust the
worker.

**Owned paths:**

- `backend/pyproject.toml`, `backend/poetry.lock`
- `backend/config/settings.py` (its own setting banner)
- `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`
- `backend/apps/shared/tests_dependencies.py` (a new test class only)
- `docs/plans/Verification_Log.md`

**Done when:**

- `poetry lock --check` passes and the image builds.
- `osv-scanner`, `npm audit` (unchanged) and the licence gate are green, and Trivy on both
  images reports nothing new at HIGH or CRITICAL.
- A test opens a small fixture workbook and reads its rows; a file above the cap and a
  sheet above the row cap are both refused with a user-facing message, not an exception.
- The Verification log row names the version, the source URL and the date it was read.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh install && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `bash scripts/prepush.sh --all` (a dependency change runs every gate, including the
  scanners and both images)

**Invariants:**

- Fetch provider documentation, never recall it, and log it in the Verification log.
- Every threshold is a setting with an env override.
- One dependency change per ship.

### c12-config-logic: the tenant configuration snapshot

**Requirements:** VOC-09
**Scenarios:** contributes to VOC-S13, which `c12-config-jobs` un-skips
**Depends on:** `c8-vocab-scales-reasons`, `c10-workflow-policy`, `c4-second-editor` (the tenant roles it stamps)
**Minutes:** 40

Build `backend/apps/taxonomy/configuration.py`: one function that produces the tenant's
configuration as a snapshot, and one that reads a snapshot back as a plan of creates,
updates and conflicts without writing anything.
- The snapshot is keyed by immutable keys, never by id or label: vocabulary lists and
  their rows (key, kind, label per language, usage note, sort order, active), tenant
  roles and their permissions, the scales and reason lists, and a `version` stamp
  (`{schemaVersion, exportedAt, tenantSlug}`). Labels travel as text; keys are what an
  import matches on. The roles and their permissions are why committing a configuration
  snapshot is a role and permission change: `c12-imports-contract` gates that commit on
  `roles.manage` with a step-up, and `c12-config-jobs` builds it.
- The read-back reports, per row: `create`, `update`, `conflict` (the key exists with a
  different kind, or a system row would be changed in a way VOC-S14 refuses) or
  `unchanged`. It writes nothing and needs no transaction.
- Nothing tenant-identifying beyond the slug, and no member names, travel in a snapshot.

**Owned paths:**

- `backend/apps/taxonomy/configuration.py`
- `backend/apps/taxonomy/tests_configuration.py`
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- A snapshot of the seeded tenant round-trips: read back into the same tenant it reports
  every row `unchanged`.
- Read back into a second tenant it reports creates and no conflicts, and into a tenant
  with a clashing key of another kind it reports that row as a conflict.
- A system row's retire or reorder is reported as a conflict, never as an update
  (VOC-S14).
- The snapshot carries keys only: a test asserts no uuid and no label-as-identifier
  anywhere in it.
- The functions write nothing: an audit-on-write test proves a read produces no row.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/taxonomy/configuration.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Store and compare keys, never labels; the API returns `key` and `kind`.
- A read writes nothing and records nothing.
- Tenant content never reaches a log.

### c12-exports-contract-b: the export routes, the runner and the kind registry

**Requirements:** REP-02
**Scenarios:** REP-S3 (un-skipped)
**Depends on:** `c12-exports-contract-a`
**Security review:** yes (a step-up, a download that streams tenant files)
**Minutes:** 40 (stopping point in rule 14)

Write `backend/apps/reports/api.py`, `schemas.py` and `tasks.py` once for the export half,
and mount the router in `config/api.py`:

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `createExport` | `POST /exports` | SessionAuth, `exports.create`, `@requires_step_up` | `reports/jobs.py` |
| `listExports` | `GET /exports` | SessionAuth, `exports.create` | `reports/jobs.py` |
| `getExport` | `GET /exports/{exportId}` | SessionAuth, `exports.create` | `reports/jobs.py` |
| `downloadExport` | `GET /exports/{exportId}/download` | SessionAuth, `exports.create` | `reports/jobs.py` |

- Schemas, camelCase through `CamelSchema`: `ExportInput` = `{kind, subjectId?, format,
  filters?}`; `ExportFilters` = the named, typed shape every builder shares
  (`instrumentKey?`, `entityId?`, `standardEdition?`, `from?`, `to?`, `statusKeys?`), so
  no later task changes the schema (ruling 7); `ExportJobOut` = `{id, kind, subjectId,
  format, status, createdAt, completedAt, expiresAt, contentHash, downloadedAt, error}`,
  where `contentHash` is the produced file's SHA-256 and `downloadedAt` the first
  download, both null until the job completes and is first downloaded — the Data screen
  shows the final export's checksum and `c12-exit-execute` refuses an export nobody has
  downloaded, and neither can read a column the contract does not return; `GET /exports`
  answers the
  shared page shape (default 20, max 100), newest first. No `DownloadLink`
  (INPUT_DELTAS §4), and the INPUT_DELTAS row records the added list (ruling 6).
- `reports/jobs.py` creates the row, queues the task and answers 202. A kind whose builder
  is not registered answers 501 `not_built` naming its task, **before** a row is written
  (ruling 6). A format the kind does not offer answers 422.
- `reports/exports/__init__.py` is the registry: `register(kind, builder)` and a lookup;
  it is an append ledger and holds no builder of its own.
- `reports/tasks.py` holds the one `@tenant_task` that runs a job: it calls the builder,
  writes the file through the storage seam, stores the key, the SHA-256 and `expires_at`
  (`EXPORT_RETENTION_DAYS`, 7), and sets `failed` with a user-facing `error` on a
  builder's `ValidationError`. It is idempotent: a second run of a completed job changes
  nothing.
- The download streams the file through the API with the permission checked again, writes
  one `record()` audit row naming the export, its kind and the person, and answers 409
  `export_expired` once `expires_at` has passed and 404 for another tenant's job.
- Un-skip REP-S3 and delete the four operations' lines from `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/reports/api.py`, `schemas.py`, `jobs.py`, `tasks.py`
- `backend/apps/reports/exports/__init__.py`
- `backend/apps/reports/tests_jobs.py`, `tests_contract.py`
- `backend/apps/reports/tests_scenarios.py` (the REP-S3 skip line and body only)
- `backend/apps/reports/app.md` (its own status cells)
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/config/api.py` (the router mount only)
- `backend/config/settings.py` (its own banner), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`
- `backend/scripts/contract_drift_pending.txt` (its own lines)

**Done when:**

- REP-S3 is green: without a fresh assertion the request answers 403 `step_up_required`;
  with one it answers 202 with a job id, and the file is produced by the worker, never in
  the request.
- A request never builds a file: a test asserts the response returns before the builder
  runs, and the route holds to the 250 ms budget.
- Every unregistered kind answers 501 `not_built` and writes no row.
- Tenant B gets 404 for tenant A's job, its status and its download.
- The download writes exactly one audit row, streams rather than loading the file into
  memory, answers 409 for an expired export, and sets `downloaded_at` on the first
  download only.
- A completed job answers with its `contentHash`, and `downloadedAt` is null before the
  first download and fixed afterwards, so the screen can show a checksum and
  `c12-exit-execute` can require a download.
- The Celery registration guard sees the task, and `@tenant_task` activates the tenant.
- `contract_drift.py` reports the four operations as delivered, and `GET /exports`
  lists only the caller's own tenant's jobs, paginated.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/*' (api.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only; do not commit `openapi.json` or `api.generated.ts`

**Invariants:**

- No logic in `api.py`; no `Dict[str, Any]`; no `*args`/`**kwargs`.
- A step-up on export creation (playbook 4.2), and `record()` on every write, in the same
  transaction.
- Exports stream through permission checks (playbook 4.6); a trace never leaves, and
  errors are RFC 9457 with a `code`.
- `tenancy.activate()` after auth; `@tenant_task` in the worker.

### c12-card-data-b: the Admin data card, retention and exit

**Requirements:** AUD-04, REP-04
**Scenarios:** none
**Depends on:** `c12-card-data-a`
**Minutes:** 25

Add the last two panels to `design/screens/admin-data.html`:
- **Retention:** the fixed period in plain words ("we delete a record ten years after it
  was last used"), what that covers and what it never touches, the last run with its date
  and counts, and Pause with its reason field and its Resume, both behind a passkey.
- **Leaving bleqq:** what exit does, in the order it happens (request, a second admin
  approves, the tenant goes read-only, the final export, then deletion of everything
  including the audit trail), who can cancel and until when, the final export's download
  and its checksum, and the tombstone that remains. The panel states that deletion cannot
  be undone and that two different people are needed.

**Owned paths:**

- `design/screens/admin-data.html` (the two new panels only)
- `docs/plans/UI_Implementation_Plan.md` (its own ledger row)

**Done when:**

- Both panels render in light and dark at 375 px and at desktop width.
- The exit panel names the two people, the read-only period and the deletion of the audit
  trail in the bank's own words, with no requirement id and no invariant text.
- The retention panel shows the last run and the pause state, and never offers a period
  to edit (ruling 3).
- The card leaves `c12-card-data-a`'s two panels untouched.

**Gates:**

- Open the card in a browser at both widths and both themes.
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- The design decides look and flow, never the rules.
- Screen copy says what the user is doing; six tones by slot or kind.

### c12-retention-contract-a: the lifecycle registry, the policy row and the run row

**Requirements:** AUD-04
**Scenarios:** none
**Depends on:** `c5-ai-log-contract`, `c7-ai-log-backend`, `c9-evidence`, `c10-collab-models`
**Security review:** yes (a registry that decides what may be deleted)
**Minutes:** 35

Add to `backend/apps/governance/`:
- `RetentionPolicy(TenantModel)`: one row per tenant, `paused_at`, `paused_by`,
  `paused_reason`, `updated_at`, unique on `tenant` (ruling 4). No period column.
- `RetentionRun(TenantModel)`: `run_at`, `policy` (`JSONField` with its named schema:
  the age and the pause state as they were), `deleted_counts` (`JSONField`, named
  schema: table to count), `status` (`JobStatus`), `Meta.ordering = ["-run_at"]`.
- The migration applies `rls_operations()` to both.

Add `backend/apps/shared/lifecycle.py` (ruling 5): one entry per table carrying
`tenant_id` or `owner_tenant_id`, mapping it to `cases`, `evidence`, `audit`, `live` or
`platform window`, plus a `kept` list where each entry carries its reason
(`footprint_history`: it replays the regulatory scope as of a date; the library tables:
they are not the tenant's). Its guard test, in `apps/shared/tests_lifecycle.py`, walks
every model and fails on one that is in neither list, naming it. The file and its lists
are append ledgers from here on.

**Owned paths:**

- `backend/apps/governance/models.py`
- `backend/apps/governance/migrations/000X_retention.py`
- `backend/apps/governance/tests_retention_models.py`
- `backend/apps/shared/lifecycle.py`
- `backend/apps/shared/tests_lifecycle.py`
- `backend/apps/shared/tests_rls.py` (the guarded-table list only)
- `backend/apps/shared/kinds.py` (its own entry)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- `makemigrations --check` is clean and `migrate_from_zero` applies the graph.
- The RLS guard lists both tables as forced tenant-only.
- The lifecycle guard fails on a planted model with `tenant_id` that is in neither list,
  and is green on the tree as it stands; every `kept` entry has a reason in words.
- Every table the guard sees is classified by a person in this task, not by a rule that
  guesses from a name.
- The INPUT_DELTAS row records ruling 3 (one age, a pause, no `legal_hold`) and ruling 4
  (the pause is a governance row).

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/governance/*,apps/shared/lifecycle.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Forced row-level security on both tables.
- `JSONField` only with a named schema.
- Nothing overwritten: this task deletes nothing and opens no hatch.
- Enums in code are for kinds only.

### c12-tenant-deleted-status: a tenant that is closing, and one that is gone

**Requirements:** REP-04
**Scenarios:** contributes to TEN-S12, which `c12-exit-request` un-skips
**Depends on:** `r1-readiness`, `c5-contract-models-agents`
**Security review:** yes (authentication, sessions and the request path)
**Cloud rule:** carries the stop-and-report instruction (parallel plan rule 12)
**Minutes:** 40 (stopping point in rule 14)

`Tenant.status` gains `closing` and `deleted` beside `active` and `deactivated`
(`TenantStatus` is a kind, so this is a kinds entry and a migration in `apps/shared`).
- While `closing`, every mutating request (anything but GET and HEAD) answers 409
  `tenant_closing`, except the allowlist in one module: sign-in, refresh, sign-out,
  step-up, revoking a session, revoking an API key, `POST /exports`, the export and
  evidence downloads, and the exit routes' cancel. The allowlist is a list with a reason
  per entry and a test that every mutating route outside it is refused.
- While `deleted`, sign-in answers 404, every session and API key is refused, and no
  route reveals that the tenant ever existed.
- Agents, reminders, digests, webhooks and the briefing skip a `closing` or `deleted`
  tenant; `@tenant_task` checks the status once, centrally, so no later task has to
  remember.
- The check reads the tenant the session already carries; it adds no query per request
  (a query-count test pins it).

**Owned paths:**

- `backend/apps/shared/models.py` (the `Tenant.status` values only)
- `backend/apps/shared/migrations/000X_tenant_closing.py`
- `backend/apps/shared/closing.py` (the allowlist and the check)
- `backend/apps/shared/tests_closing.py`
- `backend/apps/shared/authentication.py`, `tenancy.py`, `middleware.py`
- `backend/apps/shared/kinds.py` (its own entry)
- `backend/apps/identity/session_logic.py` (the sign-in refusal only)

**Done when:**

- A `closing` tenant refuses every mutating route with 409 `tenant_closing` and allows
  each route on the allowlist, proved route by route over the whole route table.
- A `deleted` tenant's sign-in answers 404 and its sessions are refused; nothing
  distinguishes it from a tenant that never existed.
- An `active` tenant is unchanged: the full existing suite is green, and the per-request
  query count is unchanged.
- A worker task for a `closing` tenant does nothing and says so in its return, with a
  test.
- The route-permission, tenant-isolation and authentication guards are green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- A guard changes only in the package named for it, after a security review.
- No password, no bypass: a closing tenant's people still sign in with a passkey.
- Never expose a trace; 409 carries `code`, and the 404 says nothing.
- `tenancy.activate()` after auth.

### c12-dashboard-contract: the three report routes behind their real gates

**Requirements:** REP-01
**Scenarios:** none
**Depends on:** `c12-exports-contract-b`, `c8-reg-gaps`, `c9-actions`
**Minutes:** 30

Add the dashboard's operations to `backend/apps/reports/api.py` and `schemas.py` (key
`reportscore`, rule 3), each answering 501 `not_built` from its named module:

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `getReportSummary` | `GET /reports/summary` | SessionAuth, `reports.read` | `reports/dashboard.py` |
| `listGaps` | `GET /reports/gaps` | SessionAuth, `reports.read` | `reports/workload.py` |
| `listOverdueActions` | `GET /reports/overdue-actions` | SessionAuth, `reports.read` | `reports/workload.py` |

Schemas, reusing chunk 5's `Urgency`, chunk 8's `ObligationSummary` and
`SourceCoverage` rather than restating them:
- `ReportSummary` = `{openChanges, overdueActions, obligationsWithGap,
  unconfirmedAiDrafts, medianHoursToTriage|null, byUrgency[], byRegimeAndAccount[],
  complianceStatus[], byOwner[], sources[]}`. Each figure is nullable, so a panel the
  reader's permissions do not cover is `null` and never `0` (the default above).
- `CountByUrgency`, `CountByStatus`, `HeatCell` = `{regimeKey, accountKey, count}` and
  `OwnerLoad` = `{ownerKind, ownerId, name, open, overdue}` as designed.
- The gaps and overdue lists take the shared pagination (default 20, max 100).

Add the three routes to the route lists in `permissions.py`; add no entry to
`UNGATED_BY_DESIGN`. Write the INPUT_DELTAS row for the nullable figures and for
`sources` moving onto the summary (the prototype's coverage panel).

**Owned paths:**

- `backend/apps/reports/api.py`, `schemas.py`
- `backend/apps/reports/tests_contract.py`
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/scripts/contract_drift_pending.txt` (its own lines)
- `docs/inputs/INPUT_DELTAS.md`

**Done when:**

- The three operations appear in `openapi.json` with those ids and answer 501
  `not_built` behind `reports.read`.
- An anonymous request gets 401 and a session without the permission 403 with
  `requiredPermission`, both before the 501, proved per route.
- The route-permission guard is green and lists no ungated route.
- `bash generate-types.sh` produces types for all three without the task committing them.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/*' (api.py >= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- No logic in `api.py`; schemas in `schemas.py`; no `Dict[str, Any]`.
- Every route carries a permission; nothing joins `UNGATED_BY_DESIGN`.
- The API returns `key` and `kind`, never a phrase.
- An empty answer is 200.

### c12-retention-contract-b: the retention policy a bank can read and pause

**Requirements:** AUD-04
**Scenarios:** AUD-S9 (new, integration half)
**Depends on:** `c12-retention-contract-a`
**Minutes:** 30

Serve the policy from `backend/apps/governance/api.py`, `schemas.py` and `retention.py`
(key `gov`):

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `getRetention` | `GET /tenant/retention` | SessionAuth, `security.manage` | `governance/retention.py` |
| `updateRetention` | `PUT /tenant/retention` | SessionAuth, `security.manage`, `@requires_step_up` | `governance/retention.py` |

- `Retention` = `{years, floorYears, paused, pausedReason|null, pausedAt|null,
  categories[{key, kind, label}], lastRun|null}`, where `lastRun` is
  `{runAt, status, counts[{table, deleted}]}` from the newest `RetentionRun`.
  `years` comes from `RETENTION_YEARS` and is read-only (ruling 3, open question 2).
- `RetentionInput` = `{paused, reason}` only. Pausing needs a reason; resuming does not.
  A body carrying a period answers 422 `retention_period_fixed` with the reason in words.
- Each write is one `record()` row with before and after and the step-up assertion id.
- Add `AUD-S9` to `backend/apps/governance/app.md` and its stub to `tests_scenarios.py`
  (a new id and a new stub; PRD 0.4 already uses AUD-S8 for the ledger purge, which
  `c12-ledger-purge-function` un-skips):
  "The Data screen shows the retention policy, its last run, and a pause that a passkey
  confirms", `@integration` `@e2e`; un-skip the integration half here.

**Owned paths:**

- `backend/apps/governance/api.py`, `schemas.py`, `retention.py`
- `backend/apps/governance/tests_retention.py`
- `backend/apps/governance/tests_scenarios.py` (the AUD-S9 line and body only)
- `backend/apps/governance/app.md` (AUD-S9 and its own status cells)
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/scripts/contract_drift_pending.txt` (its own lines)

**Done when:**

- AUD-S9's integration half is green: the policy reads the fixed age, the pause state and
  the last run; a pause without a fresh assertion answers 403 `step_up_required`; with one
  it writes the row and one audit event carrying the assertion id.
- A member without `security.manage` gets 403, and tenant B gets 404 for tenant A's
  policy.
- A body carrying `years` answers 422 and changes nothing.
- The read is under the 250 ms budget and runs a fixed number of queries.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/governance/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- Permissions, never role names; a step-up on a security setting (playbook 4.2).
- `record()` on every write, in the same transaction.
- Errors are RFC 9457 with a `code` the client branches on.

### c12-export-audit-log: the audit log as a file

**Requirements:** REP-02, AUD-01
**Scenarios:** contributes to REP-S2
**Depends on:** `c12-exports-contract-b`, `c4-audit-read`
**Minutes:** 35

Build `backend/apps/reports/exports/audit_log.py` and register it for the `audit_log`
kind. It writes the tenant's audit events in `csv` and `json`: timestamp (UTC), actor
kind and name, action, subject type, subject title at the time, summary, and the
before-and-after values, in the order the audit read already applies, filtered by
`ExportFilters.from` and `.to`.
- It reads through the same permission-filtered path as `GET /audit-events`
  (`c4-audit-read`), so a row a reader could not see on the screen cannot reach the file.
  Rows without a tenant appear only where the audit read already shows them.
- It streams in batches; a tenant with a million rows does not build the file in memory,
  and a test pins the batch behaviour.
- No trace, no stack, no internal id that the screen does not show.

**Owned paths:**

- `backend/apps/reports/exports/audit_log.py`
- `backend/apps/reports/tests_export_audit_log.py`
- `backend/apps/reports/exports/__init__.py` (its own registry line)
- `backend/scripts/contract_drift_pending.txt` (its own line)

**Done when:**

- An export of the audit log produces a file whose rows match `GET /audit-events` for the
  same reader and filters, proved row for row on the seeded tenant.
- Tenant B's rows are absent, proved with both tenants seeded.
- The file carries the export's own date, and the job writes its audit row through the
  runner.
- Memory stays flat over 50 000 seeded rows (a batched-read test).

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/exports/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Row-level security on every read; an export can never widen what a reader may see.
- Nothing overwritten: an export reads, it does not mark rows.
- Tenant content never reaches a log or Sentry.

### c12-ledger-purge-function: the owner-only purge function and the hatch allowlist

**Requirements:** AUD-04
**Scenarios:** AUD-S8 (un-skipped); contributes to AUD-S6
**Depends on:** `c12-retention-contract-a`, hardening task H-C (ruling 1)
**Security review:** yes — this is the chunk's only guard change (parallel plan rule 8)
**Cloud rule:** carries the stop-and-report instruction
**Minutes:** 40 (stopping point in rule 14)

Two things, in one migration in `apps/shared`:
1. **The hatch's allowlist.** Replace the append-only and outbox guards' maintenance
   check with `current_setting('cw.maintenance', true) = 'on' AND current_user = <the
   migrator role, from the constant the grants already use>`, so the hatch opens for the
   schema owner and for a `SECURITY DEFINER` function the owner owns, and for nobody else
   (ruling 1). Add the structural guard in `apps/shared/tests_append_only.py`: every
   `SECURITY DEFINER` function in the database is in a named allowlist; each allowlisted
   one is owned by the migrator, has `search_path` pinned to a literal, has EXECUTE
   revoked from PUBLIC, and is granted only to the roles named here. Plant a function in
   the test to prove the guard fails. In the same file, add H-C's other structural guard
   (re-homed here, ruling 1): enumerate every foreign key whose target is an append-only
   table and fail on any `ON DELETE` or `ON UPDATE` action other than `NO ACTION` or
   `RESTRICT`, with a planted constraint proving it fails. `c12-exit-execute`'s tenant-wide
   delete is what this protects: a ledger row must go because the delete list names it,
   never because a cascade dragged it out.
2. **The purge function.** `cw_purge_tenant(tenant uuid, cutoff timestamptz, batch int)`,
   `SECURITY DEFINER`, owned by `cw_migrator`, `SET search_path = public, pg_temp`,
   `SET cw.maintenance = 'on'` in its own clause so the hatch closes when it returns,
   EXECUTE revoked from PUBLIC and granted to `cw_app` alone. It:
   - raises when `cutoff` is later than `now() - RETENTION_FLOOR_YEARS`, which is a
     literal in the function, not a parameter;
   - raises when `tenant` is not the session's `app.tenant_id`, and filters every
     statement on `tenant_id = tenant`;
   - deletes only from the fixed table list the lifecycle registry names, whole rows
     only, never an UPDATE, in dependency order, at most `batch` rows per table;
   - returns the deleted counts per table;
   - does nothing and returns zero counts when the tenant's retention is paused.

Add the `HARDENING.md` rows: the H-C addendum's `session_user` predicate is replaced by
this allowlist, with the reason; the addendum's foreign-key guard is built here instead of
in H-C, named by file, so H-C's own task does not build it twice; and
`MIGRATOR_DATABASE_URL` is unset before gunicorn and the worker start, with the boot test
that proves the API's role cannot reach it.

**Owned paths:**

- `backend/apps/shared/migration_helpers.py`
- `backend/apps/shared/migrations/000X_purge_function.py`
- `backend/apps/shared/tests_append_only.py`
- `backend/apps/shared/tests_purge_function.py`
- `backend/apps/shared/tests_database_role.py` (the migrator-absent test only)
- `backend/apps/governance/tests_scenarios.py` (the AUD-S8 skip line and body only)
- `backend/apps/governance/app.md` (the AUD-S8 status cell only)
- `docs/plans/briefs/HARDENING.md` (its own rows)
- `docs/adr/0046-retention-by-age-of-last-use.md` (the implementation note only)

**Done when:**

- As `cw_app`: `SET LOCAL cw.maintenance = 'on'` and `SET LOCAL CW.MAINTENANCE = 'on'`
  still leave UPDATE and DELETE refused on every append-only table, and a direct DELETE on
  `audit_event` is refused.
- AUD-S8 is un-skipped and green. PRD 0.4's `governance/app.md` already carries it and
  `tests_scenarios.py` already carries its stub, so this task un-skips what is there and
  writes no new scenario: a cutoff inside the floor refuses and deletes nothing; `cw_app`
  is refused a direct UPDATE or DELETE on a ledger table and cannot open the hatch;
  tenant B's purge leaves tenant A's rows alone because the function filters on the active
  tenant; a paused tenant deletes nothing and says so.
- As `cw_app`, calling `cw_purge_tenant` with a cutoff inside the floor raises; with
  another tenant's id it raises; with a paused tenant it deletes nothing.
- As `cw_app`, calling it correctly deletes rows from the registry's tables and from
  nowhere else, in batches, and leaves `footprint_history` and every library table
  untouched.
- After the call, the hatch is shut: a following DELETE on `audit_event` in the same
  transaction is refused.
- `cw_app` cannot create a `SECURITY DEFINER` function, and cannot call the exit function
  (which does not exist yet: the test asserts the grant shape for every allowlisted
  function that does).
- The `SECURITY DEFINER` guard fails on a planted function and passes on the tree.
- The foreign-key guard fails on a planted `ON DELETE CASCADE` into an append-only table
  and passes on the tree, so nothing `c12-exit-execute` deletes can cascade into a ledger.
- `migrate_from_zero` applies the whole graph, and the compliance lint is green with the
  hatch used only inside a migration.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Append-only ledgers: deletion by age is the one named exception (CLAUDE.md §5, D-53),
  and it is a delete, never an update.
- `cw_app` cannot bypass row-level security and cannot open the hatch.
- Nothing in the API or the worker holds migrator credentials.
- A guard changes only here, and only with a security review.

### c12-imports-contract: the import routes, the upload and the dry-run seam

**Requirements:** REP-03, VOC-09
**Scenarios:** none
**Depends on:** `c12-exports-contract-b`, `c9-scanner-adapter`, `c12-deps-spreadsheets`
**Security review:** yes (an uploaded file from a person, parsed in the worker)
**Minutes:** 40

Add the import half to `backend/apps/reports/api.py`, `schemas.py`, `tasks.py` and a new
`reports/imports/upload.py` (key `reportscore`):

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `createImport` | `POST /imports` | SessionAuth, `register.edit` **and** `vocab.manage` | `reports/imports/upload.py` |
| `getImport` | `GET /imports/{importId}` | SessionAuth, same pair | `reports/imports/upload.py` |
| `commitImport` | `POST /imports/{importId}/commit` | SessionAuth, same pair; for `kind=configuration` also `roles.manage` and `@requires_step_up` | `reports/imports/upload.py` |

- The file is uploaded through the API (multipart), scanned by `c9-scanner-adapter`'s
  adapter before anything reads it, hashed, and stored through the storage seam; a file
  above `IMPORT_FILE_MAX_MB` or of another type answers 422 with a user-facing message.
  Nothing presigned, and no file is visible before the scan and the hash.
- `ImportInput` = `{kind, fileName}`; `ImportJobOut` = `{id, kind, dryRun, status,
  result|null, createdAt, completedAt}`; `ImportResult` is the named schema:
  `{rows, created, updated, conflicts, unknownValues[{column, value, suggestedKey|null,
  nearMatches[]}], rowErrors[{row, code, detail}]}`.
- `POST /imports` always runs a dry run first; `commitImport` takes the reviewed mapping
  (`ImportMapping`: column to field, and value to key) and refuses with 409
  `import_not_reviewed` when the dry run has not completed, 409 `import_already_committed`
  when it has already run, and 422 `unmapped_value` when a value is still unmapped.
- **A configuration commit is a role change.** The snapshot carries the tenant's roles and
  their permissions, so `commitImport` for `kind=configuration` needs `roles.manage`
  beside the pair and a fresh assertion (`@requires_step_up`); without one it answers 403
  `step_up_required` and commits nothing. The kind's extra gate is declared here, beside
  the route, so no builder can widen or forget it, and the assertion id goes on the
  commit's `record()` row. An `obligation_register` commit is unchanged: it writes no
  role and needs no step-up.
- `reports/imports/__init__.py` is the registry, one line per kind (ruling 7), and the
  `@tenant_task` in `tasks.py` runs the parse and, separately, the commit. A kind with no
  registered importer answers 501 `not_built` before a row is written.
- Parsing limits come from `c12-deps-spreadsheets`' settings; a formula, a macro or an
  external reference in the workbook is never evaluated, and a test plants one.

**Owned paths:**

- `backend/apps/reports/api.py`, `schemas.py`, `tasks.py` (its own operations and task)
- `backend/apps/reports/imports/__init__.py`, `imports/upload.py`
- `backend/apps/reports/tests_imports.py`
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/scripts/contract_drift_pending.txt` (its own lines)

**Done when:**

- The three operations answer 501 `not_built` for a kind with no importer, behind both
  permissions, with 401 and 403 proved first.
- A `configuration` commit without `roles.manage` answers 403 and one without a fresh
  assertion answers 403 `step_up_required`, both before any row is written; with both it
  proceeds and the audit row carries the assertion id. An `obligation_register` commit
  needs neither, proved by a test per kind.
- A file is scanned before it is parsed (a test with the mock scanner refusing), and a
  refused file leaves no stored object and no readable row.
- A workbook with a formula, a macro or a 2 GB decompressed sheet is refused without the
  worker running out of memory.
- Tenant B gets 404 for tenant A's import.
- The upload, the dry run and the commit each write their own audit row; the dry run
  writes no register row at all.
- `contract_drift.py` reports the three operations as delivered-in-part.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- Input from a person, an agent or a file is never an impossible case: validate at the
  boundary.
- Fetched and uploaded content is untrusted.
- `record()` on every write; no logic in `api.py`.
- A job's status endpoint, never work inside the request.

### c12-dashboard-summary: the figures, the urgency bars and the heat table

**Requirements:** REP-01
**Scenarios:** contributes to REP-S1
**Depends on:** `c12-dashboard-contract`, `c5-watch-feed-read`, `c5-cases-so-what-and-links`, `c7-ai-log-backend`, `c5-watch-sources-coverage`, `c8-reg-entity-status`
**Minutes:** 35

Build `backend/apps/reports/dashboard.py` and serve `GET /reports/summary`:
- `openChanges`: the tenant's change cases not closed or dismissed, inside the regulatory
  scope (FP-03).
- `unconfirmedAiDrafts`: So-what drafts a person has not confirmed (WAT-05).
- `medianHoursToTriage`: over cases triaged within `REPORTS_WINDOW_DAYS` (90, a setting),
  null when there are none.
- `byUrgency`: counts per urgency key, every level present, zero included, with `{key,
  kind, label}`.
- `byRegimeAndAccount`: one cell per regime and account term the tenant's scope holds,
  counted from the open cases' footprint terms.
- `complianceStatus`: counts per compliance-status key over applicable obligations.
- `sources`: chunk 5's `SourceCoverage`, unchanged.
- `obligationsWithGap` and `overdueActions` are counted here too, from the same modules
  `c12-dashboard-workload` lists them with, calling its functions rather than writing a
  second query (so the figure and the list can never disagree).
- Every panel the reader's permissions do not cover is `null`: no `register.read`, no
  `obligationsWithGap`, no `complianceStatus`; no `watch.read`, no urgency bars or
  sources; no `cases.read`, no median.
- One fan-out, nothing chained, pinned by a query-count test, inside the 250 ms budget on
  the seeded data.

**Owned paths:**

- `backend/apps/reports/dashboard.py`
- `backend/apps/reports/tests_dashboard.py`
- `backend/scripts/contract_drift_pending.txt` (its own line)

**Done when:**

- The summary answers with every figure on the seeded tenant, and each is a count or a
  key, never a phrase.
- A record outside the regulatory scope is in no figure (FP-03), proved per panel.
- A reader without a permission gets `null` for that panel, not `0` and not a 403.
- Tenant B's rows reach no figure.
- The queries are a fixed number whatever the data, pinned by a test, and the route
  reports `Server-Timing: app` under the budget with no WARNING.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/dashboard.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Every read under row-level security, after `tenancy.activate()`.
- The API returns `key` and `kind`, never a phrase.
- Fan out, never chain; paginate every list.
- A read writes nothing.

### c12-export-inventory: the inventory as a file

**Requirements:** REP-02
**Scenarios:** contributes to REP-S2
**Depends on:** `c12-exports-contract-b`, `c3-provision-read`, `c8-reg-entity-status`, `c12-deps-spreadsheets`
**Minutes:** 35

Build `backend/apps/reports/exports/inventory.py` and register it for the `inventory`
kind, in `csv`, `xlsx` and `json`: per obligation in the tenant's inventory, the
reference, the instrument, the title in the tenant's language, the duty type, the tags,
the version in force and its date, whether it applies, the compliance status, the owner
and the last review, with the export's own date in the file.
- It reads the library through the existing library read path and the tenant's register
  through chunk 8's, never with a query of its own against another app's tables.
- It respects the regulatory scope, and `ExportFilters` narrows it
  (`instrumentKey`, `statusKeys`). The `entityId` and `standardEdition` filters and the
  Statement of Applicability columns are `f03-T83`'s, one wave later.
- Long texts are written whole, and a cell that begins `=`, `+`, `-` or `@` is written so
  a spreadsheet cannot execute it (a formula-injection test).

**Owned paths:**

- `backend/apps/reports/exports/inventory.py`
- `backend/apps/reports/tests_export_inventory.py`
- `backend/apps/reports/exports/__init__.py` (its own registry line)
- `backend/scripts/contract_drift_pending.txt` (its own line)

**Done when:**

- The export matches the inventory screen's rows for the same reader and filters.
- A record outside the regulatory scope is absent; a licensed standard's provision text is
  absent (AC-INV2's fence holds in an export too).
- A cell that could be read as a formula is neutralised, proved by a planted value.
- Tenant B's rows are absent, and the job's audit row names the file.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.library apps.register apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/exports/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Row-level security and the regulatory scope hold in a file exactly as on a screen.
- Nothing a tenant writes under a standard leaves its zone (AC-REG2).
- `record()` on the write that the runner performs; the builder itself writes nothing.

### c12-config-policies: the policies in the configuration snapshot

**Requirements:** VOC-09, AUD-04
**Scenarios:** contributes to VOC-S13
**Depends on:** `c12-config-logic`, `c10-workflow-policy`, `c11-security-policy`, `c12-retention-contract-b`
**Minutes:** 30

Extend `backend/apps/taxonomy/configuration.py` with the three policies: the workflow
policy (reminders, escalation, the sub-statuses and their categories), the security policy
(session and credential settings, minus anything secret), and the retention policy (the
pause state and its reason; the age travels as a stamp, never as a setting to import,
because it is fixed).
- No secret, hash, token, key prefix or member name ever enters a snapshot; a test walks a
  produced snapshot for every field name the security policy holds and proves the secret
  ones are absent.
- On read-back, a policy value that the target tenant's plan or permissions do not allow
  is a `conflict`, never a silent skip.
- Importing a retention pause is refused: pausing is a step-up action on its own route, so
  a configuration import can never pause or resume a bank's purge. That is a `conflict`
  with its reason.

**Owned paths:**

- `backend/apps/taxonomy/configuration.py` (the policy section only)
- `backend/apps/taxonomy/tests_configuration_policies.py`

**Done when:**

- A snapshot carries the three policies by key and round-trips `unchanged` into its own
  tenant.
- No secret field is present, proved by name over the policy models.
- A retention pause in a snapshot is reported as a conflict and never applied.
- The read-back still writes nothing.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.taxonomy apps.tenants apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/taxonomy/configuration.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- A secret is never exported, logged or returned twice.
- Store and compare keys, never labels.
- A read writes nothing.

### c12-retention-purge: the daily purge

**Requirements:** AUD-04
**Scenarios:** AUD-S6 (rewritten and un-skipped)
**Depends on:** `c12-ledger-purge-function`, `c12-retention-contract-b`, `c9-evidence`, `c10-notifications-api`
**Security review:** yes (it deletes a bank's records)
**Minutes:** 40

Build `backend/apps/governance/last_use.py` and `governance/retention_tasks.py`:
- `last_use_at` implements the default of open question 1, one rule per table, from the
  lifecycle registry: the latest of closure or dismissal, removal, the last change, or a
  reference from a live record. Reads never count. One test per table.
- The daily `@tenant_task` computes `cutoff = now - RETENTION_YEARS`, skips a paused
  tenant, and calls `cw_purge_tenant` in bounded batches (`RETENTION_BATCH_SIZE`, 500)
  until a batch comes back empty. Files go before their rows: evidence and export objects
  are deleted through the storage seam first, so a deleted row never leaves an orphan
  file. The same run deletes the object of any export past its `expires_at`
  (`EXPORT_RETENTION_DAYS`) too, keeping the row and its audit trail until the ten-year
  age; that is what makes `export_expired` true rather than a promise.
- One `RetentionRun` row per run and one `record()` audit row with counts only — never a
  title, an id or a person's name from the rows it removed.
- Idempotent: a second run the same day deletes nothing more and writes a run row saying
  so. A failure mid-run leaves the batches already deleted deleted, and the next run
  continues; the run row carries `failed` with a code, never a trace.
- The beat entry is this task's alone, with its registration test.

Rewrite AUD-S6 in `backend/apps/governance/app.md` (ruling 3 and D-53): a record is
deleted ten years after its last use; ledger rows go whole, past the age, through the
database-guarded path; a paused tenant purges nothing; tenant B's policy never touches
tenant A; a direct delete by `cw_app` is still refused; the run reports counts per table.

**Owned paths:**

- `backend/apps/governance/last_use.py`, `retention_tasks.py`
- `backend/apps/governance/tests_retention_purge.py`, `tests_last_use.py`
- `backend/apps/governance/tests_scenarios.py` (the AUD-S6 line and body only)
- `backend/apps/governance/app.md` (AUD-S6 and its own status cells)
- `backend/config/settings.py` (its own banner and the beat entry), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- AUD-S6 is green with a frozen clock moved past the age: a closed case older than ten
  years goes with its children, one a live gap still references stays, and the tenant's
  audit rows past the age go while `footprint_history` and every library row stay.
- An export past `expires_at` loses its file and keeps its row, and its download then
  answers 409 `export_expired`.
- A paused tenant purges nothing and still writes a run row saying it was paused.
- Tenant A's rows survive a purge run for tenant B, proved with both seeded.
- A second run changes nothing (idempotence), and a run interrupted after one batch
  resumes correctly.
- The audit row holds counts only: a test asserts no title, id or name in it.
- The Celery registration guard sees the beat entry, and the worker holds no migrator
  credentials (`tests_database_role`).

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Deletion by age is the named exception to "nothing overwritten"; the job never updates
  an append-only row.
- `@tenant_task` in the worker; every statement filtered by the tenant.
- Tenant content never reaches a log, an audit value or Sentry.
- Every threshold is a setting with an env override; tests freeze the clock.

### c12-dashboard-workload: gaps, overdue actions and the load per owner

**Requirements:** REP-01
**Scenarios:** REP-S1 (integration half, un-skipped)
**Depends on:** `c12-dashboard-summary`, `c8-reg-gaps`, `c9-actions`, `c8-ten-teams`
**Minutes:** 35

Build `backend/apps/reports/workload.py` and serve `GET /reports/gaps` and
`GET /reports/overdue-actions`, and export the two functions
`c12-dashboard-summary` already calls for its counts:
- Gaps: applicable obligations whose compliance status is a gap or partly compliant, per
  legal entity where the register keeps it per entity, with the severity, the owner, the
  target date and the entry's status, paginated (default 20, max 100), filtered by the
  regulatory scope.
- Overdue actions: open actions past their due date in the tenant's timezone, with the
  owner, the case and the days overdue, paginated.
- `byOwner` on the summary: open and overdue counts per owner, by team where the owner is
  a team (TEN-03), never by a person's email, and only for a reader holding `cases.read`.
- Then un-skip REP-S1's integration half, which asserts every panel of the summary and
  both lists.

**Owned paths:**

- `backend/apps/reports/workload.py`
- `backend/apps/reports/tests_workload.py`
- `backend/apps/reports/tests_scenarios.py` (the REP-S1 skip line and body only)
- `backend/apps/reports/app.md` (its own status cells)
- `backend/scripts/contract_drift_pending.txt` (its own lines)

**Done when:**

- REP-S1's integration half is green: each tile comes from its own endpoint, under
  250 ms, in counts and keys, with records outside the regulatory scope excluded.
- The counts on the summary and the rows in the lists agree, because both come from these
  functions (a test asserts the numbers match the list lengths on the seeded data).
- Both lists paginate and refuse a page size above 100.
- A reader without `cases.read` gets an empty `byOwner` and a permission-limited notice
  field, never a 403 on the page.
- Tenant B's rows are absent from both lists.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.register apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/workload.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Paginate (default 20, max 100); fan out, never chain.
- Permissions, never role names; a permission-limited panel is empty, never false.
- A read writes nothing.

### c12-export-changes-cases: changes and cases as files

**Requirements:** REP-02
**Scenarios:** contributes to REP-S2
**Depends on:** `c12-exports-contract-b`, `c5-cases-so-what-and-links`, `c9-assessment`, `c9-actions`, `c9-evidence`, `c9-signoff`
**Minutes:** 40

Build `backend/apps/reports/exports/changes.py` and `exports/cases.py` and register them
for the `changes` and `cases` kinds (ruling 6; `c9-case-file-export` keeps `case_file`,
the single case's own file, and this task exports the list):
- Changes: each regulatory change the tenant has a case for, with the source, the change
  type, the key date, the urgency, the case status, the owner, the confirmed "So what?"
  and the linked obligations. An unconfirmed AI draft is labelled as such in its own
  column and never presented as a fact (WAT-05).
- Cases: each change case with its assessment verdict, its actions and their states, its
  evidence titles (never the files), its sign-off with who and when, and the dates that
  make the audit trail readable.
- Both take `ExportFilters.from`, `.to` and `.statusKeys`, respect the regulatory scope,
  and write in `csv`, `xlsx` and `json` with the same formula-safety rule as the
  inventory.

**Owned paths:**

- `backend/apps/reports/exports/changes.py`, `exports/cases.py`
- `backend/apps/reports/tests_export_changes.py`, `tests_export_cases.py`
- `backend/apps/reports/exports/__init__.py` (its own registry lines)
- `backend/scripts/contract_drift_pending.txt` (its own lines)

**Done when:**

- Both exports match the screens' rows for the same reader and filters.
- An unconfirmed draft is labelled in the file, and a test asserts the label.
- No evidence file, no comment text and no private note reaches either file.
- Tenant B's rows are absent; records outside the regulatory scope are absent.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.watch apps.cases apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/exports/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- AI output is labelled until a person confirms it.
- Row-level security and the regulatory scope hold in a file as on a screen.
- "Applies" and "we comply" stay separate facts in the columns.

### c12-exit-request: two people ask for the door

**Requirements:** REP-04
**Scenarios:** REP-S7 (un-skipped), TEN-S12 (un-skipped)
**Depends on:** `c12-tenant-deleted-status`, `c12-exports-contract-b`, `c10-notifications-api`, `c10-mail-catalog`
**Security review:** yes (four eyes, step-up, and the switch that makes a tenant read-only)
**Minutes:** 40 (stopping point in rule 14)

Add `TenantExitRequest(TenantModel)` to `backend/apps/reports/models.py` and a migration
(key `mig:reports`): `requested_by`, `requested_at`, `requested_assertion_id`,
`approved_by`, `approved_at`, `approved_assertion_id`, `cancelled_by`, `cancelled_at`,
`cancel_reason`, `execute_after`, `export_job` (nullable), `status`, with the CHECK
`approved_by IS NULL OR approved_by <> requested_by`, added to `FOUR_EYES_TABLES` and to
the four-eyes guard's list, under forced RLS.

Serve from `reports/api.py` and a new `reports/exit_logic.py` (key `reportscore`):

| Operation | Route | Gate |
|---|---|---|
| `getTenantExit` | `GET /tenant/exit` | SessionAuth, `security.manage` |
| `requestTenantExit` | `POST /tenant/exit` | SessionAuth, `security.manage`, `@requires_step_up` |
| `approveTenantExit` | `POST /tenant/exit/approve` | SessionAuth, `security.manage`, `@requires_step_up` |
| `cancelTenantExit` | `POST /tenant/exit/cancel` | SessionAuth, `security.manage`, `@requires_step_up` |

- Approving your own request answers 409 `four_eyes_violation` before the database is
  asked, and the CHECK refuses it if the code is ever wrong.
- On approval the tenant becomes `closing`, `execute_after` is set to
  `now + TENANT_EXIT_DELAY_DAYS` (30), and the final export job is created
  (`tenant_export`, built by `c12-exit-export`; until that task lands the job answers 501
  and the request still stands).
- Every active admin is emailed at the request, at the approval and
  `TENANT_EXIT_NOTICE_DAYS` (7) before execution, through the mail catalog in each
  recipient's language. The notice mail is a `@tenant_task`.
- Any `security.manage` holder may cancel with a step-up until execution; the tenant
  returns to `active` and the pending export is cancelled.
- Every write is one `record()` row carrying the assertion id.
- Un-skip REP-S7 and TEN-S12.

**Owned paths:**

- `backend/apps/reports/models.py` (the new model only), `migrations/000X_tenant_exit.py`
- `backend/apps/reports/api.py`, `schemas.py`, `exit_logic.py`, `tasks.py` (its own task)
- `backend/apps/reports/tests_exit_request.py`
- `backend/apps/reports/tests_scenarios.py` (the REP-S7 line only)
- `backend/apps/tenants/tests_scenarios.py` (the TEN-S12 line only)
- `backend/apps/reports/app.md`, `backend/apps/tenants/app.md` (own status cells)
- `backend/apps/shared/tests_four_eyes.py` (the guarded-table list only)
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/config/settings.py` (its own banner), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- REP-S7 is green: the requester's own approval answers 409 and the database refuses the
  row; a second holder's approval sets `closing` and `execute_after`; a cancel before the
  date restores `active`.
- TEN-S12 is green: while `closing`, a mutating route answers 409 `tenant_closing`, and
  sign-in, refresh, step-up, session revocation and the export download all still work.
- Each of the three writes needs a fresh assertion and records it.
- The four-eyes guard lists `tenant_exit_request`; the RLS guard lists it as forced.
- The three mails are sent once each, in the recipient's language, and carry no tenant
  content beyond the tenant's own name and the dates.
- Tenant B sees nothing of tenant A's request.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.reports apps.tenants apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- Four eyes, enforced by a check constraint, with a passkey step-up.
- `record()` on every write, in the same transaction.
- No route lets one person delete a bank.
- Errors are RFC 9457 with a `code`.

### c12-e2e-seed: the chunk's journey data

**Requirements:** REP-01 to REP-04, AUD-04, VOC-09
**Scenarios:** none (it makes four journeys possible)
**Depends on:** `c9-e2e-seed`, `c8-e2e-seed-register`, `c12-exports-contract-b`, `c12-imports-contract`, `c12-retention-contract-b`
**Minutes:** 40 (stopping point in rule 14)

Extend `backend/apps/shared/e2e_seed.py` with one seed call for chunk 12, deterministic
and idempotent, from the prototype's data:
- a completed export of the inventory with its file in the mock storage, and one expired
  export, so the screen shows both states;
- a small register spreadsheet fixture under `backend/apps/shared/fixtures/`, with 40
  rows, three unknown status values and two row errors, which REP-S4 uploads;
- a retention policy with a last run carrying counts, and a record whose last use is past
  the age in the second tenant only, so no journey deletes the first tenant's data;
- an approved exit request on the **second** seeded tenant alone, never on the tenant the
  other journeys sign in to, so no journey can put the main tenant into `closing`;
- one login per negative case: an admin holding `security.manage`, a compliance officer
  holding `exports.create` without it, and a reader holding neither.

Teardown restores the seeded state on failure too, so a journey that pauses retention or
cancels an exit leaves the next run clean.

**Owned paths:**

- `backend/apps/shared/e2e_seed.py` (its own seed call only)
- `backend/apps/shared/e2e_logins.py`, `e2e_passkeys.py` (its own logins only)
- `backend/apps/shared/fixtures/register_import_sample.xlsx`
- `backend/apps/shared/tests_seed_integrity.py` (its own assertions only)
- `frontend/tests/e2e/support/passkeys.ts` (its own LOGINS entries only)

**Done when:**

- `seed_e2e` runs twice with the same result, and `tests_seed_integrity` covers the new
  rows.
- Every date in the seed derives from the tenant-local anchor, never from the real today
  (a test moves the clock a year and the seed still makes sense).
- The exit request sits on the second tenant, proved by an assertion.
- The fixture workbook is under the file cap and holds no personal data.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `cd frontend && npm run test:e2e -- --grep @smoke` (the seed must not break the golden paths)

**Invariants:**

- Extend `seed_e2e`, never mock; the seed is idempotent, deterministic and realistic.
- Clocks anchor to the tenant-local date plus a fixed wall time.
- No real personal data in a fixture.

### f03-T83: the Statement of Applicability as a dated inventory export

**Requirements:** REP-02, REG-08
**Scenarios:** REP-S6 (un-skipped)
**Depends on:** `f03-T72`, `c12-export-inventory`
**Security review:** yes (a standard's licensed text must not leave in a file)
**Minutes:** 30

Extend `backend/apps/reports/exports/inventory.py` with the Statement of Applicability
filters and columns (STANDARDS STD-33, D-46): `ExportFilters.standardEdition` and
`.entityId` narrow the export to one standard's edition and one legal entity, and each
row then carries the unit's reference, the tenant's own title, its applicability, the
reason, the compliance status, the approver and the decision date, with the export's date
in the file.
- The unit rows come from chunk 8's register reads (`f03-T72`), never from a query of this
  module's own.
- A standard's provision text is never exported (AC-INV2); a test plants one and proves
  the file carries the tenant's own words only.
- REP-S3 stays green: the export is still a job behind a step-up.

**Owned paths:**

- `backend/apps/reports/exports/inventory.py` (the SoA filters and columns only)
- `backend/apps/reports/tests_export_soa.py`
- `backend/apps/reports/tests_scenarios.py` (the REP-S6 line only)
- `backend/apps/reports/app.md` (its own status cells)

**Done when:**

- REP-S6 is green and REP-S3 stays green.
- The filtered export carries the seven unit columns and its export date.
- Nothing written under a standard reaches another tenant, an index or a model
  (AC-REG2), proved here for the file.
- An `entityId` of another tenant answers 404 before a job is written.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.register apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/exports/inventory.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- A standard's licensed text never leaves the library's fence.
- "Applies" and "we comply" are separate columns, never merged.
- Exports stream through permission checks and are audited.

### c12-fe-data-retention: the retention panel

**Requirements:** AUD-04
**Scenarios:** AUD-S9 (journey half, un-fixmed)
**Depends on:** `c12-card-data-b`, `c12-retention-contract-b`, `c12-e2e-seed`
**CLAUDE.md §11 applies in full.**
**Minutes:** 35

Build `/admin/data`'s page shell and its retention panel in
`frontend/src/features/data/` (types, api, hooks, presentation) and
`frontend/src/app/(tenant)/admin/data/page.tsx`, from `design/screens/admin-data.html`:
the fixed period in words, what it covers, the last run with its date and counts, and
Pause and Resume behind the passkey step-up the API demands.
- Every string is in the `data` message catalog namespace, in en and sv; no string
  literal in JSX.
- The pill on the run row is the `Pill` component with a tone from the run's status kind.
- The page is reachable from the navigation registry entry this task adds, gated by
  `security.manage`.
- The journey (AUD-S9, in `frontend/tests/e2e/governance.journey.spec.ts`) signs in with
  a passkey through the UI, opens Data, reads the policy and the last run, pauses with a
  step-up, sees the paused state, and resumes.

**Owned paths:**

- `frontend/src/features/data/*`
- `frontend/src/app/(tenant)/admin/data/page.tsx`
- `frontend/src/components/admin/DataScreen.tsx`, `RetentionPanel.tsx`
- `frontend/src/messages/data/en.json`, `sv.json`
- `frontend/src/shared/navigation/registry.ts` (its own entry)
- `frontend/tests/e2e/governance.journey.spec.ts` (the AUD-S9 block only)
- `backend/apps/governance/app.md` (the AUD-S9 status cell)

**Done when:**

- AUD-S9's journey is green against the real stack, with the API guard declaring the one
  expected 403 where the step-up is demanded.
- The panel offers no period to edit and says the period is fixed.
- A member without `security.manage` never sees the navigation entry and gets the
  restricted page, not a 403 screen.
- `npm run lint`, `typecheck`, `test:coverage`, `check:messages`, `check:copy-drift` and
  `build` are green; the screen renders at 375 px with no horizontal scroll and in both
  themes.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "AUD-S9"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Pills only through `Pill`; six tones by slot or kind; typography roles only.
- No string literal in JSX; every string in the message catalogs.
- E2E signs in with a passkey through the UI, mocks no API, and imports `test` from
  `support/api-guard`.
- The client branches on `code`, never on `detail`.

### c12-import-register-dryrun: the dry run that asks once per value

**Requirements:** REP-03
**Scenarios:** contributes to REP-S4
**Depends on:** `c12-imports-contract`, `c8-reg-status`, `c8-reg-applicability`, `c3-provision-read`
**Minutes:** 40

Build `backend/apps/reports/imports/register.py`'s read half and register it for
`obligation_register`:
- Parse the workbook with the pinned reader inside the limits, map columns to fields by
  header with a suggestion per column, and report per row: matched obligation (by
  reference, then by near match over the tenant's own titles), `create`, `update`,
  `conflict` or an error with its line number and a code.
- Collect unknown values per column **once**, each with its near matches from the target
  vocabulary and a suggested key; the same value never appears twice.
- Write the `ImportResult` and nothing else: the dry run touches no register row, no
  vocabulary row and no applicability request, proved by an audit-on-write test.
- A row that would decide applicability is reported as "will become a request for a second
  person" (the default), not as a decision.

**Owned paths:**

- `backend/apps/reports/imports/register.py` (the parse and report half)
- `backend/apps/reports/tests_import_dryrun.py`
- `backend/apps/reports/imports/__init__.py` (its own registry line)

**Done when:**

- The seeded 40-row fixture reports 40 rows, the near matches and exactly three unknown
  values, each asked once.
- A malformed row is an error with its line number and a code, and does not stop the run.
- The dry run writes nothing at all.
- A reference belonging to another tenant's private instrument is never matched.
- Parsing a file at the row and column caps stays within the worker's memory, pinned by a
  test.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.register apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/imports/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Uploaded content is untrusted; validate at the boundary.
- A dry run writes nothing and records nothing.
- Store and compare keys, never labels.

### c12-committee-pack: the pack the committee reads

**Requirements:** REP-02, REP-01
**Scenarios:** REP-S2 (integration half, un-skipped)
**Depends on:** `c12-dashboard-workload`, `c12-export-inventory`, `c12-export-changes-cases`, `c12-export-audit-log`, `c6-roadmap-backend`, `c5-watch-sources-coverage`, `c10-mail-catalog`
**Minutes:** 35

Build `backend/apps/reports/exports/committee_pack.py` and register it for the
`committee_pack` kind, in `txt` and `json`: the period's figures from
`reports/dashboard.py` and `workload.py`, the roadmap's next dates, the source coverage,
the open cases by urgency, the gaps with their owners and target dates, and the
decisions taken in the period from the audit trail — each section with its heading from
`c10-mail-catalog`'s text in the tenant's default language.
- It calls the dashboard and roadmap functions; it writes no query of its own.
- It carries a confirmed "So what?" and never an unconfirmed draft (WAT-05).
- The period comes from `ExportFilters.from` and `.to`, defaulting to the last quarter in
  the tenant's timezone.
- Then un-skip REP-S2's integration half: each export is a job with a status, and each
  download streams with an audit event naming the file and the person.

**Owned paths:**

- `backend/apps/reports/exports/committee_pack.py`
- `backend/apps/reports/tests_committee_pack.py`
- `backend/apps/reports/tests_scenarios.py` (the REP-S2 line only)
- `backend/apps/reports/app.md` (its own status cells)
- `backend/apps/reports/exports/__init__.py` (its own registry line)
- `backend/scripts/contract_drift_pending.txt` (its own line)

**Done when:**

- REP-S2's integration half is green for the pack and the four exports.
- The pack's figures equal the dashboard's for the same period, proved by a test that
  reads both.
- No unconfirmed draft and no comment text appears in the pack.
- The text is the tenant's default language, and a second language produces the same
  numbers with different headings.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.home apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/exports/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- AI output is labelled until a person confirms it, and an unconfirmed draft never
  travels.
- One source for a number: the pack reads the dashboard's functions.
- Exports are jobs; the request returns before the file is built.

### c12-exit-export: the final export and its checksum

**Requirements:** REP-04
**Scenarios:** contributes to REP-S5
**Depends on:** `c12-exit-request`, `c12-export-inventory`, `c12-export-changes-cases`, `c12-export-audit-log`, `c12-config-logic`, `c9-evidence`, `c9-case-file-export`, `c10-comments-api`
**Minutes:** 40

Build `backend/apps/reports/exports/tenant_export.py` and register it for the
`tenant_export` kind: one archive holding the register, the cases with their assessments,
actions, evidence files and sign-offs, the comments, the configuration snapshot, the
footprint history and the audit log, each in an open format (`csv` or `json`, files as
they were stored), with a manifest listing every file, its row count and its SHA-256.
- It walks the lifecycle registry (ruling 5), so a tenant table nobody covered fails the
  export's own guard test rather than being silently missing — the same guard ruling 36
  asks for, run here and in `c12-exit-execute`.
- The job records the archive's SHA-256 on the `ExportJob` row and links the job to the
  exit request; the first download sets `downloaded_at`, which `c12-exit-execute` requires.
- The export runs while the tenant is `closing` (the allowlist), and it is the one export
  that may be created by a `closing` tenant.

**Owned paths:**

- `backend/apps/reports/exports/tenant_export.py`
- `backend/apps/reports/tests_tenant_export.py`
- `backend/apps/reports/exports/__init__.py` (its own registry line)
- `backend/apps/shared/lifecycle.py` (its own `covered_by` entries)

**Done when:**

- The export of the seeded tenant holds every table the lifecycle registry lists, and the
  guard fails on a planted uncovered table.
- The manifest's hashes match the files, and the archive's SHA-256 is on the job row.
- The first download sets `downloaded_at` once and writes its audit row.
- Tenant B's rows are nowhere in the archive, proved with both tenants seeded.
- A `closing` tenant can create and download it; nothing else it does is allowed to write.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/exports/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Every tenant table is covered or listed with a reason; the guard decides, not memory.
- Row-level security holds: the export reads under the tenant's own session.
- A secret, a token hash or a passkey's credential never leaves in an export.

### c12-fe-reports-dashboard: the Reports screen

**Requirements:** REP-01
**Scenarios:** REP-S1 (journey half, un-fixmed)
**Depends on:** `c12-card-reports`, `c12-dashboard-workload`, `c12-dashboard-summary`, `c12-e2e-seed`
**CLAUDE.md §11 applies in full.**
**Minutes:** 40

Build `frontend/src/features/reports/` (types, api, hooks, `reports-presentation.ts`) and
`frontend/src/app/(tenant)/reports/page.tsx` from `design/screens/tenant-reports.html`:
the four figures, the urgency bars, the regime-by-account heat table, source coverage,
the compliance-status bars, the gap rows and the overdue actions, each panel loading from
its own endpoint and each absent with a one-line notice where the reader's permissions do
not cover it.
- Presentation functions turn keys into pills and labels; no tone is chosen in a
  component, and `tone-by-kind.ts` gains only this screen's entries.
- The navigation registry gains the Reports destination.
- The journey signs in through the UI, opens Reports, asserts each panel and its figures
  against the seed, and opens a gap row through to the obligation page.

**Owned paths:**

- `frontend/src/features/reports/*`
- `frontend/src/app/(tenant)/reports/page.tsx`
- `frontend/src/components/reports/*`
- `frontend/src/messages/reports/en.json`, `sv.json`
- `frontend/src/shared/navigation/registry.ts` (its own entry)
- `frontend/src/features/shared/tone-by-kind.ts` (its own entries)
- `frontend/tests/e2e/reports.journey.spec.ts` (the REP-S1 block only)
- `backend/apps/reports/app.md` (the REP-S1 status cell)

**Done when:**

- REP-S1's journey is green against the real stack on the seeded data.
- Each panel comes from its own request, and the screen reaches real data inside the
  500 ms budget measured against `next start`.
- A reader without `register.read` sees the permission-limited notice and no zero.
- Lint, typecheck, unit coverage, `check:messages`, `check:copy-drift` and the production
  build are green; both themes and 375 px pass.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "REP-S1"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Pills only through `Pill`, one presentation function per record type.
- No string literal in JSX; typography roles only.
- The screen calls no stub; it mocks no API in its journey.
- A permission-limited panel is absent, never a false zero.

### c12-import-register-commit: the commit, in one audited transaction

**Requirements:** REP-03
**Scenarios:** REP-S4 (integration half, un-skipped)
**Depends on:** `c12-import-register-dryrun`, `c8-reg-applicability`, `c8-ten-teams`, `c3-provision-read`
**Minutes:** 40

Build the write half of `backend/apps/reports/imports/register.py`:
- `commitImport` applies the reviewed mapping in one transaction: register entries created
  or updated, unknown values created as vocabulary rows through the vocabulary's own
  creation path (so AC-VOC3's near-duplicate check still runs), and applicability filed as
  **requests** for a second person (the default), never as decisions.
- One `record()` audit row records the import with its mapping and its counts; each
  created register row also carries its own audit row, as every write does.
- A second commit answers 409 `import_already_committed` and writes nothing, and a commit
  whose dry run is stale (the register changed under it) answers 409 `stale_write` with
  what changed.
- A row that fails leaves the whole commit unapplied: it is one transaction, and the
  result says which row stopped it.
- Then un-skip REP-S4's integration half.

**Owned paths:**

- `backend/apps/reports/imports/register.py` (the commit half)
- `backend/apps/reports/tests_import_commit.py`
- `backend/apps/reports/tests_scenarios.py` (the REP-S4 line only)
- `backend/apps/reports/app.md` (its own status cells)
- `backend/scripts/contract_drift_pending.txt` (its own line)

**Done when:**

- REP-S4's integration half is green: 40 rows, three unknown values, "Complies" mapped
  once to `compliant` and used for every row with it, then a commit whose register rows
  exist and whose audit event records the import with the mapping.
- Applicability arrives as pending requests; a test proves none is decided.
- A second commit and a stale commit are both refused, and neither writes.
- A failing row rolls the whole commit back, proved by a test.
- Tenant B's register is untouched.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.register apps.taxonomy apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/imports/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- "Applies" and "we comply" stay separate facts, and an import cannot decide
  applicability for one person.
- `record()` on every write, in the same transaction as the write.
- `If-Match` and `stale_write` on versioned records.
- Vocabularies are rows; a new value goes through the vocabulary's own door.

### c12-exit-execute: the operator deletes the bank

**Requirements:** REP-04
**Scenarios:** REP-S5 (integration half, un-skipped), REP-S8 (un-skipped)
**Depends on:** `c12-exit-export`, `c12-ledger-purge-function`, `c12-tenant-deleted-status`
**Security review:** yes (a deletion that cannot be undone)
**Cloud rule:** carries the stop-and-report instruction
**Minutes:** 40 (stopping point in rule 14)

Three pieces:
1. **The function.** `cw_delete_tenant(tenant uuid)`, created by a migration, owned by
   `cw_migrator`, EXECUTE never granted to `cw_app`, not `SECURITY DEFINER` (ruling 2). It
   deletes every table the lifecycle registry lists — the audit log, the outbox, the
   security log and footprint history included — the tenant's rows in mixed tables (its
   problem reports; a proposal that resolved one stays), its private instruments and
   obligations with their append-only children, memberships, then the users left with no
   membership and no platform role together with their assertions, passkeys and sessions.
   It returns counts before and after.
   **Platform security-log rows naming a deleted user go with them** (item 9 of
   `OWNER_RECOMMENDATIONS.md`, which asks for the deletion or the window in writing).
   Those rows carry no `tenant_id`, so nothing else would reach them: a sign-in refusal or
   a lockout naming a user who has just been deleted would leave that person's identifier
   on the platform after the bank left, and the tombstone's counts are what the assurance
   pack points at instead. The function deletes every platform `security_log` row whose
   subject is one of the users it deleted, in the same transaction, before the user rows
   go, and counts them in the tombstone. A row naming a user who is kept (a former member
   still named by a library record) stays, because that user stays.
   **The session it runs in.** `cw_migrator` is `NOBYPASSRLS` and every tenant table is
   under **forced** row-level security, so the owner sees no more than a policy lets it:
   with no `app.tenant_id` set, each policy matches nothing, the function would delete
   nothing, and "verifies zero rows" would pass vacuously. After ruling 1 the append-only
   hatch needs `cw.maintenance` as well. The command therefore sets both for its own
   session before it calls the function — `SET app.tenant_id = <the tenant>` and
   `SET cw.maintenance = 'on'` — and the function raises unless
   `current_setting('app.tenant_id', true)` equals its `tenant` argument, so a session
   pointed at the wrong bank deletes nothing.
   **Never widened.** Neither `ALTER TABLE ... NO FORCE ROW LEVEL SECURITY` nor
   `ALTER ROLE ... BYPASSRLS` may be used to reach the rows, in the migration, the
   function or the command: the way in is the tenant's own policy under the tenant's own
   setting.
2. **The command.** `manage.py execute_tenant_exit <tenant> --confirmed-with "<contact>"`,
   run as `cw_migrator` in a one-off container. It refuses unless the request is approved,
   not cancelled, `execute_after` has passed and the final export was downloaded; it
   refuses a tenant that is not `closing`. It deletes the tenant's storage prefix through
   the seam's list and delete operations, verifies zero rows and an empty prefix, sets the
   tenant to `deleted`, writes the `TenantExitReport` and one platform `record()` row.
3. **The tombstone.** `TenantExitReport` (platform, not a tenant table): counts before and
   after, the export's SHA-256, the requester, the approver and the operator, their
   assertion ids, the confirmation text, the date backups age out, kept for
   `TENANT_EXIT_RECORD_YEARS`. A former member still named by a library record keeps a
   name-only user row with a unique placeholder email.
   The runbook `docs/runbooks/TENANT_EXIT.md` says how to run it, how to re-apply an exit
   after a database restore, and to check regularly for approved exits past their date.

**Owned paths:**

- `backend/apps/reports/models.py` (the report model only), `migrations/000X_exit_execute.py`
- `backend/apps/reports/exit_execute.py`
- `backend/apps/reports/management/commands/execute_tenant_exit.py`
- `backend/apps/reports/tests_exit_execute.py`
- `backend/apps/reports/tests_scenarios.py` (the REP-S5 and REP-S8 lines only)
- `backend/apps/reports/app.md` (its own status cells)
- `backend/apps/shared/adapters/storage.py` (the list and delete-prefix operations only)
- `docs/runbooks/TENANT_EXIT.md`
- `backend/config/settings.py` (its own banner), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- REP-S5 is green to its last line: after the approval and the export, the command deletes
  every tenant row including the audit trail, verifies zero rows and an empty prefix,
  leaves the tenant marked `deleted` with its tombstone, and a later sign-in answers 404.
- **Zero rows means rows went.** Every table's count is asserted **before** the run as
  well as after: non-zero first, zero second, table by table over the lifecycle registry,
  so a session that could see nothing cannot pass the check by deleting nothing. A run
  with `app.tenant_id` unset fails loudly rather than reporting success, and a test proves
  that too.
- Row-level security is still forced on every tenant table after the migration, and
  `cw_migrator` is still `NOBYPASSRLS`, both asserted; the tree contains no
  `NO FORCE ROW LEVEL SECURITY` and no `BYPASSRLS` grant, asserted by a search over the
  migration, the function body and the command.
- REP-S8 is green: the command refuses before the delay, refuses without a downloaded
  export, and `cw_app` is refused both the direct deletes and the function itself.
- A second tenant's rows are untouched, counted before and after.
- A former member named by a library record keeps a name-only row; every other orphaned
  user goes with their passkeys, sessions and assertions.
- No platform `security_log` row names a deleted user afterwards, proved by seeding one
  per deleted user and counting zero; a row naming the kept name-only user is still
  there; and the tombstone carries the count of the platform rows removed.
- The command is idempotent: run twice, the second says there is nothing to do.
- The `SECURITY DEFINER` guard still passes **unchanged**: `cw_delete_tenant` is not
  `SECURITY DEFINER`, so this task adds no entry to that allowlist and touches no guard
  file; a test asserts the function's security type and its owner. The compliance lint is
  green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Deletion at exit is the second named exception to "nothing overwritten" (CLAUDE.md §5,
  D-56); it deletes, it never rewrites.
- `cw_app` can neither call the function nor delete a ledger row.
- No migrator credential exists in the API or the worker; the command is a one-off
  container.
- Two different people, each with a passkey, stand behind every deletion.

### c12-config-jobs: configuration in and out as jobs

**Requirements:** VOC-09
**Scenarios:** VOC-S13 (integration half, un-skipped)
**Depends on:** `c12-config-policies`, `c12-exports-contract-b`, `c12-imports-contract`
**Security review:** yes (a configuration import writes roles and permissions)
**Minutes:** 30

Register two builders: `reports/exports/configuration.py` for the `configuration` export
kind (`json`, from `taxonomy/configuration.py`'s snapshot, behind `exports.create` and the
step-up every export has) and `reports/imports/configuration.py` for the `configuration`
import kind (behind `vocab.manage` **and** `roles.manage` with a step-up, the gate
`c12-imports-contract` declared for this kind, with the dry run the import framework
already runs and a commit in one transaction).
- The import applies creates and updates by key, reports conflicts and applies none of
  them, and never changes a system row in a way VOC-S14 refuses.
- A snapshot from another product, another schema version or a missing version stamp is
  refused with 422 and a message that says what was expected.
- Roles and permissions in a snapshot are intersected with `TENANT_PERMISSIONS` before
  anything is written, so an edited file cannot grant `proposals.review` (hardening H2's
  lesson, applied at a second door).
- A role or permission the snapshot changes is written only under the commit's
  `roles.manage` gate and its fresh assertion, and each such write is a `record()` row
  carrying the assertion id, so a role change made by import looks in the audit log
  exactly like one made on the Roles screen.
- Then un-skip VOC-S13 and add its `@e2e` tag, naming `c12-fe-data-configuration` for the
  journey half.

**Owned paths:**

- `backend/apps/reports/exports/configuration.py`, `imports/configuration.py`
- `backend/apps/reports/tests_config_jobs.py`
- `backend/apps/reports/exports/__init__.py`, `imports/__init__.py` (own registry lines)
- `backend/apps/taxonomy/tests_scenarios.py` (the VOC-S13 line only)
- `backend/apps/taxonomy/app.md` (VOC-S13's tags and its own status cells)

**Done when:**

- VOC-S13's integration half is green: an export keyed by immutable keys with a version
  stamp, and an import into another tenant whose dry run lists creates, updates and
  conflicts before anything commits.
- A snapshot with an unknown schema version, and one with a permission outside
  `TENANT_PERMISSIONS`, are both refused and write nothing.
- A commit by a `vocab.manage` holder without `roles.manage` answers 403 and writes
  nothing; one without a fresh assertion answers 403 `step_up_required`; with both, every
  role and permission row written carries the assertion id on its audit row, proved row
  by row.
- A conflict blocks its own row only, and the result names it.
- The commit writes one audit row for the import and one per row written.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.reports apps.taxonomy apps.identity apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/reports/*,apps/taxonomy/configuration.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Permissions are constants in code; a file can never widen them.
- A passkey step-up stands in front of every role and permission change (CLAUDE.md §5),
  whichever door it comes through.
- Vocabularies are rows, compared by key.
- `record()` on every write; a dry run writes nothing.

### c12-fe-exports: the exports on the Reports screen

**Requirements:** REP-02
**Scenarios:** REP-S2 (journey half, un-fixmed)
**Depends on:** `c12-fe-reports-dashboard`, `c12-committee-pack`, `c12-export-inventory`, `c12-export-changes-cases`, `c12-export-audit-log`, `c4-fe-audit-log`
**CLAUDE.md §11 applies in full.**
**Minutes:** 40

Add the export controls to the Reports screen and the audit log screen: "Show committee
pack", the export menu (inventory, changes, cases, audit log, configuration), the format
choice where the kind offers one, the step-up dialog, the job's status polled until it is
ready, the download, and the states for failed and expired.
- The step-up uses the existing step-up flow; nothing about exports invents a second one.
- Polling backs off and stops; a failed job shows its user-facing message, never a trace.
- The journey (REP-S2) exports the inventory and the audit log through the UI with a
  passkey step-up, waits for each job, downloads each file, and asserts the audit rows
  through the audit log screen.

**Owned paths:**

- `frontend/src/features/reports/*` (the export hooks and presentation only)
- `frontend/src/components/reports/ExportMenu.tsx`, `ExportStatus.tsx`
- `frontend/src/messages/reports/en.json`, `sv.json`
- `frontend/tests/e2e/reports.journey.spec.ts` (the REP-S2 block only)
- `backend/apps/reports/app.md` (the REP-S2 status cell)

**Done when:**

- REP-S2's journey is green against the real stack, downloading real files.
- An export without a fresh assertion shows the step-up dialog, declared to the API guard
  as the one expected 403.
- An expired export shows its state and offers a new export, never a broken download.
- Lint, typecheck, unit coverage, `check:messages`, `check:copy-drift` and the build are
  green; both themes and 375 px pass.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "REP-S2"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- The screen calls no stub and mocks no API.
- The client branches on `code`, never on `detail`.
- Pills through `Pill`; no string literal in JSX.

### c12-fe-data-import: the import panel

**Requirements:** REP-03
**Scenarios:** REP-S4 (journey half, un-fixmed)
**Depends on:** `c12-card-data-a`, `c12-import-register-commit`, `c12-imports-contract`, `c12-e2e-seed`, `c12-fe-data-retention`
**CLAUDE.md §11 applies in full.**
**Minutes:** 40

Add the import panel to `/admin/data` from `design/screens/admin-data.html`: the file
field with its limits in words, the upload, the dry run's summary (created, updated,
conflicts, unknown values), the one-question-per-value mapping with "use an existing
value" and "suggest a new one", the row errors with their line numbers, and Commit with
what it will write spelled out, including that applicability becomes requests for a second
person.
- The journey (REP-S4) uploads the seeded fixture through the UI, reads the dry run, maps
  "Complies" once, commits, and finds the register rows and the audit event.

**Owned paths:**

- `frontend/src/features/data/*` (the import hooks and presentation only)
- `frontend/src/components/admin/ImportPanel.tsx`
- `frontend/src/messages/data/en.json`, `sv.json`
- `frontend/tests/e2e/reports.journey.spec.ts` (the REP-S4 block only)
- `backend/apps/reports/app.md` (the REP-S4 status cell)

**Done when:**

- REP-S4's journey is green against the real stack with the real file upload.
- Each unknown value is asked once; answering it updates every row that carries it.
- A row error shows its line number and its message, and Commit stays disabled while a
  value is unmapped.
- Lint, typecheck, unit coverage, `check:messages`, `check:copy-drift` and the build are
  green; 375 px and both themes pass.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "REP-S4"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- No string literal in JSX; every limit stated in words a user reads.
- The screen calls no stub and mocks no API.
- Uploaded content is untrusted: the screen never renders a cell as HTML.

### c12-security-review: the chunk's sweep

**Requirements:** all of chunk 12
**Scenarios:** none
**Depends on:** `c12-exports-contract-b`, `c12-imports-contract`, `c12-import-register-commit`, `c12-retention-purge`, `c12-ledger-purge-function`, `c12-tenant-deleted-status`, `c12-exit-request`, `c12-exit-execute`, `c12-config-jobs`
**Minutes:** 40

One security-review sub-agent over `git diff` of every chunk 12 backend merge, against
the invariants of CLAUDE.md §5 and this brief's rulings. It reads, in particular:
- the hatch predicate and the `SECURITY DEFINER` allowlist (ruling 1), and that nothing
  else in the tree opens the hatch;
- that `cw_app` can neither delete a ledger row directly nor call `cw_delete_tenant`, and
  that no migrator credential reaches the API or the worker (ruling 2, rule 12);
- every new route's permission, step-up and four-eyes shape, and that no policy on a
  tenant table is keyed on a session flag;
- every export builder for what it can leak: another tenant's rows, a standard's licensed
  text, a secret, an evidence file, comment text, an unconfirmed draft;
- the import for what an uploaded file can do: formulas, traversal, decompression,
  permissions widened through a configuration snapshot;
- the lifecycle registry's coverage and the exit export's guard;
- that every deletion path is filtered by the tenant and bounded by the floor.
It writes `docs/reviews/2026-XX-XX-chunk12-security.md` with findings by severity. A
critical or high finding blocks the merge of whatever it names; anything lower becomes a
`HARDENING.md` row.

**Owned paths:**

- `docs/reviews/` (its own file)
- `docs/plans/briefs/HARDENING.md` (its own rows)

**Done when:** the review file exists, every finding has a severity, an owner and either a
fix task or a HARDENING row, and the guards it exercised are named with their commands.

**Gates:** the full backend suite and every guard module, run once on the reviewed tree.

**Invariants:** a review lowers no gate and writes no product code.

### c12-fe-data-exit: the exit panel

**Requirements:** REP-04
**Scenarios:** REP-S5 (journey half, un-fixmed)
**Depends on:** `c12-card-data-b`, `c12-exit-request`, `c12-exit-export`, `c12-exit-execute`, `c12-tenant-deleted-status`, `c12-fe-exports`, `c12-fe-data-import`
**CLAUDE.md §11 applies in full.**
**Minutes:** 40

Add the exit panel to `/admin/data`: what leaving does in order and in the bank's own
words, Request with its step-up, the pending request with who asked and when, Approve for
a second `security.manage` holder with their own step-up (and the refusal the requester
sees), the countdown to execution, the final export with its checksum and its download,
Cancel with its step-up, and the read-only banner every screen shows while the tenant is
`closing`.
- The journey (REP-S5) runs on the **second** seeded tenant (`c12-e2e-seed`): the admin
  requests the exit, the same person is refused their own approval (declared to the API
  guard), a second admin approves, the banner appears, a write elsewhere is refused with
  its message, the final export is downloaded, and the journey then cancels the exit so
  the seed is restored. Execution itself is the operator's command and is proved by
  REP-S5's integration half, not by the journey.

**Owned paths:**

- `frontend/src/features/data/*` (the exit hooks and presentation only)
- `frontend/src/components/admin/ExitPanel.tsx`
- `frontend/src/components/shell/ClosingBanner.tsx`
- `frontend/src/messages/data/en.json`, `sv.json`
- `frontend/tests/e2e/reports.journey.spec.ts` (the REP-S5 block only)
- `backend/apps/reports/app.md` (the REP-S5 status cell)

**Done when:**

- REP-S5's journey is green and leaves the seed as it found it.
- The requester's own approval is refused in the UI with the message, not a blank error.
- The read-only banner appears on every screen while the tenant is `closing`, and a
  refused write says why in words.
- The panel states that deletion cannot be undone and that the audit trail goes too.
- Lint, typecheck, unit coverage, `check:messages`, `check:copy-drift` and the build are
  green; 375 px and both themes pass.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "REP-S5"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Four eyes with a passkey step-up, visible as such on the screen.
- Teardown restores seeded data on failure too.
- No string literal in JSX; the client branches on `code`.

### c12-review-fixes: close the review's findings

**Requirements:** whatever the review names
**Scenarios:** none
**Depends on:** `c12-security-review`
**Minutes:** 35

Fix every critical and high finding of `c12-security-review`, each with the test that
fails first. A finding that turns out to need a design decision goes to
`docs/TODO_FOR_alex.md` with the recommendation, and the review file records which
findings were fixed here and which were deferred, with the reason.

**Owned paths:** the files each finding names, and `docs/reviews/` (the outcome lines),
`docs/plans/briefs/HARDENING.md`, `docs/TODO_FOR_alex.md`.

**Done when:** no critical or high finding is open; each fix has its own test; the whole
backend suite, the guards and the compliance lint are green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:** a fix never lowers a gate, skips a test or weakens a guard.

### c12-fe-data-configuration: the configuration panel

**Requirements:** VOC-09
**Scenarios:** VOC-S13 (journey half, un-fixmed)
**Depends on:** `c12-card-data-a`, `c12-config-jobs`, `c12-fe-exports`, `c12-fe-data-exit`
**CLAUDE.md §11 applies in full.**
**Minutes:** 35

Add the configuration panel to `/admin/data`: what a configuration export contains in
plain words, Export with its step-up and the job's status, and Import with its file field,
its dry run (creates, updates, conflicts, each with its key) and its commit.
- Commit asks for a passkey, because the snapshot carries roles and their permissions, and
  the panel says so in the bank's own words before the file is chosen.
- The journey (VOC-S13's `@e2e` half, in `frontend/tests/e2e/taxonomy.journey.spec.ts`,
  because CLAUDE.md §10 puts a scenario's journey in the spec of the app whose `app.md`
  carries it, and VOC-S13 is `taxonomy`'s) exports the configuration, uploads it into the
  second seeded tenant, reads the dry run, confirms the commit with a passkey, and finds
  the vocabulary rows there with their keys.

**Owned paths:**

- `frontend/src/features/data/*` (the configuration hooks and presentation only)
- `frontend/src/components/admin/ConfigurationPanel.tsx`
- `frontend/src/messages/data/en.json`, `sv.json`
- `frontend/tests/e2e/taxonomy.journey.spec.ts` (the VOC-S13 block only)
- `backend/apps/taxonomy/app.md` (the VOC-S13 status cell)

**Done when:**

- VOC-S13's journey is green against the real stack, across two tenants.
- A conflict is shown with its key and its reason, and Commit applies the rest.
- Lint, typecheck, unit coverage, `check:messages`, `check:copy-drift` and the build are
  green; 375 px and both themes pass.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`
- `npm run test:e2e -- --grep "VOC-S13"`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Keys, never labels, on screen as in the API.
- The screen calls no stub and mocks no API.
- No string literal in JSX.

### c12-close: the chunk closes

**Requirements:** REP-01 to REP-04, AUD-04, VOC-09
**Scenarios:** none (it proves every owner's scenario is green)
**Depends on:** every task above
**Minutes:** 40

- Run the whole checklist: `bash scripts/prepush.sh --all`, the full E2E suite, and
  `migrate_from_zero`.
- Prove no chunk 12 route answers 501 and that `contract_drift_pending.txt` holds no
  chunk 12 line.
- Prove the lifecycle guard and the exit export's coverage guard are green, as ruling 36
  of the parallel plan requires of this close and of `c14-close`.
- Set the chunk 12 coverage floors in `backend/scripts/coverage_gate.py`, measured on this
  tree, with the date beside each; lower none.
- Update `backend/apps/reports/app.md`, `governance/app.md`, `taxonomy/app.md` and
  `tenants/app.md` status cells to `built` where the scenario is green and `verified`
  where a journey proves it end to end; leave anything later-chunk as it is, named.
- Update `docs/plans/IMPLEMENTATION_STATUS.md` and the UI plan's chunk 12 rows and
  statuses.
- Copy into `docs/TODO_FOR_alex.md`: the two open questions of this brief with their
  recommended options, and every "to confirm" default listed above.
- Record in `docs/plans/Verification_Log.md` anything fetched during the chunk (the
  spreadsheet reader's documentation, and any provider page the storage seam needed).

**Owned paths:**

- `backend/scripts/coverage_gate.py`
- `backend/apps/*/app.md` (status cells)
- `docs/plans/IMPLEMENTATION_STATUS.md`, `docs/plans/UI_Implementation_Plan.md`
- `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`

**Done when:** every gate above is green on one tree, every chunk 12 scenario its
ownership table names is un-skipped and passing, no 501 is left, and the status files say
what `git log` says.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `bash scripts/prepush.sh --all`
- `cd frontend && npm run test:e2e`

**Invariants:** never lower a gate, skip or quarantine a test, or mock an API in E2E.
