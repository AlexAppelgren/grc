# Chunk 14: tasks

Written 2026-09-20 by the planning workflow (read, plan, parallelism and coverage critiques, revise). Each task runs in its own worktree or cloud session (`docs/runbooks/WORKTREES.md`). A task starts once everything in its depends-on is on `main`. The task ids are the `c14-` package ids of `docs/plans/PARALLEL_PLAN.md` section 3.3; nothing is renamed, added or dropped, and where a package is split the halves keep the package id with an `-a` / `-b` suffix, as `c4-close-a` and `c14-owasp-fixes-*` already do. Five ids are new: the two halves of hardening task H-C and the H6 follow-up, which no other brief owns; the chunk's E2E seed; and the two tasks that serve `startEvalRun`, which `c7-eval-routes` hands to chunk 14 by name.

## Revised 2026-09-20

A review of the first version raised seven MEDIUM findings and one LOW, most of
them from PRD 0.4's `governance/app.md` and from the two ADRs accepted on
2026-09-20. What changed, and which finding each change closes:

| Change | Closes |
|---|---|
| `ADM-S7` (PRD 0.4: "The console reads each bank's figures through one audited window") gains an owner. `c14-billing-usage-b` un-skips it for the figures, the platform audit row and the window's two refusals; its failed-jobs line is closed by `c14-health-backend-b`, and its retry line waits for `q-retry-write` | MEDIUM: ADM-S7 had no owner in this chunk |
| `ADM-S6`'s plans clause, which PRD 0.4 adds by rewording the scenario to "Tenants, plans and support access are managed from the console", goes to `c14-billing-plans` (integration) and `c14-e2e-billing` (journey). It can go green nowhere else: chunk 4 and chunk 8 have no plan to assign | MEDIUM: ADM-S6's plans clause had no owner |
| Per-bank lag is a typed counter, `lag_seconds`, written by the outbox publisher and the SIEM delivery job on their own `job_run` row and added by `c14-job-runs-b`; the console reads the latest such row per bank inside the window. The plan no longer reads the lag "from `job_run` alone" as if the outbox were in it, and `outbox_event` is never added to the window map | MEDIUM: after H-C a no-tenant session sees only NULL-tenant outbox rows, and ADR 0052 bars outbox payloads from the window |
| `c14-job-runs-b` builds `rebuild()` and the model and writes no ADR amendment. `retryConsoleJob` stays 501 `not_built` until Alex answers `q-retry-write`, which the main agent put to him on 2026-09-20; `c14-health-backend-b`, `c14-fe-health-b`, `c14-e2e-health` and `c14-close` follow | MEDIUM: the console retry writes inside a tenant, against accepted ADR 0042, and the plan pre-wrote the amendment |
| `c14-close` gains `c14-eval-runs` and `c14-fe-eval-run` in its depends-on, the two tasks that clear the `startEvalRun` line it proves gone | MEDIUM: `c14-close` required a pending line it did not wait for |
| Section 4 gains item 7, D-61's open point (who pays for a tenant's agents), which section 1.4 had taken as a default although `DECISIONS.md` marks it open. Section 4 and `c14-close` now both say seven | MEDIUM: six confirmations against seven |
| Rule 14 names the green point at which `c14-shared-scenarios`, `c14-job-runs-b`, `c14-billing-usage-a`, `c14-eu-data-location-a` and each `c14-perf-*` pass stops, and the derived id that takes the rest | LOW: five tasks at the hour with no stopping point named |
| Section 4 item 3 is recorded as a default taken, not a question: billing/app.md §1 already rules out self-service checkout, which ruling 4 cites. Item 5 cites `PARALLEL_PLAN.md` 7.3's `people` row and asks only the order. `c14-fe-usage-a` drops its ADM-01 claim, which section 1.4 itself contradicts | MEDIUM: questions the sources already answer |

## 1. Scope

Chunk 14 plan: hardening, the assurance pack, billing and usage, system health, and the EU data-location guard. `Build_Plan.md` gives the chunk NFR-02 (performance budgets), NFR-04 (EU-only hosting and the assurance pack of playbook 18) and NFR-05 (billing: plans, limits, usage). `PARALLEL_PLAN.md` section 3.3 gives it 37 packages; section 8 gives it the hardening follow-ups nobody else owns. The plan below has **58 tasks in 16 waves**, about 33 agent-hours of package work plus review.

### 1.1 Preconditions: what must be on main before wave 1

- **Nothing.** Six tasks of wave 1 depend on nothing at all (`h-c-mixed-zones` needs only `c3-append-only` and the H-B commit `f336cce`, both on `main`; `c14-perf-harness-a`, `c14-owasp-scope`, `c14-cards-console-usage-a`, `c14-assurance-locations-a` and `c14-assurance-continuity-a` depend on nothing). Chunk 14 therefore starts at hour 0 of the parallel plan and runs alongside every other chunk; it is not a tail.
- **Each later task carries its own external dependencies** in its depends-on line, exactly as `PARALLEL_PLAN.md` 3.3 states them. The heaviest are `r1-readiness` (for `c14-eu-data-location-*` and `c14-job-runs-*`, parallel-plan rule 11: security-critical R2 and R3 work waits for R1), `c4-console-tenants-api` (for the billing contract), `c12-exit-deletion` and `c12-exit-export`, `c13-siem-stream`, `c13-ip-allowlist` and `c13-sso-oidc` (for the exit-controls document), and each area's chunk close (for its OWASP review and its performance pass).
- **`h-c-mixed-zones` is not a chunk 14 dependency; it is everybody's.** See ruling 2.

### 1.2 What it delivers

- **The two open hardening findings.** H15 (high): mixed tables get the split policy `agent_run` already has, so a bank session can no longer insert, change or delete a platform row at the database level. The H-B review's addition: the append-only hatch is allowed by role allowlist rather than by refusing one name, no `SECURITY DEFINER` function and no cascading foreign key can reach an append-only table, and the compliance lint sees the quoted spelling. H6 (low, design): a machine translation is confirmed through the proposal door, so the append-only ledger keeps its shape and the library keeps its one door.
- **NFR-04, EU data location.** The production boot refuses every processor outside an EU member state, from allowlists that are constants in code (ADR 0047, D-54): `anthropic` and `managed_agents` refused, Bedrock only in the six EU regions with an in-region model id, the embedder and reranker `none` or Bedrock under the same rule, Sentry only on `ingest.de.sentry.io`, mail and storage only from reviewed host lists, Railway only in `europe-west4-drams3a`. `ENVIRONMENT=test` is exempt and says so on screen. Two new scenarios, NFR-S20 and NFR-S21, and one boot subprocess test per rule.
- **NFR-04, the assurance pack.** `docs/assurance/` with the subprocessor register, a data-flow diagram per zone, RTO and RPO with the backup restore test log, the incident notification runbook, the exit plan, and the access-control statement (SIEM stream, IP allow-list, support access log). Every fact that nobody has verified is written as unverified with a `TODO_FOR_alex.md` row beside it.
- **NFR-05, billing.** A `plan` with typed integer limits and a price in integer minor units, assigned to a bank from the console; `usage_record` metered by the worker from facts that already exist; the limits enforced where a tenant acts, with 422 `above_plan_limit`; the figures on the tenant's own screen and, through the ADR 0052 window, per bank in the console.
- **ADM-02, system health.** `GET /console/health` under `system.health` with components, source coverage, recent runs, per-bank outbox and SIEM lag as a counter the jobs themselves write, and the failed-jobs list. `POST /console/jobs/{jobId}/retry` is declared and left at 501 until Alex answers `q-retry-write` (section 4); its `rebuild()` is built and proved in the worker. Behind all of it, `job_run`: one row per worker job, holding numbers, kinds and times only, never an exception message.
- **NFR-02, the performance pass.** One harness (R1, used by `r1-perf`), five API passes over the whole product and one screen sweep against `next start`, each recording its measurement.
- **The OWASP review until findings converge**: one scope document, five area reviews, five fix packages and one convergence pass.
- The four screens the above needs, their design cards, their journeys, the operator runbooks, and the chunk close.

### 1.3 Rulings where the sources disagree

1. **Two decisions that gated this chunk are answered; no task re-asks them.** `q-eu-guards` is answered by Alex's item 7 (D-54, ADR 0047) and `q-platform-counters` by item 12 (D-59, ADR 0052). `PARALLEL_PLAN.md` 7.1 still lists both as blocking and its "If late" columns still describe fallbacks; those rows are closed. Reviews of the chunk 5, 7 and 8 plans blocked on exactly this (re-asking a decided point, or planning the rejected option), so every chunk 14 task builds the accepted design and nothing waits.
2. **`h-c-mixed-zones` is listed here only because no other brief owns it, and it must run first of everything.** `OWNER_RECOMMENDATIONS.md` says problem reports, private records, platform counters and the search index all build on H-C, "so schedule it first". `PARALLEL_PLAN.md` section 8 lists H1 to H10 and has no row for H11 to H15; H11 and H12 are on `main` (`f336cce`), H13 belongs to `h-a-guards` and H14 to `f03-T01`, which leaves H15 and the H-B review's addition with no package anywhere. They are R1 work, not R3: the plan-5 review raised a HIGH finding on `ai_generation` that rests on the split shape, and `OWNER_RECOMMENDATIONS.md` schedules problem reports, private records and the platform counters on top of it. Chunk 7 has since removed its own dependency by building `agent_run`'s split shape directly in `c7-search-index-model`, which is the right answer for a new table and leaves the five existing mixed tables still on the broken shape. `HARDENING.md` also now records that `problem_report` keeps the plain split and gets no platform read window (D-50), which `chunk4-T16` pins — so `h-c-mixed-zones` builds the split and nothing on top of it. So `h-c-mixed-zones` and `h-c-hatch-allowlist` are wave 1 and 2 here, they are dispatched as soon as a slot is free rather than when chunk 14 starts, and `c14-close` checks that `PARALLEL_PLAN.md` section 8 gained a row for each.
3. **Money is an integer minor unit; `schema.sql` says `numeric`.** `plan.price_monthly numeric(10,2)` and `usage_record.quantity numeric` contradict playbook 4.3, billing/app.md ("never as a float and never anywhere else in the product"), `PARALLEL_PLAN.md` 7.2 and ADR 0052. The build wins: `price_monthly_minor` is an integer with a `currency` kind column, and `quantity` is a `bigint`. INPUT_DELTAS §7 carries both rows, written by `c14-billing-contract-a`.
4. **There is no payment provider, so `tenant_subscription`, `invoice`, `feature_flag` and `tenant_feature` are not built.** billing/app.md §1: "There is no self-service checkout: contracts are signed with banks, and a plan is assigned from the console." A bank's plan is a nullable foreign key on `Tenant`; there is no period, no provider id, no invoice mirror and no feature flag table, because nothing in the PRD or in a scenario reads one. Seats are the `seats` usage metric, never a stored counter and never a count of `membership` (ADR 0052: "the seat count comes from the seats metric, never from reading membership").
5. **Plan limits are typed integer columns, not `jsonb`.** `schema.sql` gives `plan.limits jsonb` and `features text[]`. CLAUDE.md allows a `JSONField` only with a named schema, ADR 0052 refuses an untyped JSON column on `usage_record`, and five integers need no document. `plan` gets `max_members`, `max_agents`, `min_cadence_hours`, `ai_budget_minor` and `max_storage_bytes`; `features` is cut.
6. **`job_run` holds no free text.** `schema.sql` gives it `stats jsonb` and `error text`. ADR 0052 replaces both: an `error_code` kind, typed integer counters, `attempts`, and a typed `subject_kind` plus `subject_id` so a retry can rebuild the job. A structural test refuses a free-text or untyped JSON column on `job_run` and on `usage_record` while allowing kind columns.
7. **`/health/` and the console's system health are two different things.** `apps/shared/health_check.py` serves the unauthenticated `/health/` the platform's own monitor calls; it is not touched. The console surface is `GET /console/health` under `system.health`, which calls the same component checks and adds coverage, runs, lag and failed jobs. ADM-S5 reads both, which is what its Gherkin already says ("/health/ answers 503 … and the screen shows it").
8. **The console never reads a bank's rows.** Every console figure comes through `tenancy.platform_counters()` on `usage_record` and `job_run` alone (ADR 0052), never through a support grant, never through a policy keyed on a session flag on a tenant table, and never through `cw_migrator` credentials in the API process. The chunk 8 plan was blocked for proposing the last two; this plan builds the `identity_lookup()` shape that is already on `main` instead.
9. **A review reports; a fix package pushes.** An OWASP review changes no code, lowers no gate and closes no finding. Its fix package owns only the files the findings name. A finding that can be closed only by weakening an invariant in CLAUDE.md §5 is a stop-and-ask for Alex, never a quiet exception.
10. **`ADM-S4`'s integration half is extended once.** Two chunk 14 tasks add console destinations (plans, and system health), and ADM-S4's integration test walks "every console destination and endpoint that exists". `c14-health-backend-a` extends it once for both, and therefore depends on `c14-billing-contract-b`. The journey half is `c14-e2e-health`'s, which depends on both screens.
11. **`NFR-S8` and `NFR-S9` are un-fixmed here, although they are R1 work.** The pill gallery spec and the contrast test have been on `main` since chunk 0, but nobody pointed the two stubs in `shared.journey.spec.ts` at them and no R1 package owns the un-fixme. `c14-shared-scenarios` takes them, which is why its lane changes from `cloud` to `cloud+e2e`. If an R1 package un-fixmes them first, the task simply finds them green and says so.
12. **The in-worker EU agent runner is not chunk 14's.** ADR 0047 tranche 2 ("the in-worker agent runner on Bedrock EU") is due "before the first bank tenant", and `PARALLEL_PLAN.md` says a new package builds it with ADR 0007's third tranche. Chunk 14 builds only the boot rules, which means production boots with `AGENT_RUNNER=none` and runs no agent until that package lands. `c14-eu-data-location-a` writes that consequence into `TODO_FOR_alex.md`; it does not build the runner.
13. **`c14-billing-contract` is three tasks, not one.** The plan sizes it at 60 minutes and gives it models, routes and behaviour. The reviews of the chunk 5, 7 and 8 plans each raised oversized packages as a finding, and parallel-plan rule 2 wants the contract declared before anything serves it. So: `-a` builds the models, `-b` declares the six routes at 501 behind their real gates, and `c14-billing-plans` serves the four plan routes. The same reasoning splits nine other packages (section 1.6).

### 1.4 Defaults taken (each stated in its commit body, and copied into `docs/TODO_FOR_alex.md` by `c14-close`)

- **The tenant's own usage read is gated by `security.manage`.** PRD §6 has no billing permission and ADM-01 does not list plan or usage among the tenant-admin surfaces, so either an existing permission is reused or the matrix grows. `security.manage` is the admin-only permission the organisation's contractual settings already sit behind (D-49 makes it the support-access approver), and reusing it needs no PRD change. The alternative, a new `billing.read` held by admin and auditor, is a PRD §6 change and is listed under section 4 to confirm.
- **`Plan` is a platform table readable by any session, writable only with no tenant active.** It holds no tenant data; a bank must read its own limits during its own requests, so refusing a tenant session would break `NFR-S18`. Its policy is H-C's split shape: `FOR SELECT` open, `FOR ALL` restricted to a session with no tenant. The price never appears in a tenant response; `GET /tenant/usage` returns the plan's name and limits only.
- **A limit is enforced at the write that would exceed it, and never retroactively.** A bank moved to a smaller plan keeps every member, agent and byte it already has; the next write that would add one answers 422 `above_plan_limit` naming the limit and its figure, and the usage screen shows the overage. Nothing is deactivated, deleted or hidden by a plan change.
- **The last-admin recovery is never limited.** The seats limit does not apply to the recovery invitation that `bootstrap_platform` already allows, so a plan cannot lock a bank out of its own administration.
- **A plan in use cannot be deactivated** (409 `plan_in_use`); it is replaced by moving each bank to another plan first. No plan is ever deleted, because usage rows and the audit trail reference it.
- **The seeded plan is a fixture, not a price list.** `c14-billing-contract-a` seeds exactly one plan for the E2E database and the local seed; the real plans, with their limits and prices, come from Alex (`PARALLEL_PLAN.md` 7.3, "plans") and are created in the console.
- **A tenant's agent cost is its own.** bleqq's platform-run agents have no tenant (D-61), so their cost is never metered against a bank. A bank's "Spend this month" covers its own agents and its own Ask calls, and the budget cap that stops them is the tenant's. `DECISIONS.md` still marks "who pays for a tenant's agents" open under D-61 with exactly that proposal, so this is a default taken from an open point and is section 4's item 7.
- **Retry needs no step-up and no four eyes**, when the route is served. Playbook 4.2 does not list it, ADR 0052 designs it under `system.health` with a platform audit row, and re-running a job the bank's own schedule already asked for is the safe direction. Whether the platform may cause that write at all is `q-retry-write`, which is open.
- **No route in chunk 14 joins `UNGATED_BY_DESIGN`.** `/health/` is already there from chunk 0 and is not changed.
- **`usage_record` is written only by the worker, under `@tenant_task`.** No request path writes a usage row, so a slow month-to-date read can never sit inside a 250 ms endpoint's write.
- **A month is the tenant's own month.** `usage_record.period_start` is the first day of the month in the tenant's timezone, matching how the briefing week is the tenant's ISO week.
- **An assurance document never states an unverified fact as verified.** RTO, RPO, the restore test, Tigris's region, the mail sender's location and the pen-test vendor are all unknown today; each is written as "not verified" with the check that would verify it and a `TODO_FOR_alex.md` row. No document claims a tested recovery time before a restore test log exists.
- **The OWASP review's frame is the OWASP Top 10 (2021) plus ASVS 5.0 level 2**, mapped to this product's five areas; `c14-owasp-scope` fetches both, never recalls them, and logs each in `docs/plans/Verification_Log.md`.
- **A performance pass fixes what it measures, inside the pass.** A measurement over budget that needs a schema change or a design change is recorded as a finding with a proposed patch and named for the owning chunk instead of widening the pass.
- **H6's default is the proposal door.** Confirming a machine translation is a `confirm_translation` proposal applied by `apply.py`, which writes a new translation row with the confirmer recorded. It keeps both invariants: the ledger stays append-only, and proposals stay the only door into the library.

### 1.5 Cut, with reasons

- `tenant_subscription`, `invoice`, `feature_flag`, `tenant_feature`, `plan.features` and every provider column: ruling 4 and 5. Nothing reads them and no scenario asks for one.
- `usage_event`, `tenant_metric_daily` and `search_query_log`: analytics tables. ADR 0052 names all three as things the window must never reach, and no chunk 14 requirement reads one.
- A usage trend or chart: `NFR-S19` asks for "runs, spend against the cap, storage against the limit". A month's figures are three numbers per metric, not a time series; a trend needs `tenant_metric_daily`, which is cut.
- An invoice or billing-email surface: `tenant.billing_email` exists in `schema.sql` and nothing sends to it. No invoice is produced, so the column is not built.
- A per-tenant plan override: a limit that differs from the plan is a second source for the same number. A bank that needs different limits gets its own plan row.
- The in-worker Bedrock EU runner: ruling 12.
- A runtime check of each model call's processing location: ADR 0047 rejected it. The boot rules are the control.
- A screen affordance for H6's translation confirmation: the console proposal queue already lists and approves every proposal kind. Adding a button on the obligation page would put `h6-translation-confirm` into the `obpage` chain for no behaviour. The kind is built; the affordance is named in `TODO_FOR_alex.md`.

### 1.6 Changes from `PARALLEL_PLAN.md`, with reasons

- **Ten packages are split in two, and one into three.** `c14-billing-contract` (ruling 13), `c14-billing-usage` (metering in the worker, then the two reads through the window: two different zones of risk and two different key sets), `c14-billing-limits` (the limits service with seats and agents, then storage and exports, which land in other apps' writers), `c14-job-runs` (the model with its window and guard, then the wiring of every worker job), `c14-health-backend` (the health read, then failed jobs and retry), `c14-eu-data-location` (processors, then services: both hold `bootguard` and must run one at a time anyway), `c14-assurance-locations`, `c14-assurance-continuity` and `c14-assurance-exit-controls` (two documents each), `c14-cards-console-usage` (four cards over two tasks), `c14-fe-console-plans` (the new plans screen, then the assignment control on the console tenant detail, which is another package's file) and `c14-fe-health` (the health panel, then the failed-jobs table). Every one of them was at 50 to 60 minutes, which the reviews of the chunk 5, 7 and 8 plans each raised as a finding against the thirty-minute target.
- **`c14-fe-usage` is split** into the tenant's own usage screen and the console's per-tenant usage panel: two route groups, two catalog namespaces, two backend routes, and they can run side by side.
- **Three tasks are new.** `h-c-mixed-zones` and `h-c-hatch-allowlist` (ruling 2) and `h6-translation-confirm` (section 8 of the parallel plan leaves H6 with no owner: "built with the screens that confirm", and no chunk 3 or chunk 4 task builds a confirm action).
- **`c14-eval-runs` and `c14-fe-eval-run` are new.** `c7-eval-routes` hands `startEvalRun` to chunk 14 by name — "there is no job runner with a status endpoint until `c14-job-runs`" — and moves its line in `contract_drift_pending.txt` from chunk 7 to chunk 14. `c14-close` cannot clear that line without a task that serves the route, and a route with no caller is half a feature, so the console gets its Run control in the same wave group.
- **`c14-e2e-seed` is new.** Every other chunk has a seed package, and `c14-e2e-billing` and `c14-e2e-health` cannot run without a seeded plan, usage rows, a failed job run and a platform admin login. Without it the two journey packages would each extend `e2e_seed.py`, which breaks the "one seed call per task" ledger rule.
- **`c14-shared-scenarios` changes lane** from `cloud` to `cloud+e2e` and gains NFR-S8 and NFR-S9 (ruling 11).
- **`c14-cards-console-usage` widens** from the console usage card to four cards: console plans, console usage, console system health and the tenant's usage screen. Three screens in this chunk would otherwise be built with no design card, which `design/README.md` and CLAUDE.md §2 forbid.
- **`c14-health-backend-a` gains `c14-billing-contract-b`** in its depends-on (ruling 10).
- **`c14-perf-harness` is split** into the API harness and the screen-timing helper. `r1-perf` needs both, `c14-perf-screens` needs only the second, and the five API passes need only the first.
- **New serialization keys:** `billingapi` (`backend/apps/billing/api.py` and `schemas.py`), `billingfe` (`frontend/src/features/billing/`, the bank's own usage), `consolebillingfe` (`frontend/src/features/console-billing/`), `healthfe` (`frontend/src/features/system-health/`). `c14-job-runs-a` holds `auth` (it adds `platform_counters()` to `tenancy.py`) and `mig:shared`, as the plan already says; `c14-billing-contract-a` holds `mig:billing` and `mig:shared` and therefore runs in a different wave from `c14-job-runs-a`.

### 1.7 Changes from the two critiques

- **Parallelism.** The console's billing feature split from the bank's own (`c14-fe-console-plans-a` and `c14-fe-usage-a` were in one wave and both created `features/billing/{types,api,hooks}.ts`; they now own `features/console-billing/` and `features/billing/`, two chains that never queue behind each other, as chunk 6 did for the calendar-feeds screen); the frontend waves re-laid so the console chain runs plans-a, plans-b, usage-b in three waves while the tenant screen and the health screens run beside them; the `billingapi` key (four tasks would have edited `billing/api.py`); `mig:shared` serialised between `c14-billing-contract-a` and `c14-job-runs-a`, which both add a model to `apps/shared`; `migration_helpers.py` serialised between the two H-C halves; the plan-assignment control split out of `c14-fe-console-plans` because it edits `c4-fe-tenants`' screen; ADM-S4's integration half given one owner (ruling 10) instead of two tasks editing one test body; `governance/api.py` written once by `c14-health-backend-a` so `-b` never touches it; the OWASP fix packages given a dispatch rule instead of a fixed owned-path list, because a fix package's files are not known until its review lands; `c14-e2e-seed` extracted so two journey packages do not both edit `e2e_seed.py`.
- **Coverage.** `c14-e2e-seed` had no owner at all; NFR-S8 and NFR-S9 had no owner (ruling 11); ADM-S4's two new console destinations had no owner (ruling 10); H15 and the H-B review's addition had no package anywhere (ruling 2); H6 had no owner; three of the four chunk 14 screens had no design card; the EU rules had one scenario for eight rules, so they became NFR-S20 and NFR-S21 with one subprocess test per rule; nobody deleted chunk 14's lines from `backend/scripts/contract_drift_pending.txt`, so each backend task deletes its own and `c14-close` proves none is left; nobody owned the `docs/assurance/README.md` that the six assurance documents need, so `c14-assurance-locations-a` creates it; `AUD-S7` (mixed tables) asserts only the read rule, so `h-c-mixed-zones` extends it with the write rule it exists to enforce; nothing proved that a console read writes its `platform_counters.read` audit row, so `c14-billing-usage-b` and `c14-health-backend-a` each pin their own; `job_run` would have grown without limit, since D-53's retention names neither it nor `usage_record`, so `c14-job-runs-b` gains a bounded purge with its own setting; playbook 18's penetration test and certification path had no owner, so `c14-owasp-converge` writes both rows; `governance/app.md`'s ADM-S4 note still listed system health and plans as surfaces the scenario cannot reach, so `c14-health-backend-a` removes those two entries; nobody checked that CLAUDE.md §5 gained the two exception lines Alex approved, so `c14-close` checks and names chunk 12 if they are missing; `getConsoleHealth` would have been added to `contract_drift_pending.txt` by the task that serves it in the same commit, so only the two job routes go there; and the second read of `main` after chunks 7 and 8 landed found `startEvalRun` handed to chunk 14 by `c7-eval-routes`, which this plan had cut, so `c14-eval-runs` and `c14-fe-eval-run` build it.

## 2. Plan-wide rules

1. **Slots.** Every backend and E2E gate runs inside the task's slot: `set -a; . ./.env.worktree; set +a`. A cloud session runs `bash scripts/cloud-setup.sh` (with `--e2e` where the gates include E2E) instead.
2. **Contracts first.** A route is declared once, by the contract task named for it, with its auth class, its permission and its step-up, answering 501 `not_built` from a named function in the module that will build it. A logic task owns only its own module and its tests, never `api.py` or `schemas.py`. A logic task that finds the contract wrong stops and reports.
3. **No screen calls a stub.** A screen task depends on every backend task whose routes it calls, and a journey task depends on every screen it walks.
4. **Generated files.** No task commits `openapi.json`, `frontend/src/types/api.generated.ts` or `frontend/tests/e2e/support/e2e-passkeys.generated.ts`. A task regenerates them locally to run `contract_drift.py` and the typecheck, then reverts them. The main agent regenerates and commits them at the merge, and regenerates the navigation and pill snapshot baselines when `registry.ts` changed.
5. **Append ledgers.** Each task adds only its own lines and never edits another's: `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`, `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`, `docs/plans/UI_Implementation_Plan.md` rows and status cells, `docs/plans/briefs/HARDENING.md` rows, `backend/config/settings.py` setting banners, `backend/.env.example` and `docs/runbooks/RAILWAY_VARIABLES.md` blocks, router mounts in `backend/config/api.py`, `backend/apps/shared/kinds.py`, the route lists in `permissions.py`, the guarded-table and window lists in `tests_rls.py` and `tests_seed_integrity.py`, `backend/apps/shared/e2e_seed.py` (one seed call per task), `backend/perf/routes.py`, `backend/perf/baseline.json` and `backend/perf/fixtures_bulk.py` (own entries per performance pass), `frontend/src/shared/navigation/registry.ts` entries, `frontend/src/features/shared/tone-by-kind.ts` entries, each app.md's status cells, each `tests_scenarios.py` (own skip line only) and each `*.journey.spec.ts` (own test blocks only).
6. **Serialization keys held here.** `bootguard` (`c14-eu-data-location-a`, then `-b`); `auth` and `mig:shared` (`c14-job-runs-a`); `mig:shared` and `mig:billing` (`c14-billing-contract-a`); `billingapi` (`c14-billing-contract-b`); `gov` (`c14-health-backend-a`, then `-b`); `apply` and `prop` (`h6-translation-confirm`); `members` (`c14-billing-limits-a`); `billingfe` (`c14-fe-usage-a` alone); `consolebillingfe` (`c14-fe-console-plans-a`, then `-b`, then `c14-fe-usage-b`); `healthfe` (`c14-fe-health-a`, then `-b`); `runner` (`c14-eu-data-location-a`, for the `none` value on the agent-runner adapter); `searchapi` and `evalfe` (`c14-eval-runs`, then `c14-fe-eval-run`); `ten` (`c14-fe-console-plans-b` reads it only, and takes no key). `c14-billing-limits-a` and `-b` add a call site each in files chunk 8, 9, 11 and 12 own, and take each of those packages as a dependency rather than a key, because those packages have merged by then. A key is held from start to merge.
7. **Coverage floors.** `backend/scripts/coverage_gate.py` gets the chunk 14 floors once, from `c14-close`, measured at the close with the date beside each. A task states its own `coverage report --include` threshold in its done-condition and never lowers an existing floor.
8. **Security review before merge** for `h-c-mixed-zones`, `h-c-hatch-allowlist`, `h6-translation-confirm` (the proposal door), `c14-billing-contract-a` (two new tables, one of them tenant), `c14-billing-usage-b` and `c14-health-backend-a` (both read through the platform window), `c14-job-runs-a` and `-b` (the window, its guard and a platform-to-tenant write), `c14-eu-data-location-a` and `-b` (the boot guard), and each of the five `c14-owasp-fixes-*`. The five `c14-owasp-*` reviews are themselves security reviews and need no second one.
9. **Merge at once.** Each task is squash-merged and the full checklist run as soon as it passes review (WORKTREES step 5). Finished work never waits for the rest of the chunk.
10. **Clocks.** Everything dated is anchored to the tenant-local date plus a fixed wall time (CLAUDE.md §8.3 and §11). A usage month, a job run's times and a plan's assignment date are derived from the anchor, never from the real "today": a month boundary would make the usage screen green in September and empty in October.
11. **The OWASP dispatch rule.** A `c14-owasp-fixes-*` package declares its owned paths at dispatch, from its review's findings. The main agent runs the parallel plan's rule 1 dispatch check before starting two fix packages, or a fix package and a performance pass, in the same wave; if their files overlap, the second waits.
12. **E2E.** CLAUDE.md section 11 in full applies to every UI task here and is propagated to its sub-agent: one command against the real stack, a production Next build, sign-in through the UI with a passkey, `test` imported from `support/api-guard`, `seed_e2e` extended rather than mocked, and no API mocked.
13. **Stop rather than weaken.** A finding, a limit or a measurement that can be satisfied only by lowering a gate, skipping a test, adding an `UNGATED_BY_DESIGN` entry or bending an invariant in CLAUDE.md §5 is a stop-and-ask for Alex, recorded in `TODO_FOR_alex.md`, never a quiet exception.
14. **Green points.** A task that runs past its hour stops at a green point and the rest becomes a task with the parent's id and a derived suffix, as chunk 8's rule 11 does. The five tasks that have an interior green point name it here, so a sub-agent that runs out of room knows where to stop: `c14-shared-scenarios` stops with NFR-S1 to NFR-S6 green and hands NFR-S11 to NFR-S16 and the two journeys to `c14-shared-scenarios-b`; `c14-job-runs-b` stops with the helper, the wiring, the lag counter and `rebuild()` green and hands the bounded purge to `c14-job-runs-purge`; `c14-billing-usage-a` stops with the metrics that come from the bank's own zone (seats, agent runs, cost, tokens, Ask and searches) green and hands storage, exports and API calls to `c14-billing-usage-a-storage`; `c14-eu-data-location-a` stops with the model rules green and hands the embedder, reranker and runner values to `c14-eu-data-location-a-embedder`; each `c14-perf-*` pass stops with the routes it has measured recorded in `routes.py` and `baseline.json` and hands the rest to `c14-perf-<area>-rest`. A derived task inherits its parent's owned paths, serialization keys, dependants and security review, and the main agent adds its row to `PARALLEL_PLAN.md` 3.3.

## 3. Waves

Tasks in one wave have disjoint owned paths and can run side by side. A task also waits for its external depends-on, which its own section states.

| Wave | Tasks |
|---|---|
| 1 | `h-c-mixed-zones`, `c14-perf-harness-a`, `c14-owasp-scope`, `c14-cards-console-usage-a`, `c14-assurance-locations-a`, `c14-assurance-continuity-a` |
| 2 | `h-c-hatch-allowlist`, `c14-perf-harness-b`, `c14-cards-console-usage-b`, `c14-assurance-locations-b`, `c14-assurance-continuity-b`, `c14-assurance-exit-controls-a` |
| 3 | `h6-translation-confirm`, `c14-shared-scenarios`, `c14-assurance-exit-controls-b`, `c14-billing-contract-a` |
| 4 | `c14-job-runs-a`, `c14-billing-contract-b`, `c14-eu-data-location-a` |
| 5 | `c14-job-runs-b`, `c14-billing-plans`, `c14-eu-data-location-b` |
| 6 | `c14-billing-usage-a`, `c14-health-backend-a`, `c14-billing-limits-a`, `c14-eval-runs` |
| 7 | `c14-billing-usage-b`, `c14-health-backend-b`, `c14-billing-limits-b` |
| 8 | `c14-e2e-seed`, `c14-fe-console-plans-a`, `c14-fe-usage-a`, `c14-fe-health-a` |
| 9 | `c14-fe-console-plans-b`, `c14-fe-health-b`, `c14-runbooks`, `c14-fe-eval-run` |
| 10 | `c14-fe-usage-b`, `c14-owasp-auth`, `c14-owasp-access` |
| 11 | `c14-e2e-billing`, `c14-e2e-health`, `c14-owasp-library-ai`, `c14-owasp-files-data`, `c14-owasp-integrations-web`, `c14-perf-search-home` |
| 12 | `c14-owasp-fixes-auth`, `c14-owasp-fixes-access`, `c14-perf-register-cases` |
| 13 | `c14-owasp-fixes-library-ai`, `c14-owasp-fixes-files-data`, `c14-owasp-fixes-integrations-web`, `c14-perf-core`, `c14-perf-library-watch` |
| 14 | `c14-owasp-converge`, `c14-perf-rest` |
| 15 | `c14-perf-screens` |
| 16 | `c14-close` |

Waves 1 and 2 are dispatched as soon as a slot is free, ahead of the chunk's own place in the global schedule: H-C blocks four other chunks (ruling 2), and `c14-perf-harness-a` is an R1 package that `r1-perf` waits for.

The billing chain and the health chain are independent of each other from wave 4 on, so a delay in one does not hold the other. If `r1-readiness` is late, `c14-job-runs-*` and `c14-eu-data-location-*` wait (parallel-plan rule 11) and everything else proceeds; `c14-health-backend-b` then stops at a green point with the failed-jobs half unbuilt, ADM-S5 stays skipped, and `c14-close` cannot run.

### 3.1 Scenario ownership

Exactly one task un-skips each integration test and one un-fixmes each journey.

| Scenario | `@integration` | `@e2e` |
|---|---|---|
| NFR-S1 to NFR-S6 | `c14-shared-scenarios` | — |
| NFR-S7 | — | `c14-perf-screens` |
| NFR-S8, NFR-S9 | — | `c14-shared-scenarios` |
| NFR-S10 | green already (`c3-urgency-rule`) | — |
| NFR-S11 to NFR-S16 | `c14-shared-scenarios` | — |
| NFR-S17 | `c14-billing-plans` | `c14-e2e-billing` |
| NFR-S18 | `c14-billing-limits-a` (green up to storage and exports), closed by `c14-billing-limits-b` | — |
| NFR-S19 | `c14-billing-usage-b` | `c14-e2e-billing` |
| NFR-S20 (new) | `c14-eu-data-location-a` | — |
| NFR-S21 (new) | `c14-eu-data-location-b` | — |
| INV-S13 (new) | `h6-translation-confirm` | — |
| AUD-S7 (extended) | `h-c-mixed-zones` | — |
| AUD-S2 (extended) | `h-c-hatch-allowlist` | — |
| ADM-S4 (extended) | `c14-health-backend-a` | `c14-e2e-health` |
| ADM-S5 | `c14-health-backend-b` (green but for its retry line, which waits for `q-retry-write`) | `c14-e2e-health` |
| ADM-S6 (plans clause, PRD 0.4) | `c14-billing-plans` | `c14-e2e-billing` |
| ADM-S7 (PRD 0.4) | `c14-billing-usage-b` (green up to the failed-jobs line, which `c14-health-backend-b` closes; the retry line waits for `q-retry-write`) | — |

`AUD-S6` (retention) is chunk 12's and stays skipped with its chunk named. `INT-S4` (stream lag) is chunk 13's; `c14-health-backend-a` adds the per-bank lag panel that ADM-S5 reads and changes INT-S4's wording not at all. `I18N-S3` and `I18N-S4` are chunk 13's. `ADM-S6` is chunk 4's and chunk 8's for tenant creation and support access, but PRD 0.4 rewords it to "Tenants, plans and support access are managed from the console" and its Gherkin now assigns a plan, which no chunk 4 or chunk 8 task can serve: that one clause is `c14-billing-plans`' and `c14-e2e-billing`'s, and each extends the scenario where it lives rather than rewriting it. `ADM-S7` is new in PRD 0.4 and is chunk 14's in full. Both scenarios arrive with PRD 0.4's `governance/app.md`; until that is on `main` the task adds its assertion to the stub that is there and says so in one line beside the scenario. `c14-close` proves that every scenario in the repository is un-skipped or names its chunk.

## 4. Open questions

- **q-retry-write (for Alex; the route waits, the rest of the chunk does not).** ADR 0042 says platform staff "never write inside a tenant except through the last-admin recovery that already exists". ADR 0052, accepted the same day, adds `POST /console/jobs/{jobId}/retry`, which re-queues a bank's own failed job as a tenant task and writes an audit row inside the bank. Both are accepted and the first one's sentence has not been amended, so two ADRs disagree about how many ways the platform can cause a write in a tenant. That is an invariant question, and CLAUDE.md §12 says to ask rather than guess: the main agent put it to Alex on 2026-09-20 and it is in `docs/TODO_FOR_alex.md`.

  Option A (recommended): retry is a system-actor write, not platform staff acting as a person. It re-runs work the bank's own schedule already asked for, it can carry no operator input (the job is rebuilt from its stored kind, tenant and subject, and nothing else), the tenant audit row names the system actor, and a platform audit row names the operator. If Alex takes it, ADR 0042's sentence gains "and the console's job retry, which re-queues the tenant's own job as a system actor and writes an audit row in the bank" — written then, by the task that serves the route, and by nobody before the answer.

  Option B: retry only jobs with no tenant, and a bank's stuck job needs a support grant first. Item 12 explicitly rejected that shape ("Without the window, every stuck delivery would need a support grant"), and it would make ADM-S5's retry action useless for the case it exists for.

  Until the answer: `c14-job-runs-b` builds `rebuild()` and its tests inside the worker, where a scheduled run already writes the same rows, and amends no ADR; `c14-health-backend-b` serves the failed-jobs list and leaves `retryConsoleJob` answering 501 `not_built`, keeping its `contract_drift_pending.txt` line; `c14-fe-health-b` builds the table without a Retry action, because rule 3 forbids a screen calling a stub; `c14-e2e-health` walks ADM-S5 without the two retry steps; and ADM-S5's retry line and ADM-S7's stay noted in `governance/app.md` with `q-retry-write` named. `c14-close` names the one open route and the two noted lines instead of proving them gone. When the answer comes, a task of about twenty minutes serves the route, un-skips the two lines and writes the ADR line the answer decides.

- **Non-blocking (defaults are taken and the build does not wait).** Seven rows, six of them to confirm and item 3 recorded as a default the sources already settle; `c14-close` writes all seven into `docs/TODO_FOR_alex.md`:
  1. That the tenant's own usage and plan read is gated by `security.manage` rather than a new `billing.read` permission in PRD §6 (section 1.4).
  2. That a plan change is never retroactive: a bank moved to a smaller plan keeps what it has and only the next write is refused.
  3. Recorded, not asked: no invoice, payment provider, billing email or feature flag is built and a plan is assigned from the console alone, because billing/app.md §1 says in terms that there is no self-service checkout and that contracts are signed with banks, which is the source ruling 4 rests on. The row is written for the record.
  4. That `AGENT_RUNNER=none` is what production runs until ADR 0047's second tranche lands, so a deployed production environment runs no agent at all in the meantime (ruling 12).
  5. In what order Alex wants the assurance pack's unverified facts verified. Which facts they are is not open: `PARALLEL_PLAN.md` 7.3's `people` row already names the native-speaker review, the legal review of the incident clocks and the DORA Article 30 map, a restore test on Railway, a pen-test vendor and a certification path, all needed before the first bank tenant. The documents ship naming them unverified either way (section 1.4).
  6. That the H6 confirmation has no screen affordance in R3 (section 1.5).
  7. Who pays for a tenant's agents. `DECISIONS.md` marks it open under D-61 and proposes the tenant's budget cap; section 1.4 takes that proposal, so a bank's own agents and Ask calls are metered against its own cap and bleqq's platform agents are metered against nobody. If Alex answers otherwise, the change is `c14-billing-usage-a`'s metric sources and one test.
- **Rejected, from the parallelism critique:** merging the five OWASP reviews into one package because they share a method. Each depends on a different area's close, so one package would wait for the last of them, and `c14-owasp-converge` already gives the convergence a single owner.
- **Rejected, from the parallelism critique:** giving `c14-billing-limits` one task because the limits are one service. Its enforcement points sit in four different apps under four different keys; one task would hold all four at once for an hour on the chunk's longest chain.
- **Rejected, from the coverage critique:** building a usage trend so the tenant screen can show a month-on-month figure. It needs `tenant_metric_daily`, which ADR 0052 names as a table the window must never reach, and no requirement or scenario asks for a trend.
- **Rejected, from the coverage critique:** letting the console read `membership` to show a bank's seat count. ADR 0052 forbids it in terms; the seats metric is the only source.
- **Rejected, from the coverage critique:** adding a chunk-wide `c14-security-review` beside the five OWASP reviews. `c14-owasp-access` already covers `c14-billing-usage-b` and `c14-health-backend-a` by its own depends-on, and eleven chunk 14 tasks carry their own security review under rule 8. A twelfth sweep would review work that has been reviewed twice.

## 5. Tasks

### h-c-mixed-zones: a mixed table is read across zones and written only in its own

**Requirements:** NFR-01, AUD-01
**Scenarios:** AUD-S7 extended (stays green with a new write clause)
**Depends on:** `c3-append-only` (on `main`), the H-B commit `f336cce` (on `main`)
**Security review:** yes (row-level security on every mixed table)

`HARDENING.md` H15, high: `rls_operations(mixed=True)` creates one `FOR ALL` policy whose `WITH CHECK` equals the mixed read rule, so a bank session can insert, update or delete a platform row at the database level — the platform agent's API key among them. Two zones must hold in the database, not only in code.

Split every mixed table's policy the way `agent_run` has been split since the E5 fix:
- a `FOR SELECT` policy carrying today's mixed read rule (the tenant's rows, plus the rows with no tenant), unchanged in effect;
- a `FOR ALL` policy whose `USING` and `WITH CHECK` are both `tenant_id IS NOT DISTINCT FROM NULLIF(current_setting('app.tenant_id', true), '')::uuid`, so a bank session writes only its own rows and a session with no tenant writes only platform rows.

Apply it to every table the helper marks mixed today — `api_key`, `problem_report`, `ai_generation`, `outbox_event`, `audit_event` — with one new migration in each owning app, and keep any narrower policy a table already has, including the `identity_lookup` clause on the four tables that carry it. The `column="owner_tenant_id"` form of the helper takes the same split.

Extend the RLS guard so the policy shape is asserted for every mixed table from the enumeration, not from a hand-written list: a new mixed table cannot get the old shape and pass. Extend `AUD-S7`'s Gherkin and its test with the write rule the scenario exists to protect: under tenant A, inserting, updating or deleting a platform row is refused or touches no row, and moving a row between zones is refused; reads are unchanged.

Every test runs as the real `cw_app` role, not as the owner.

**Owned paths:**

- `backend/apps/shared/migration_helpers.py` (`rls_operations` only)
- one new migration in each app owning a mixed table (`identity`, `governance`, `shared`)
- `backend/apps/shared/tests_rls.py`
- `backend/apps/governance/tests_scenarios.py` (the AUD-S7 method only)
- `backend/apps/governance/app.md` (AUD-S7's Gherkin only)
- `docs/plans/briefs/HARDENING.md` (the H15 row only)

**Done when:**

- Every mixed table has exactly two policies with the shapes above, proved by reading `pg_policies` in the guard.
- As `cw_app` with tenant A active: an insert, update or delete of a platform row on each mixed table is refused or affects zero rows; an update that moves a row between zones is refused; every existing read returns exactly what it returned before.
- As `cw_app` with no tenant active: a write of a platform row succeeds and a write of a tenant's row is refused.
- The RLS guard fails when a mixed table is given the old single-policy shape (proved once by planting it).
- `migrate_from_zero` applies the whole graph, and the existing suites are green with no test weakened.
- `HARDENING.md`'s H15 row names this task and the commit.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/migration_helpers.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Two zones, in the database: the app role `cw_app` can neither bypass row-level security nor write outside its own zone.
- No policy is dropped without its replacement in the same migration.
- Nothing is proved as the table owner; every isolation test runs as `cw_app`.

### h-c-hatch-allowlist: the append-only hatch belongs to the migrator alone

**Requirements:** AUD-01, AC-AUD1
**Scenarios:** AUD-S2 extended (stays green with the new clauses)
**Depends on:** `h-c-mixed-zones` (both edit `migration_helpers.py`)
**Security review:** yes (the append-only guard)

From the H-B review, recorded at the end of `HARDENING.md`. Two findings, both low and both in the same file:

1. The hatch check names the role to refuse (`current_user <> 'cw_app'`), so any other role, a `SECURITY DEFINER` function owned by the migrator, or a cascading foreign key into an append-only table could still use it. Replace the refusal with an allowlist: the hatch opens only when `current_setting('cw.maintenance', true) = 'on'` **and** `session_user` is the migrator role, taken from the constant the grants already use so a renamed role cannot drift from a literal. Add a guard test that no `SECURITY DEFINER` function exists in the schema, and that no foreign key pointing into an append-only table carries an `ON DELETE` or `ON UPDATE` action.
2. The compliance lint accepts the quoted spelling `"CW"."MAINTENANCE"`. Widen its pattern to optional quotes, case-insensitively, with a planted test for each spelling.

Extend `AUD-S2`'s Gherkin and test with both: as the migrator inside a migration the hatch still opens; as `cw_app`, as any third role and through a `SECURITY DEFINER` function it does not.

**Owned paths:**

- `backend/apps/shared/migration_helpers.py` (the guard function only)
- one new migration in `backend/apps/shared/migrations/` replacing `cw_append_only_guard`
- `backend/scripts/compliance_check.py` (the maintenance pattern only)
- `backend/apps/shared/tests_compliance_lint.py`
- `backend/apps/shared/tests_append_only.py`
- `backend/apps/governance/tests_scenarios.py` (the AUD-S2 method only)
- `backend/apps/governance/app.md` (AUD-S2's Gherkin only)
- `docs/plans/briefs/HARDENING.md` (its own row only)

**Done when:**

- Update and delete on every append-only table are refused for `cw_app`, for a third role, and from inside a `SECURITY DEFINER` function, in either letter case and in the quoted spelling.
- The migrator, inside a migration's transaction, can still use the hatch, and one existing migration proves it.
- The guard test fails when a `SECURITY DEFINER` function or a cascading foreign key into an append-only table is planted.
- The lint fails on `"CW"."MAINTENANCE"` and on `cw . maintenance`, proved by planted tests.
- `migrate_from_zero` applies the whole graph.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.shared apps.governance apps.library --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/migration_helpers.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Nothing overwritten: the ledgers stay append-only for every role but the schema owner, inside a migration.
- A lint is not the guard; the database refuses the write.
- No test is weakened to make the new guard pass.

### h6-translation-confirm: confirming a machine translation goes through the proposal door

**Requirements:** INV-05, PRO-01, AC-PRO1
**Scenarios:** INV-S13 (new, un-skipped); INV-S6 and PRO-S2 stay green
**Depends on:** `c3-append-only`, `c4-approve-apply` (it adds a kind to `apply.py`)
**Security review:** yes (the library fence and the proposal door)

`HARDENING.md` H6, low, design: under the append-only trigger a machine translation cannot be confirmed in place, so INV-05's "machine translations labelled" has no way to stop being labelled. Section 8 of the parallel plan leaves it with no owner ("built with the screens that confirm"), and no chunk 3 or chunk 4 task builds a confirm action.

Build the default of section 1.4: a `confirm_translation` proposal kind. Its payload names the translation row and the text as confirmed, `apply.py` writes a **new** translation row with `machine=false` carrying the confirmer and the time, and the previous row stays as it was. No table changes its append-only shape, no allowlist grows, and the library keeps one door.

Add `INV-S13` to `library/app.md`:

```gherkin
Given an obligation whose summary exists as an sv original and an en machine translation
When a compliance officer proposes the en text as confirmed and a library editor approves it
Then a new en translation row is in force, labelled as confirmed rather than machine, with the approver and the time
And the machine row is unchanged and still readable as history
When anyone tries to change a translation row in place
Then the append-only trigger refuses it
```

Record the new kind in `INPUT_DELTAS.md` §1, and the missing screen affordance in `TODO_FOR_alex.md` with its reason (section 1.5).

**Owned paths:**

- `backend/apps/proposals/apply.py` (the new kind only)
- `backend/apps/proposals/models.py` (the `ProposalKind` member only)
- `backend/apps/proposals/tests_apply.py`
- `backend/apps/library/tests_scenarios.py` (the INV-S13 method only)
- `backend/apps/library/app.md` (INV-S13 and INV-05's note)
- `docs/inputs/INPUT_DELTAS.md`, `docs/TODO_FOR_alex.md`, `docs/plans/briefs/HARDENING.md` (own rows only)

**Done when:**

- INV-S13 is green, and INV-S6 and PRO-S2 are still green.
- Applying the kind writes a new row and touches none; the trigger is proved to refuse the in-place update.
- Four eyes holds: the proposer cannot approve, 409 `four_eyes_violation`.
- The library fence is unchanged: `tests_library_fence.py` has the same allowlist it had before.
- `contract_drift.py` reports no new operation, because none is added.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.proposals apps.library apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/proposals/apply.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Proposals are the only door into the library; the re-verification stamp stays the single exception.
- Nothing overwritten: a confirmation is a new row, never an edit.
- Four eyes, enforced by the check constraint that already exists.

### c14-perf-harness-a: one way to measure an endpoint against its budget

**Requirements:** NFR-02
**Scenarios:** none (NFR-S6 is `c14-shared-scenarios`'; this task gives it its measurement)
**Depends on:** nothing

R1, and `r1-perf` waits for it (parallel-plan ruling 35). Build the one harness every performance pass uses, so a pass measures and never re-invents measuring.

- `backend/perf/harness.py`: given a named route, a principal factory and a request body, it drives the route against a seeded database inside the task's slot, discards a warm-up run, takes `PERF_SAMPLES` (a setting, default 20) samples, and returns the median and 95th percentile of the `Server-Timing: app` value the middleware already writes, plus the query count from `CaptureQueriesContext`.
- `backend/perf/routes.py`: the measured route list, one row per operation with its principal, its fixture and its budget (`API_BUDGET_MS` unless the route names its own, as hybrid search and Ask do). It is an append ledger: each performance pass adds its own rows.
- `backend/scripts/perf_report.py`: runs the list, writes `backend/perf/baseline.json` with `--record`, and without it compares against the recorded baseline and exits non-zero on any route over its budget or more than `PERF_REGRESSION_PCT` (a setting, default 20) slower than its baseline. It prints the route, the measured value, the budget and the query count, so the output names the fix.
- The report never runs against a deployed environment, and refuses to if `IS_DEPLOYED_ENVIRONMENT`.

No route list rows are recorded here beyond two that exist on `main` today, which prove the harness end to end: one fast read and one deliberately slow test route that the harness must fail. The passes fill the list.

**Owned paths:**

- `backend/perf/__init__.py`, `backend/perf/harness.py`, `backend/perf/routes.py`, `backend/perf/tests_harness.py`
- `backend/scripts/perf_report.py`
- `backend/config/settings.py` (one labelled block: `PERF_SAMPLES`, `PERF_REGRESSION_PCT`), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`

**Done when:**

- `python backend/scripts/perf_report.py --record` writes a baseline for the two seeded rows and exits 0.
- Without `--record` it exits 0 on an unchanged route and non-zero on a planted route that exceeds its budget, and on one that is 25 % slower than its baseline.
- The harness reports a query count and the test proves it catches an N+1 planted in a fixture view.
- It refuses to run on a deployed environment, with a test.
- Nothing in the harness writes to the database outside a transaction it rolls back.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test perf apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='perf/*' (>= 90)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Measurement is against the real database under the task's slot; nothing is mocked to make a number look good.
- Every threshold is a setting with an env override.
- The harness reports; it never changes a budget.

### c14-perf-harness-b: measuring a screen's time to real data

**Requirements:** NFR-02
**Scenarios:** none (NFR-S7 is `c14-perf-screens`')
**Depends on:** `c14-perf-harness-a`

The screen half, for Playwright. `frontend/tests/e2e/support/screen-timing.ts` exports `measureScreen(page, destination)`: it navigates, waits for the destination's own "real data" marker (a `data-loaded` attribute the shell already sets when a query resolves, never a timeout and never a skeleton), and returns the milliseconds from navigation to that marker, taken as the median of `SCREEN_SAMPLES` (default 5) loads. It fails loudly when the marker never appears, so a screen that shows a skeleton for ever is a failure and not a fast number.

It runs only against `next start`; a helper asserts the build mode and fails on `next dev`, which CLAUDE.md §6 requires and which no existing helper checks.

`frontend/tests/e2e/support/screen-budgets.ts` holds the per-destination budget (500 ms by default) as an append ledger, and a writer appends each measurement to `docs/plans/UI_Implementation_Plan.md` beside its screen, which NFR-S7's Gherkin asks for.

**Owned paths:**

- `frontend/tests/e2e/support/screen-timing.ts`, `frontend/tests/e2e/support/screen-budgets.ts`
- `frontend/tests/e2e/support/screen-timing.test.ts` (a unit test of the median and the marker failure)

**Done when:**

- `measureScreen` returns a number for a seeded destination and throws a named error when the marker never appears, both proved.
- It refuses to run against `next dev`, proved.
- A measurement lands in the UI plan row for the destination measured, in the shape the plan already uses.
- `npm run lint`, `typecheck` and `test:coverage` are green, and the ESLint rule that every E2E spec imports `test` from `support/api-guard` still passes.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
- `npm run test:e2e -- --grep @smoke`

**Invariants:**

- Never `next dev`; measurement is against a production build.
- A skeleton is not real data.
- No API is mocked to make a screen fast.

### c14-owasp-scope: what the review covers, how it is run, and how a finding is written

**Requirements:** NFR-04
**Scenarios:** none
**Depends on:** nothing

Write `docs/security/OWASP_REVIEW_SCOPE.md`, the frame the five area reviews and their fix packages share, so five sub-agents do not each invent a method.

- **The frame,** fetched and not recalled: the OWASP Top 10 (2021) categories and OWASP ASVS 5.0 level 2, each with the URL it was read from and today's date, logged in `docs/plans/Verification_Log.md`.
- **The five areas and what each owns:** auth (enrolment, passkeys, sessions, step-up, SSO, SCIM, API keys, IP allow-list, credential and session policy); access (permissions, row-level security, the two zones, four eyes, support access, the platform counters window, tenant exit); library and AI (the proposal door, the fence, prompts, fetched content, the AI log, the search index, private records); files and data (evidence, the scanner, storage, imports, exports, retention, the case file); integrations and web (webhooks, the SIEM stream, tickets, CORS, headers, the frontend, the token-carrying calendar feed).
- **The method per area:** the routes and models in scope, the guard suites to run, the threat questions to answer with evidence, and the sources to read (`app.md`, the ADRs, `docs/security/`, `HARDENING.md`).
- **The severity scale,** the same one `docs/security/CHUNK1_AUTH_REVIEW_2026-09-19.md` and the chunk reviews use, with the rule that critical and high block `c14-close`, medium is fixed by the area's fix package, and anything lower becomes a `HARDENING.md` row with a package named.
- **The finding format:** severity, area, file and line, the scenario that reproduces it, and the fix asked for, so a fix package can start from the file list.
- **What a review may never do:** change code, lower a gate, add an `UNGATED_BY_DESIGN` entry, or close its own finding.

**Owned paths:**

- `docs/security/OWASP_REVIEW_SCOPE.md` (new)
- `docs/plans/Verification_Log.md` (its own rows only)

**Done when:**

- Every route and model in the repository falls in exactly one of the five areas, proved by listing the apps against the areas with no app left out and none in two.
- Each area names its guard suites, its sources and at least six threat questions.
- Both external frames carry a URL and a fetch date in the Verification log.
- The document says in terms that a review reports and never fixes.

**Gates:**

- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Outside facts are fetched, never recalled, and logged with their URL.
- The document changes no code and no gate.

### c14-cards-console-usage-a: design cards for the console's Plans and Usage

**Requirements:** NFR-05, ADM-02, NFR-03
**Scenarios:** none
**Depends on:** nothing

`design/screens/` has no card for any chunk 14 screen, and CLAUDE.md §2 makes the prototype the decider of how things look, read and flow. Write two, in the shape of `console-queue.html` and `admin-vocabularies.html`, on the console shell:

- `design/screens/console-plans.html`: the plan list (name, code, the five limits, the price with its currency, active), the create and edit form with the price as a whole minor-unit amount and the currency as a picker, the "in use by N banks" count, the refusal to deactivate a plan in use, and the empty, loading, error and denied states from `design/screens/states.html`.
- `design/screens/console-usage.html`: usage per bank for a month — the month picker, one row per bank with runs, spend against the cap, storage against the limit, seats against the limit, and an over-limit row in the `warning` tone — plus the note that the console reads numbers only and that every read is logged.

Both carry the six-tone pill rules of `design/system/pills-and-labels.md`: the tone comes from the slot or the kind, never from a person, and an over-limit figure is a pill, not coloured text. Every string is written in English in the card and carries its catalog key, so the screen tasks copy rather than invent.

**Owned paths:**

- `design/screens/console-plans.html`, `design/screens/console-usage.html` (new)
- `design/README.md` (the two index rows only)

**Done when:**

- Both cards render standalone in light and dark from the committed tokens, with no new colour value.
- Every state of `states.html` is drawn for both.
- Every pill on both cards names the kind or slot it comes from.
- Money is drawn as a whole amount with its currency, never as a float, and the card says the API sends minor units.
- `design/README.md` lists both.

**Gates:**

- None automated; the main agent reviews the cards against `design/system/pills-and-labels.md` and `design/screens/states.html` before merge.

**Invariants:**

- Six pill tones, chosen by slot or kind.
- No requirement ID and no restated invariant on screen.
- The prototype decides how things look, never what the rules are.

### c14-cards-console-usage-b: design cards for System health and the bank's own Usage

**Requirements:** ADM-02, NFR-05, NFR-03
**Scenarios:** none
**Depends on:** `c14-cards-console-usage-a` (it owns the `design/README.md` index rows first)

- `design/screens/console-health.html`: components with their state (database, cache, worker, pgvector), source coverage, recent runs, outbox lag per bank, and the failed-jobs table with a Retry action per row, its confirmation and its result. A failing component is a `negative` pill and a lagging bank a `warning` pill; the card shows the 503 state as the screen's own state, not as an error page.
- `design/screens/admin-usage.html`: the bank's own usage under Admin — runs, "Spend this month" against the cap, storage against the limit, seats against the limit, the plan's name, and the note that the plan is set by agreement and changed by bleqq. No price.

**Owned paths:**

- `design/screens/console-health.html`, `design/screens/admin-usage.html` (new)
- `design/README.md` (its own two index rows only)

**Done when:**

- Both cards render in light and dark with no new colour value, and draw every state.
- The health card draws the 503 case as a screen state with the component named, matching ADM-S5's Gherkin.
- The bank's card shows no price and no other bank.
- Retry is drawn with its confirmation and both outcomes.

**Gates:**

- None automated; reviewed by the main agent before merge, as `-a`.

**Invariants:**

- Six pill tones, chosen by slot or kind.
- A bank's screen never shows another bank, and never shows money it does not owe.

### c14-assurance-locations-a: the subprocessor register

**Requirements:** NFR-04
**Scenarios:** none
**Depends on:** nothing

Playbook 18 asks for a subprocessor register with processing locations, as part of what a bank's vendor review reads. Create `docs/assurance/` with its `README.md` (what the pack is, which document answers which DORA contract term, and the rule that an unverified fact is written as unverified), then `docs/assurance/subprocessors.md`:

one row per processor with the service it provides, the company, the processing location, the data categories it sees, the legal basis for the transfer if any, and how it is controlled. From ADR 0047 and `RAILWAY_VARIABLES.md`: the hosting platform and its region, PostgreSQL, Redis, the object store (AWS S3 in an EU region until Tigris's EU restriction is verified), the transactional mail sender, Sentry (with the note that account metadata stays in the United States), Amazon Bedrock in an EU region for the model, the embedder and reranker when they exist, and the destinations a bank configures itself — webhooks, SIEM, ticket tools, its identity provider — listed as the bank's own processors, not ours.

State, with the code that proves it, which of these the production boot refuses to change (the allowlists of ADR 0047) and which it does not. Mark the mail sender, the storage endpoint and Tigris's region as **not verified**, with the check that would verify each, and add a `TODO_FOR_alex.md` row for each.

**Owned paths:**

- `docs/assurance/README.md`, `docs/assurance/subprocessors.md` (new)
- `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md` (own rows only)

**Done when:**

- Every processor the product can reach in production has a row, and each row names its location or says the location is unverified.
- Each claim about a vendor's region carries the URL it was read from and today's date in the Verification log; nothing is recalled.
- The register says which entries the boot guard enforces and which the operator checklist covers.
- `README.md` maps each pack document to the DORA contract term it answers.

**Gates:**

- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Outside facts are fetched, never recalled.
- An unverified fact is written as unverified, with the check that would settle it.

### c14-assurance-locations-b: a data-flow diagram per zone

**Requirements:** NFR-04, NFR-01
**Scenarios:** none
**Depends on:** `c14-assurance-locations-a` (which creates `docs/assurance/README.md`)

`docs/assurance/data-flows.md`: one flow per zone, as text plus a Mermaid diagram, showing what crosses which boundary.

- **The library zone:** public sources to the watch agents, to proposals, to the shared library, to every bank. No tenant content enters it, and the proposal door is the only write.
- **The tenant zone:** the bank's own writes, its evidence, its exports, its SIEM stream, its webhooks, its tickets, its identity provider. Row-level security, forced, with no bypass.
- **What crosses, and on whose instruction:** the question typed into Ask and the tenant's own agent inputs, which reach a model only while the bank's AI switch is on (D-07, ruling 13 of the parallel plan); jurisdiction keys to a tenant-scoped run, never tenant text (D-32); and the platform counters window (ADR 0052), stated plainly: bleqq sees each bank's usage figures, failed job kinds and stream lag, as numbers, kinds and times, never content.
- **What never crosses:** tenant content to logs, Sentry, analytics or an unapproved model endpoint; a bank's problem report to bleqq (D-50); a private record to the index, the embedder, the reranker or a model (D-57).

Each arrow names the code that enforces it, so a reviewer can check the diagram against the repository.

**Owned paths:**

- `docs/assurance/data-flows.md` (new)
- `docs/plans/Verification_Log.md` (its own rows only)

**Done when:**

- Every boundary crossing in the product appears in exactly one flow, with the module that enforces it named.
- The platform counters window is stated as a crossing bleqq makes, not omitted.
- The diagrams render in the repository's Markdown.
- Nothing in the document contradicts an accepted ADR; each claim cites one.

**Gates:**

- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- The document describes what the code does, not what it should do; a gap is written as a gap.
- Tenant content never reaches logs, Sentry, analytics or an unapproved model endpoint.

### c14-assurance-continuity-a: recovery objectives and the restore test log

**Requirements:** NFR-04
**Scenarios:** none
**Depends on:** nothing

`docs/assurance/continuity.md` and `docs/assurance/restore-tests.md`.

The first states the recovery point and recovery time objectives the product commits to, what they rest on (the hosting platform's backup cadence and retention, the object store's durability, what a redeploy restores and what it does not), and what a bank should assume when the objectives are missed. Since nobody has measured a restore, the document states the proposed objectives as **proposed, not verified**, names the test that would confirm each, and does not present either as tested.

The second is the log a restore test writes: date, environment, what was restored, from which backup, how long it took, what was lost, who ran it, and the outcome. It ships with the procedure and an empty table, so the first real test has a place to land.

Add a `TODO_FOR_alex.md` row for the first restore test on Railway, which `PARALLEL_PLAN.md` 7.3 already lists under "people".

**Owned paths:**

- `docs/assurance/continuity.md`, `docs/assurance/restore-tests.md` (new)
- `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md` (own rows only)

**Done when:**

- Every objective is marked proposed or verified, and none is marked verified.
- The backup cadence and retention each carry the URL they were read from and today's date.
- The restore procedure is runnable as written by someone who has not seen the repository before.
- The log's columns are the ones a bank's auditor asks for.

**Gates:**

- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- No assurance document states an untested figure as tested.
- Outside facts are fetched, never recalled.

### c14-assurance-continuity-b: the incident notification runbook

**Requirements:** NFR-04
**Scenarios:** none
**Depends on:** `c14-assurance-continuity-a`

`docs/assurance/incident-notification.md`: what bleqq does when an incident touches a bank's data, in the order it is done — detect, classify, contain, notify, report, close — with who does each step, the clock each notification runs on, what the bank is told and in what form, and what evidence is kept.

Take the incident classes from what the product can actually suffer: a processor outage, a data exposure across zones, a stolen passkey or session, a poisoned source or prompt injection reaching the library, a failed delivery to a bank's SIEM, a loss of backup integrity. For each, name the signal the console already shows (system health, the security log, the audit log, the failed-jobs table) so the runbook starts from something real.

The legal clocks — what DORA's major-incident reporting requires of a bank and therefore of us as its ICT third party, and what the GDPR's 72 hours means for a processor — are written as **proposed, needing a lawyer's reading**, with a `TODO_FOR_alex.md` row, because `PARALLEL_PLAN.md` 7.3 already lists that review as outstanding and a wrong clock in an assurance document is worse than a named gap.

**Owned paths:**

- `docs/assurance/incident-notification.md` (new)
- `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md` (own rows only)

**Done when:**

- Each incident class names its signal in the product and its first containing action.
- Every clock is marked as needing legal confirmation, with the source read and its URL.
- The runbook says what the bank receives, in what channel, and who signs it.
- Nothing in it depends on a person reading a log the product does not write.

**Gates:**

- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- A legal claim nobody has checked is written as unchecked.
- The runbook starts from signals the product produces.

### c14-assurance-exit-controls-a: the exit plan

**Requirements:** NFR-04, REP-04, AUD-04
**Scenarios:** none
**Depends on:** `c12-exit-export`, `c12-exit-deletion`, `c14-assurance-locations-a`

`docs/assurance/exit-plan.md`: exit as a feature, written from the code that exists after chunk 12.

What a bank gets and when: the full tenant export in open formats (register, cases, evidence, configuration, audit log), how it is requested, how long it takes, how it is verified (the export hash), and how long it stays available. What happens next: the tenant becomes `closing`, which mutating routes refuse with 409 `tenant_closing` while sign-in, step-up, revocation, exports and downloads keep working; the `TENANT_EXIT_DELAY_DAYS` window; then `execute_tenant_exit` run by the platform operator as the schema owner, deleting every tenant row including the audit trail, the outbox, the security log and footprint history, leaving a tombstone report with counts, the export hash and the people involved (D-56, ADR 0049).

State the two people it takes and the passkey each of them uses, that no single stolen passkey can erase a bank, and what is **not** deleted: the shared library, which holds no bank's data.

Name the guard that keeps the export and the deletion honest as the product grows: parallel-plan ruling 36's test, which fails on any tenant table the export or the deletion does not cover, and its exception list with a reason per entry.

**Owned paths:**

- `docs/assurance/exit-plan.md` (new)
- `docs/plans/Verification_Log.md` (its own rows only)

**Done when:**

- Every step matches the code on `main` after chunk 12, cited by module.
- The document names the four-eyes requirement, the delay, the operator step and the tombstone.
- It lists what is kept and why, including the exception list's entries as they stand at the close.
- It says plainly that ledger rows are deleted at exit, which is the CLAUDE.md §5 exception Alex approved (item 9).

**Gates:**

- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- The document describes the code; a step that is not built is written as not built.
- Tenant exit deletes everything of the bank's and nothing of the library's.

### c14-assurance-exit-controls-b: audit streaming, IP allow-listing and the support access log

**Requirements:** NFR-04, INT-03, ID-13
**Scenarios:** none
**Depends on:** `c13-siem-stream`, `c13-ip-allowlist`, `c13-sso-oidc`, `c8-support-access-mechanism`, `c14-assurance-exit-controls-a`

`docs/assurance/access-controls.md`, the third thing playbook 18 asks for: audit log streaming to the customer's SIEM, IP allow-listing, and the support access log.

- **The SIEM stream:** which events are streamed, in what shape, over what transport, what a bank does when a delivery fails, what the retry does, and how the bank sees the lag (the console shows it per bank; the bank sees its own).
- **The IP allow-list:** what it covers, what it does not (a bank's own webhook destinations are outbound), how a locked-out admin recovers, and how the change is audited.
- **Support access:** the whole D-49 flow — a platform admin requests with a purpose and a limit, a tenant admin approves with a passkey, the window starts at approval, the support principal reads and never writes, every request writes a `support_access.read` row in the bank, and the bank can revoke at any moment. Include the console's job retry as the one other platform-caused write inside a bank, described as ADR 0052 designs it and as the open question q-retry-write records it.
- **Who at bleqq can see what, in one table**, so a vendor review gets its answer on one page: the shared library (everyone), a bank's content (nobody, without an approved grant), a bank's figures (the counters window, logged), a bank's problem reports (nobody, D-50).

**Owned paths:**

- `docs/assurance/access-controls.md` (new)
- `docs/plans/Verification_Log.md` (its own rows only)

**Done when:**

- Each control names the module that enforces it and the test that proves it.
- The "who can see what" table has a row for every zone and names the audit row each read writes.
- Support access is described exactly as ADR 0042 and the code on `main` have it, with no bypass and no platform write beyond the two named exceptions.
- Nothing claims a control the code does not have.

**Gates:**

- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Platform staff read a bank only through an approved, time-limited, logged grant.
- The document is checkable: every claim cites code.

### c14-shared-scenarios: the shared NFR scenarios point at the guards that prove them

**Requirements:** NFR-01, NFR-02, NFR-03, NFR-04
**Scenarios:** NFR-S1 to NFR-S6 and NFR-S11 to NFR-S16 (`@integration`, un-skipped); NFR-S8 and NFR-S9 (`@e2e`, un-fixmed)
**Depends on:** `c3-no-tone`

Twelve integration stubs and two journey stubs in `shared/app.md` are still skipped although the guards that prove them have been on `main` since chunk 0: `tests_tenant_isolation`, `db_role_guard`, `tests_rls`, `tests_celery_registration`, the `Server-Timing` middleware test, `tests_production_guard`, `tests_route_permissions`, `tests_health`, the compliance lint and `sentry_scrub`, `tests_errors`, `pills.gallery.spec.ts` and `styles/contrast.test.ts`.

Un-skip each stub by making it the scenario's own assertion, not a comment pointing elsewhere: each test calls the guard's own entry points and asserts the scenario's Gherkin end to end, so a future change that weakens a guard fails the scenario as well as the guard. Where a Gherkin line has no assertion today, write it (for example NFR-S6's "list endpoints refuse a limit above 100 and default to 20", which `PageQuery` proves per route rather than in one place, and NFR-S16's "a filtered list that matches nothing answers 200 with an empty collection").

Where a scenario cannot be fully green because a later chunk owns part of it, say so in one line in `app.md` beside the scenario and assert the part that exists — never weaken the Gherkin to fit. Nothing here changes a guard.

NFR-S8 and NFR-S9 are un-fixmed in `shared.journey.spec.ts` by calling the existing gallery spec's and contrast test's checks from the journey, in light and dark (ruling 11).

**Owned paths:**

- `backend/apps/shared/tests_scenarios.py`
- `backend/apps/shared/app.md` (the status notes beside the scenarios only)
- `frontend/tests/e2e/shared.journey.spec.ts` (the NFR-S8 and NFR-S9 blocks only)

**Done when:**

- The twelve integration scenarios are un-skipped and green, each asserting its own Gherkin.
- NFR-S8 and NFR-S9 are un-fixmed and green in both themes against a production build.
- No guard, allowlist or threshold changed; the diff adds tests and app.md notes only.
- A planted weakening of each guard fails its scenario, proved once per scenario in the task's report (not committed).
- `requirements_coverage.py` is green and no shared scenario is left skipped without a chunk named.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `cd frontend && npm run test:e2e -- --grep "NFR-S8|NFR-S9"`

**Invariants:**

- A scenario asserts; it never assumes a guard is green because it exists.
- Never lower a gate, skip or quarantine a test, or mock an API in E2E.

### c14-eu-data-location-a: production refuses a model, embedder, reranker or runner outside the EU

**Requirements:** NFR-04
**Scenarios:** NFR-S20 (new, un-skipped); NFR-S11 and NFR-S12 stay green
**Depends on:** `r1-readiness`, `c14-shared-scenarios`
**Security review:** yes (the production boot guard)

ADR 0047 and D-54, tranche 1, first half. In the production-safety block of `backend/config/settings.py`, on every deployed environment except `ENVIRONMENT=test`:

- `LLM_PROVIDER=anthropic` is refused, naming the reason (Anthropic's own API offers `us` and `global` inference only).
- `bedrock` is allowed only in `eu-central-1`, `eu-west-1`, `eu-west-3`, `eu-south-1`, `eu-south-2` or `eu-north-1`. `eu-west-2` (United Kingdom) and `eu-central-2` (Switzerland) are refused by name, so nobody reads the rule as an `eu-` prefix match.
- The model id must be an in-region id, or a `(source region, eu. profile)` pair on a list that starts **empty**. `global.`, `us.` and `apac.` prefixes and application-profile ARNs are refused.
- `EMBEDDER_PROVIDER` and `RERANKER_PROVIDER` must be `none`, or `bedrock` under the same rule.
- `AGENT_RUNNER=managed_agents` is refused (it follows the workspace geography), and a new value `none` is added to the adapter and to the settings comment, so production boots with no runner until ADR 0047's second tranche lands.

Every list is a module-level constant in the production-safety block, never an environment variable, each entry with a `Verification_Log.md` row. On `ENVIRONMENT=test`, the existing mock banner also shows whenever a non-EU processor is configured, so the exemption is never silent; the banner's field is added to the adapters status the API already reports.

Add `NFR-S20` to `shared/app.md`:

```gherkin
Given a deployed environment that is not named test
When Django boots with LLM_PROVIDER=anthropic, with bedrock in eu-west-2 or eu-central-2, with a global., us. or apac. model id, with an application-profile ARN, with a non-EU embedder or reranker, or with AGENT_RUNNER=managed_agents
Then each boot fails with the offending setting and its value named
Given bedrock in an EU region with an in-region model id, an EU embedder or none, and AGENT_RUNNER=none
Then the boot succeeds
Given the one environment named test
Then a non-EU processor boots and the API reports it so the UI shows its banner
```

One subprocess boot test per rule, in the shape `tests_production_guard.py` already uses. Write the consequence of ruling 12 into `TODO_FOR_alex.md`: until the in-worker Bedrock EU runner exists, production runs no agent.

**Owned paths:**

- `backend/config/settings.py` (the production-safety block and one labelled settings block)
- `backend/apps/shared/tests_production_guard.py`
- `backend/apps/shared/adapters/agent_runner.py` (the `none` value only)
- `backend/apps/shared/tests_scenarios.py` (the NFR-S20 method only), `backend/apps/shared/app.md` (NFR-S20 only)
- `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (own blocks only)
- `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md` (own rows only)

**Done when:**

- NFR-S20 is green, with one subprocess boot per rule, each asserting the setting name in the message.
- Every allowlist is a constant; a test asserts that no allowlist is read from the environment.
- `AGENT_RUNNER=none` is a real adapter value that refuses to run a run rather than silently succeeding, with a test.
- `ENVIRONMENT=test` still boots with mocks and now reports a non-EU processor to the UI, with a test.
- NFR-S11 and NFR-S12 are still green and their Gherkin is unchanged.
- Each region, endpoint and profile claim has a Verification log row with its URL and today's date.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='config/settings.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- A transfer must never follow from a changed environment variable.
- A guard that cannot fail is decoration: every rule has a boot that fails on it.
- Outside facts are fetched, never recalled.

### c14-eu-data-location-b: production refuses telemetry, mail, storage or a region outside the EU

**Requirements:** NFR-04
**Scenarios:** NFR-S21 (new, un-skipped); NFR-S12 and NFR-S15 stay green
**Depends on:** `c14-eu-data-location-a` (both hold `bootguard`)
**Security review:** yes (the production boot guard)

ADR 0047, tranche 1, second half, in the same block:

- **Sentry:** no DSN, or a DSN whose host matches `o<number>.ingest.de.sentry.io`. Any other host is refused. The register records that Sentry keeps account metadata in the United States, which the boot does not refuse (`c14-assurance-locations-a` carries it).
- **Mail:** `MAIL_SMTP_HOST` must be on a reviewed host list that starts **empty**, so production cannot send mail until a sender is reviewed and added in code. Correct the storage and mail variable names in `docs/runbooks/RAILWAY_VARIABLES.md`, which ADR 0047 records as wrong today.
- **Storage:** the endpoint must be `s3.<EU region>.amazonaws.com` for one of the six regions, or a Railway (Tigris) endpoint only once its EU restriction is verified; until then production uses AWS S3 in an EU region and the Tigris entry is absent from the list.
- **Region:** when `RAILWAY_ENVIRONMENT_NAME` is set, `RAILWAY_REPLICA_REGION` must be present and equal `europe-west4-drams3a`. A missing value is refused, not accepted.

Not refused at boot, and named in the code comment so the next reader does not add them: destinations a bank configures itself (webhooks, SIEM, ticket tools, its identity provider), the database, Redis and web regions, and Sentry's account metadata.

`NFR-S21` in `shared/app.md`:

```gherkin
Given a deployed environment that is not named test
When Django boots with a Sentry DSN on any host but ingest.de.sentry.io, with a mail host that is not on the reviewed list, with a storage endpoint outside the EU regions, or with RAILWAY_ENVIRONMENT_NAME set and RAILWAY_REPLICA_REGION missing or not europe-west4-drams3a
Then each boot fails with the offending setting and its value named
Given no Sentry DSN, a reviewed mail host, an EU S3 endpoint and the expected replica region
Then the boot succeeds
And a bank's own webhook, SIEM, ticket and identity-provider destinations are not checked at boot
```

**Owned paths:**

- `backend/config/settings.py` (the production-safety block only)
- `backend/apps/shared/tests_production_guard.py`
- `backend/apps/shared/tests_scenarios.py` (the NFR-S21 method only), `backend/apps/shared/app.md` (NFR-S21 only)
- `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md` (its own block, and the mail and storage variable-name corrections)
- `docs/plans/Verification_Log.md` (its own rows only)

**Done when:**

- NFR-S21 is green, one subprocess boot per rule.
- The mail host list is empty on `main` and a test asserts that an empty list refuses every host, so adding one is a reviewed change.
- A missing `RAILWAY_REPLICA_REGION` with `RAILWAY_ENVIRONMENT_NAME` set is refused, proved.
- The variable names in `RAILWAY_VARIABLES.md` match the settings, proved by a test that reads both.
- NFR-S15 is still green: no new setting value reaches a log or Sentry.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='config/settings.py'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Allowlists are constants in code; an empty list means "nothing is approved yet", not "anything goes".
- A missing value is refused, never assumed safe.
- Tenant content never reaches logs, Sentry or analytics.

### c14-job-runs-a: a job row of numbers and kinds, and the window that reads it

**Requirements:** ADM-02, NFR-01
**Scenarios:** none (ADM-S5 is `c14-health-backend-b`'s)
**Depends on:** `r1-readiness`, `h-c-mixed-zones`
**Security review:** yes (a new window into every bank's rows)

ADR 0052 and D-59, tranche 1. Build `job_run` in `apps/shared` (key `mig:shared`) as a mixed table that can hold no tenant content by shape:

| Column | Kind |
|---|---|
| `id` | uuid |
| `tenant_id` | uuid, nullable (a platform job has none) |
| `kind` | a job kind from `kinds.py` |
| `status` | a job status kind (`running`, `succeeded`, `failed`) |
| `attempts` | integer |
| `started_at`, `finished_at` | timestamptz |
| `error_code` | a kind, nullable — never an exception message |
| `items`, `failures`, `skipped` | integers |
| `subject_kind`, `subject_id` | a kind and a uuid, nullable, so a retry can rebuild the job |

`schema.sql`'s `stats jsonb` and `error text` are replaced (ruling 6); INPUT_DELTAS §7 carries the row. `Meta.ordering` on `-started_at`, because the health read takes `.first()` of a filtered set — and because the per-bank lag figure is the newest publisher row per bank. One more integer stat, `lag_seconds`, arrives with the jobs that write it in `c14-job-runs-b`.

- **Row-level security** in H-C's split shape: `FOR SELECT` mixed (the tenant's rows and the rows with none), `FOR ALL` restricted to the session's own zone.
- **A structural test** over `job_run` and, when it exists, `usage_record`: no `TextField`, no `CharField` without `choices` or a kind constraint, no untyped `JSONField`. A kind column passes; a free-text column fails. It reads the model's fields, so a new column cannot slip past.
- **The window.** `tenancy.platform_counters(principal)` (key `auth`) is a context manager that sets `app.platform_counters` only for a platform principal holding `tenants.manage` or `system.health`, raises when a tenant is active, and clears the setting afterwards even on an exception. One `FOR SELECT` policy on `job_run` keyed on it. An AST guard, in the shape of the `identity_lookup()` guard already on `main`, allows callers in `billing/usage_logic.py` and `governance/health_logic.py` only. `tests_rls.py` gains one map of every window with the tables it opens, and the guard fails on a window with no entry.

**Owned paths:**

- `backend/apps/shared/models.py` (`JobRun` only) and a new migration
- `backend/apps/shared/kinds.py` (the job, status, error and subject kinds only)
- `backend/apps/shared/tenancy.py` (`platform_counters` only)
- `backend/apps/shared/tests_rls.py` (the window map and the `job_run` entries), `backend/apps/shared/tests_tenancy.py`, `backend/apps/shared/tests_structural_counters.py` (new)
- `docs/inputs/INPUT_DELTAS.md` (its own rows only)

**Done when:**

- `job_run` exists with the columns above and no free-text or untyped JSON column, proved by the structural test failing on a planted `TextField`.
- As `cw_app` with tenant A active: A reads its own rows and the platform's, writes only its own, and cannot move a row between zones.
- `platform_counters()` opens for a platform principal with either permission, raises for a tenant principal, raises while a tenant is active, and clears the setting on the way out including after an exception — four tests.
- Inside the window, a platform session reads every bank's `job_run` rows; outside it, none.
- The AST guard fails when a third module calls `platform_counters()`, proved by a planted call.
- `migrate_from_zero` applies the whole graph and the RLS guard lists `job_run`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/tenancy.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Two zones: the window is `SELECT` only, row-level security stays enabled and forced, and `cw_app` gains no bypass.
- Tenant content never reaches the platform: the table cannot hold it.
- A window is pinned by a guard and a test, never by a convention.

### c14-job-runs-b: every worker job leaves a row, and a failed one can be re-queued

**Requirements:** ADM-02
**Scenarios:** none (ADM-S5 is `c14-health-backend-b`'s)
**Depends on:** `c14-job-runs-a`, `c5-outbox-cursor`, `c11-run-scheduler`, `c12-exports-contract`, `c13-webhook-delivery`, `c13-siem-stream`
**Security review:** yes (a platform action causes a write inside a bank)

One helper in `apps/shared/jobs.py`, used by every `@tenant_task` and every beat job: it opens a `job_run` row at the start, closes it with counts at the end, and on an exception records `failed` with an `error_code` mapped from the exception type — never its message, never its arguments. A guard test walks every registered Celery task and fails on one that does not go through the helper, in the shape `tests_celery_registration.py` already uses for the beat schedule.

One typed counter joins `job_run` here, with its own migration: `lag_seconds`, a nullable integer that the outbox publisher and the SIEM delivery job write on their own row — the age in seconds of the oldest row still waiting when that run started, or zero when nothing was waiting. It is the only per-bank lag figure the console can have: after H-C a platform session with no tenant reads only the NULL-tenant rows of `outbox_event`, and ADR 0052 bars outbox payloads from the window in terms, so `outbox_event` is never added to the window map. The figure is a number, carries no payload and no destination, and the structural test of `c14-job-runs-a` passes it as an integer stat.

A second beat task, in the same module, deletes `job_run` rows older than `JOB_RUN_RETENTION_DAYS` (a setting, default 400) in bounded batches and writes its own row with counts. Without it the one table the console reads across every bank grows without limit, and a vendor review asks about exactly that; `usage_record` needs none, because it grows by nine rows per bank per month. This is the task's green point (rule 14): the purge is `c14-job-runs-purge`'s if the hour runs out.

`rebuild(job_run)` re-queues a failed job from its `kind`, `tenant_id` and `subject_kind`/`subject_id` alone, under `@tenant_task`, incrementing `attempts` on the same row; it takes no operator input, so a retry can only re-run what the bank's own schedule asked for. The retried task writes its audit row inside the tenant with a system actor, through `record()`, exactly as a scheduled run does. Nothing in the console reaches it yet: `retryConsoleJob` stays 501 until Alex answers `q-retry-write` (section 4), so the only caller here is the worker's own test.

Record in the commit body that `q-retry-write` is open and was put to Alex on 2026-09-20, and add its row to `docs/TODO_FOR_alex.md`. Amend no ADR: ADR 0042 is accepted, its sentence stands until the answer, and a pending note in an accepted ADR would read as the decision it is not.

**Owned paths:**

- `backend/apps/shared/jobs.py` (new), `backend/apps/shared/tests_jobs.py` (new)
- `backend/apps/shared/models.py` (the `JobRun.lag_seconds` column only) and its migration
- `backend/apps/shared/tasks.py` (the purge task only)
- `backend/config/settings.py` (one labelled block: `JOB_RUN_RETENTION_DAYS`, and the beat entry), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`
- `backend/apps/shared/tests_celery_registration.py` (the new guards only)
- each app's `tasks.py` (the helper call only, one line per task; the publisher and the SIEM delivery job also set `lag_seconds`)
- `docs/TODO_FOR_alex.md` (the q-retry-write row only)

**Done when:**

- Every registered Celery task writes a `job_run` row, proved by the guard failing on a planted task that does not.
- A failing task records `failed` with an `error_code` and no message, proved with an exception whose message carries a row value: the value appears nowhere in the row, the logs or Sentry.
- `rebuild` re-queues from the stored fields only, increments `attempts`, activates the right tenant, and writes a tenant audit row with a system actor.
- `rebuild` refuses a running or succeeded row, and refuses a row whose subject no longer exists, each with a named code.
- The outbox publisher and the SIEM delivery job write `lag_seconds` on their own row for the bank they ran for, zero when nothing waited, proved with a seeded backlog; no ADR file changed in the diff.
- The purge deletes only rows past the retention age, in batches, writes counts and no content, and is registered in the beat schedule.
- No task's own behaviour changed: every existing scenario is still green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/shared/jobs.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- `record()` on every write, in the same transaction.
- An exception message never reaches a row, a log or Sentry.
- A retry carries no operator input: it re-runs the bank's own job, nothing else.

### c14-billing-contract-a: the plan, the usage record and the bank's link to its plan

**Requirements:** NFR-05
**Scenarios:** none (NFR-S17 is `c14-billing-plans`')
**Depends on:** `c4-console-tenants-api`, `h-c-mixed-zones`
**Security review:** yes (two new tables, one tenant, and a money column)

Build the models. `Plan` in `apps/billing` (key `mig:billing`), a platform table:

| Column | Kind |
|---|---|
| `id` | uuid |
| `code` | citext, unique |
| `name` | text |
| `price_monthly_minor` | integer, minor units (ruling 3) |
| `currency` | a currency kind |
| `max_members`, `max_agents`, `min_cadence_hours`, `max_storage_bytes` | integers |
| `ai_budget_minor` | integer, minor units |
| `active` | boolean |

`UsageRecord` in `apps/billing`, a tenant table with `(tenant_id, metric, period_start)` as its key, `metric` a kind from the nine `schema.sql` names, `quantity` a `bigint`, and `currency` on the money metrics. `Tenant.plan` is a nullable foreign key in `apps/shared` (key `mig:shared`).

- `Plan` gets row-level security in H-C's split shape, open for `SELECT` and restricted for writes to a session with no tenant (section 1.4). `UsageRecord` gets the ordinary forced tenant policy and joins `tests_rls`, `tests_tenant_isolation` and the export and deletion coverage list of parallel-plan ruling 36.
- The structural test of `c14-job-runs-a` extends to `usage_record`: no free text, no untyped JSON. Since the two tasks are in different waves, this one adds the `usage_record` entry to the test the other created.
- `Meta.ordering` on both, because both are `.first()`ed.
- Seed exactly one plan, for the local seed and the E2E database, marked in the seed comment as a fixture and not a price list (section 1.4). It joins `tests_seed_integrity.py`.
- Write ADR 0054 ("billing without a payment provider"): what is built, what is not (ruling 4 and 5), and why money is an integer minor unit everywhere. Write the two INPUT_DELTAS §7 rows for the departures from `schema.sql`.

**Owned paths:**

- `backend/apps/billing/models.py`, `backend/apps/billing/migrations/`, `backend/apps/billing/tests_models.py`
- `backend/apps/shared/models.py` (the `Tenant.plan` field only) and a new `shared` migration
- `backend/apps/shared/kinds.py` (the metric and currency kinds only)
- `backend/apps/shared/tests_rls.py`, `tests_tenant_isolation.py`, `tests_seed_integrity.py`, `tests_structural_counters.py` (own entries only)
- `backend/apps/billing/seeds/__init__.py` (new)
- `docs/adr/0054-billing-without-a-payment-provider.md` (new), `docs/adr/README.md` (its row only)
- `docs/inputs/INPUT_DELTAS.md` (its own rows only)

**Done when:**

- Both tables apply from zero and carry the columns above, with no `numeric`, no float and no untyped JSON anywhere.
- A price or budget given as a decimal is refused by the field, with a test.
- `usage_record` is isolated: tenant B gets nothing of tenant A's, at the database level as `cw_app`.
- `plan` is readable by a tenant session and writable only with no tenant active, both proved as `cw_app`.
- The structural test fails on a planted `TextField` on either table.
- The seeded plan survives a second `seed_reference` run without losing an edit made through the console (the H5 rule), proved.
- `migrate_from_zero` is green and the ruling 36 coverage guard lists `usage_record`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps.billing apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/billing/*' (>= 90)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Money is an integer minor unit with a currency kind, here and nowhere else in the product.
- Tenant tables carry `tenant_id` under enabled and forced row-level security.
- Enums in code are for kinds only; the metric list is a kind because the code branches on it.

### c14-billing-contract-b: the six billing routes, behind their real gates

**Requirements:** NFR-05, ADM-02
**Scenarios:** none
**Depends on:** `c14-billing-contract-a`

Write `backend/apps/billing/api.py` and `schemas.py` once (key `billingapi`), mount the router, and send each operation to a named function that answers 501 `not_built` (rule 2):

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `listPlans` | `GET /console/plans` | SessionAuth, `tenants.manage` | `billing/plans_logic.py` |
| `createPlan` | `POST /console/plans` | SessionAuth, `tenants.manage` | `billing/plans_logic.py` |
| `updatePlan` | `PATCH /console/plans/{planId}` | SessionAuth, `tenants.manage`, `If-Match` | `billing/plans_logic.py` |
| `setTenantPlan` | `PUT /console/tenants/{tenantId}/plan` | SessionAuth, `tenants.manage` | `billing/plans_logic.py` |
| `listConsoleUsage` | `GET /console/usage` | SessionAuth, `tenants.manage` | `billing/usage_logic.py` |
| `getTenantUsage` | `GET /tenant/usage` | SessionAuth, `security.manage` | `billing/usage_logic.py` |

Schemas, camelCase through `CamelSchema`: `Plan` (`{id, code, name, priceMonthlyMinor, currency, limits{maxMembers, maxAgents, minCadenceHours, aiBudgetMinor, maxStorageBytes}, active, tenantCount}`), `PlanInput`, `TenantPlanInput` (`{planId}`), `TenantUsage` (`{periodStart, planName, limits, metrics[UsageMetric]}`), `UsageMetric` (`{metric, quantity, currency|null, limit|null}`), `ConsoleUsageRow` (`{tenantId, tenantName, metrics}`), `ConsoleUsageQuery` (`{periodStart?}` plus the shared `limit`, default 20, max 100).

`TenantUsage` carries no price, and `ConsoleUsageRow` carries no member name, no webhook and no content of any kind (ADR 0052). Add the six routes to the route lists in `permissions.py`; add nothing to `UNGATED_BY_DESIGN`. Write the INPUT_DELTAS §7 row for the six operations, which `docs/inputs/openapi.yaml` does not have.

**Owned paths:**

- `backend/apps/billing/api.py`, `backend/apps/billing/schemas.py`, `backend/apps/billing/tests_contract.py`
- `backend/config/api.py` (the router mount only)
- `backend/apps/shared/permissions.py` (the route lists only)
- `backend/scripts/contract_drift_pending.txt`, `docs/inputs/INPUT_DELTAS.md` (own lines only)

**Done when:**

- The six operations appear in `openapi.json` with the ids above and answer 501 `not_built` behind their real gate.
- A session without the permission gets 403 with `requiredPermission`, and an anonymous request 401 — both before the 501, proved per route.
- A tenant session on a `/console/` route and a platform session on `/tenant/usage` each get 403, proved.
- The route-permission guard is green and lists no ungated route.
- `bash generate-types.sh` produces types for all six without the task committing them.
- The diff stays inside the owned paths.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.billing apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/billing/api.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only; do not commit `openapi.json` or `api.generated.ts`

**Invariants:**

- No logic in `api.py`; no `Dict[str, Any]`; no `*args`/`**kwargs`.
- Every route has a permission; nothing joins `UNGATED_BY_DESIGN`.
- The API returns `key` and `kind`, never a phrase; errors are RFC 9457 with a `code`.

### c14-billing-plans: a plan is created, edited and assigned from the console

**Requirements:** NFR-05, ADM-02
**Scenarios:** NFR-S17 (`@integration`, un-skipped); ADM-S6's plans clause (`@integration`, extended)
**Depends on:** `c14-billing-contract-b`

Serve the four plan routes from `billing/plans_logic.py`:

- **List** returns every plan with the number of banks on it, in one query, never one per plan.
- **Create** takes the name, code, the five limits, the price and the currency. A price or budget sent as a decimal, a string with a separator, or a negative number answers 422 with the field named — NFR-S17's third line. A duplicate code answers 409.
- **Edit** takes `If-Match` and answers 409 `stale_write` on a stale version. Deactivating a plan a bank is on answers 409 `plan_in_use` (section 1.4).
- **Assign** moves one bank to one plan and is the only way a bank's plan changes. It answers 404 for an unknown bank and 422 for an inactive plan. It never changes what the bank already has (section 1.4).

Every write goes through `record()` in the same transaction, under no tenant for the plan itself and inside the bank for the assignment, so the bank's own audit log shows the change to its limits.

Un-skip NFR-S17 in `billing/tests_scenarios.py` and move billing/app.md's NFR-05 status cell to `in_progress`.

Extend ADM-S6's integration half with the one clause chunk 4 and chunk 8 cannot serve: PRD 0.4 rewords the scenario to "Tenants, plans and support access are managed from the console" and its Gherkin has the platform admin assign a plan and the tenant exist with that plan's limits. Add that assertion to the existing `ADM-S6` method — the assignment route, the bank's limits read back from the plan — and touch no other line of it; a note beside the scenario says chunk 14 owns the plans clause alone.

**Owned paths:**

- `backend/apps/billing/plans_logic.py` (new), `backend/apps/billing/tests_plans.py` (new)
- `backend/apps/billing/tests_scenarios.py` (the NFR-S17 method only)
- `backend/apps/billing/app.md` (the status cell and NFR-S17's note only)
- `backend/apps/governance/tests_scenarios.py` (the ADM-S6 plans assertion only), `backend/apps/governance/app.md` (ADM-S6's note only)
- `backend/scripts/contract_drift_pending.txt` (its own four lines, deleted)

**Done when:**

- NFR-S17 is green: the plan stores each limit and the price as integers with the currency code, and a decimal price answers 422.
- The four routes answer from the logic module and none answers 501.
- The assignment writes an audit row in the bank, with before and after limits, proved.
- ADM-S6's plans clause is green: the assigned bank exists with that plan's limits, and the rest of the scenario is unchanged.
- Deactivating a plan in use answers 409 and changes nothing.
- The list runs in one query whatever the number of plans, pinned by a query-count test.
- The endpoint stays inside `API_BUDGET_MS`, measured with `c14-perf-harness-a` and its route rows added to `backend/perf/routes.py`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.billing --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/billing/plans_logic.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- `record()` on every write; `If-Match` on the versioned record.
- Money never leaves the API as a float.
- An empty list answers 200, not 404.

### c14-billing-usage-a: the worker meters what a bank uses

**Requirements:** NFR-05
**Scenarios:** none (NFR-S19 is `-b`'s)
**Depends on:** `c14-billing-contract-a`, `c14-job-runs-b`, `c7-ai-log-backend`, `c11-run-scheduler`, `c9-evidence`, `c12-exports-contract`

`billing/metering.py` and a daily `@tenant_task` in `billing/tasks.py` that rolls the month's figures forward from facts that already exist, never from a new event stream:

| Metric | Source |
|---|---|
| `seats` | active memberships at the run, counted in the bank's own zone |
| `agent_runs` | `agent_run` rows for the bank's own agents in the month |
| `agent_cost`, `ai_tokens` | `ai_generation` cost and tokens in the bank's own zone (minor units) |
| `ask_queries`, `searches` | `ai_generation` rows by purpose |
| `api_calls` | the bank's API key requests, counted from the existing counter |
| `storage_bytes` | live evidence bytes in the bank |
| `exports` | completed export jobs in the month |

The task is idempotent: it writes each `(tenant, metric, period_start)` row with the figure as of the run, so a second run in the same day changes nothing and a missed day is caught up by the next. It runs under `@tenant_task` with the bank active, writes one `job_run` row through `c14-job-runs-b`'s helper, and records one system audit row per bank per run with counts only. bleqq's own platform agents have no tenant and are never metered against a bank (section 1.4).

Its beat entry joins `CELERY_BEAT_SCHEDULE` and the registration guard. `USAGE_ROLLUP_HOUR` is a setting with an env override.

**Owned paths:**

- `backend/apps/billing/metering.py`, `backend/apps/billing/tasks.py`, `backend/apps/billing/tests_metering.py` (new)
- `backend/config/settings.py` (one labelled block and the beat entry), `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`
- `backend/apps/shared/tests_celery_registration.py` (its own entry only)

**Done when:**

- A seeded month of runs, model calls, uploads and exports produces the eight metric rows with the right figures, per bank.
- Running the task twice in one day leaves the rows unchanged, proved.
- Tenant A's run never reads or writes tenant B's rows, proved as `cw_app`.
- A platform agent run appears in no bank's figures, proved.
- One `job_run` row per bank per run, and one audit row with counts and no content.
- The task is registered in the beat schedule and the guard is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.billing apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/billing/metering.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- `@tenant_task` in the worker; one tenant active at a time.
- The seat count comes from the bank's own zone and reaches the platform only as the `seats` metric.
- Idempotency on a repeated run; no double counting.

### c14-billing-usage-b: a bank sees its own figures, and the console sees every bank's

**Requirements:** NFR-05, ADM-02
**Scenarios:** NFR-S19 (`@integration`, un-skipped); ADM-S7 (`@integration`, un-skipped up to its failed-jobs and retry lines)
**Depends on:** `c14-billing-usage-a`, `c14-job-runs-a`, `c14-billing-limits-a`
**Security review:** yes (a read across every bank)

ADR 0052, tranche 2. `billing/usage_logic.py` serves both reads:

- **`GET /tenant/usage`** runs in the bank's own session under row-level security, with no window at all: it returns the month's metrics, the plan's name and its limits, and no price.
- **`GET /console/usage`** opens `tenancy.platform_counters(principal)` — the only module beside `governance/health_logic.py` the AST guard allows — reads `usage_record` for the month across banks, and closes the window before returning. It writes one platform audit row, `platform_counters.read`, recording the screen and the filters and never the figures.

Add the `usage_record` `FOR SELECT` policy keyed on `app.platform_counters` and its entry in the `tests_rls` window map that `c14-job-runs-a` created.

Un-skip NFR-S19's integration half: the tenant admin's read shows runs, spend against the cap and storage against the limit; the platform admin's read shows the same figures per bank; and no money value in either response is a float.

Un-skip ADM-S7, PRD 0.4's scenario for this window, as far as this task's routes reach: the figures of each bank read from tables that hold numbers, kinds and times only; one platform audit row per read, holding the screen and the filters and no figure; and the window refusing to open for a platform principal without `tenants.manage` or `system.health` and while a tenant is active. Its failed-jobs line is `c14-health-backend-b`'s and its retry line waits for `q-retry-write`, so both are noted in one line beside the scenario in `governance/app.md`, naming the task and the question — never weakened away.

**Owned paths:**

- `backend/apps/billing/usage_logic.py`, `backend/apps/billing/tests_usage.py` (new)
- a new `billing` migration (the `usage_record` window policy only)
- `backend/apps/shared/tests_rls.py` (the `usage_record` window entry only)
- `backend/apps/billing/tests_scenarios.py` (the NFR-S19 method only), `backend/apps/billing/app.md` (NFR-S19's note only)
- `backend/apps/governance/tests_scenarios.py` (the ADM-S7 method only), `backend/apps/governance/app.md` (ADM-S7's note only)
- `backend/scripts/contract_drift_pending.txt` (its own two lines, deleted)

**Done when:**

- NFR-S19's integration half is green for both readers.
- ADM-S7 is green over the figures, the audit row and both refusals, and its one note names `c14-health-backend-b` for the failed-jobs line and `q-retry-write` for the retry line.
- Outside the window a platform session reads no `usage_record` row; inside it, it reads every bank's and no other table's, proved by asserting that a read of `membership`, `audit_event`, `outbox_event` or `ai_generation` in the same window returns nothing.
- The window is closed before the response is serialised, proved by asserting the setting is empty afterwards, including after an exception.
- Each console read writes exactly one `platform_counters.read` audit row, and the row holds the screen and filters and no figure.
- A tenant response holds no price and no other bank.
- Both endpoints stay inside `API_BUDGET_MS`, with their rows added to `backend/perf/routes.py`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.billing apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/billing/usage_logic.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- The window is `SELECT` only, on two named tables, from two named modules, and every read is audited.
- Tenant content never reaches the platform.
- A read never writes anything but its audit row.

### c14-billing-limits-a: the plan's limits are enforced where a bank acts

**Requirements:** NFR-05
**Scenarios:** NFR-S18 (`@integration`, un-skipped and green up to storage and exports)
**Depends on:** `c14-billing-contract-a`, `c11-tenant-agent-controls`, `c8-ten-reassignment`

`billing/limits.py`: one function, `check_limit(tenant, metric, increment)`, that reads the bank's plan once, compares the current figure with the limit and raises `ValidationError` with code `above_plan_limit` and user-facing text naming the limit and its figure. A bank with no plan has no limits and is never refused. The limits are read from the plan row, so moving the bank to a larger plan lifts them with no deploy — NFR-S18's last line.

Call it at the two write points that exist by this wave:
- **Seats.** Inviting a member or reactivating one, in `identity/members_logic.py` (key `members`), counted against `max_members`. The last-admin recovery invitation is exempt (section 1.4), with a test.
- **Agents and cadence.** Switching on a tenant agent beyond `max_agents`, and setting a cadence below `min_cadence_hours`, in chunk 11's tenant agent controls.

A limit is enforced on the write that would exceed it and never retroactively (section 1.4): a test moves a bank past its limit, then moves it to a smaller plan, and proves that nothing is deactivated and that the next write is refused.

Un-skip NFR-S18 with a note in `app.md` that the storage and export halves are green from `c14-billing-limits-b`, mirroring how REG-S5 is handled in chunk 8.

**Owned paths:**

- `backend/apps/billing/limits.py`, `backend/apps/billing/tests_limits.py` (new)
- `backend/apps/identity/members_logic.py` (the seats check only)
- `backend/apps/agents/tenant_controls.py` (the agents and cadence checks only)
- `backend/apps/billing/tests_scenarios.py` (the NFR-S18 method only), `backend/apps/billing/app.md` (NFR-S18's note only)

**Done when:**

- A bank on a plan with three agents and a weekly cadence floor gets 422 `above_plan_limit` for a fourth agent and for a daily cadence, and succeeds after the platform admin moves it to a larger plan, with no deploy — NFR-S18.
- The seats limit refuses the invitation that would exceed it and names the limit, and never refuses the last-admin recovery.
- A bank over its limit after a downgrade keeps everything it has; only the next write is refused.
- A bank with no plan is never refused.
- The limit read adds no query per call beyond one, pinned by a query-count test.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.billing apps.identity apps.agents --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/billing/limits.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- A refusal is a 422 with a `code` the client branches on, never a message it parses.
- Validation at the trust boundary is never simplified away.
- No limit is a literal; each is a plan column.

### c14-billing-limits-b: storage and exports are held to the plan too

**Requirements:** NFR-05
**Scenarios:** NFR-S18 (closed)
**Depends on:** `c14-billing-limits-a`, `c9-evidence`, `c12-exports-contract`

The two remaining write points:
- **Storage.** An evidence upload that would take the bank past `max_storage_bytes` answers 422 `above_plan_limit`, checked before the file is written and again after the scanner, so a concurrent pair cannot both pass. The figure counts live evidence only; soft-deleted evidence is not counted, which matches what the usage screen shows.
- **Exports.** Creating an export job beyond the month's `exports` figure answers the same code. The tenant's final exit export (D-56) is exempt, because a bank must always be able to take its data out, with a test.

Close NFR-S18 in `app.md` and in `tests_scenarios.py`.

**Owned paths:**

- `backend/apps/cases/evidence_logic.py` (the storage check only)
- `backend/apps/reports/exports_logic.py` (the export check only)
- `backend/apps/billing/tests_limits_storage.py` (new)
- `backend/apps/billing/tests_scenarios.py` (the NFR-S18 method only), `backend/apps/billing/app.md` (NFR-S18's note only)

**Done when:**

- An upload that would exceed the storage limit is refused before anything is written, and no orphan object is left, proved.
- Two concurrent uploads that together exceed the limit cannot both succeed, proved with a concurrency test.
- Soft-deleted evidence does not count toward the limit, and the usage screen's figure matches the one the check uses, proved by reading both from one helper.
- The exit export is never refused by a limit.
- NFR-S18 is green in full, with no note left about an unbuilt half.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.billing apps.cases apps.reports --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/billing/*'`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- A refused upload leaves nothing behind.
- One figure, one source: the check and the screen read the same helper.
- A bank can always take its data out.

### c14-health-backend-a: system health, per component and per bank

**Requirements:** ADM-02, NFR-04
**Scenarios:** ADM-S4 extended (`@integration`, both new console destinations)
**Depends on:** `c14-job-runs-a`, `c14-job-runs-b` (the `lag_seconds` counter and the jobs that write it), `c14-billing-contract-b`, `c13-int-contract`, `c11-run-scheduler`, `c12-exports-contract`, `c13-webhook-delivery`, `c13-siem-stream`, `c5-watch-sources-coverage`, `c5-agent-runs`
**Security review:** yes (a read across every bank)

Declare the console health routes once in `governance/api.py` and `schemas.py` (key `gov`), and serve the first of them from `governance/health_logic.py`:

| Operation | Route | Gate | Answers from |
|---|---|---|---|
| `getConsoleHealth` | `GET /console/health` | SessionAuth, `system.health` | `governance/health_logic.py` |
| `listConsoleJobs` | `GET /console/jobs` | SessionAuth, `system.health` | `governance/jobs_logic.py` (501 until `-b`) |
| `retryConsoleJob` | `POST /console/jobs/{jobId}/retry` | SessionAuth, `system.health` | `governance/jobs_logic.py` (501 until `-b`) |

`ConsoleHealth` = `{components[ComponentState], sources[SourceCoverage], recentRuns[RunSummary], lag[TenantLag]}`. `components` calls `apps/shared/health_check.py`'s own checks, so `/health/` and the console never disagree (ruling 7). `lag` is the `lag_seconds` counter of the newest outbox-publisher row and the newest SIEM-delivery row per bank, read inside `tenancy.platform_counters()` from `job_run`, with the row's `started_at` beside it so the screen can say how old the figure is. The console never reads `outbox_event` itself: after H-C a session with no tenant sees only its NULL-tenant rows, and ADR 0052 keeps outbox payloads out of the window, so `outbox_event` is not in the window map and this task does not add it. No outbox payload, no webhook URL and no member name reaches the response. `recentRuns` and `sources` are the existing library-zone reads, which need no window.

Each console read writes one `platform_counters.read` platform audit row with the screen and filters.

Extend ADM-S4's integration half once, for both new console destinations and the four plan routes (ruling 10): a platform admin reaches console health, jobs and plans; a library editor gets 403 with the permission named on each; and each destination the other role holds is absent from that role's navigation.

**Owned paths:**

- `backend/apps/governance/api.py`, `backend/apps/governance/schemas.py`, `backend/apps/governance/health_logic.py` (new), `backend/apps/governance/tests_health.py` (new)
- `backend/apps/shared/permissions.py` (the three route lists only)
- `backend/apps/governance/tests_scenarios.py` (the ADM-S4 method only), `backend/apps/governance/app.md` (ADM-S4's note only)
- `backend/scripts/contract_drift_pending.txt` (the two job-route lines only), `docs/inputs/INPUT_DELTAS.md` (own lines only)

**Done when:**

- `GET /console/health` answers with every component, source coverage, recent runs and per-bank lag, and matches `/health/` on the component states, proved by asserting both in one test with the worker stopped.
- The two job routes answer 501 `not_built` behind `system.health`, and 403 or 401 before that.
- Outside the window the lag read returns nothing; inside it, it reads `job_run` and no other table, proved, and `outbox_event` is absent from the window map in `tests_rls.py`.
- No response field holds an outbox payload, a webhook URL, a member name or any free text from a bank.
- ADM-S4's integration half is green over the three new console destinations and the four plan routes, and its note in `governance/app.md` no longer lists system health or plans among the surfaces it does not reach.
- `contract_drift_pending.txt` carries the two job routes and not `getConsoleHealth`, which this task serves.
- The endpoint stays inside `API_BUDGET_MS` with its row in `backend/perf/routes.py`, and its query count is pinned so the lag read is one query, not one per bank.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/governance/health_logic.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- The window is `SELECT` only on the two named tables, and every read is audited.
- `/health/` is unchanged and stays unauthenticated; the console surface is a separate gated route.
- No logic in `api.py`.

### c14-health-backend-b: failed jobs, and re-queuing one

**Requirements:** ADM-02
**Scenarios:** ADM-S5 (`@integration`, un-skipped and green but for its retry line); ADM-S7's failed-jobs line (`@integration`, closed here)
**Depends on:** `c14-health-backend-a`, `c14-job-runs-b`
**Security review:** yes (a read across every bank)

Serve the failed-jobs list from `governance/jobs_logic.py`:

- **List** returns failed `job_run` rows inside `tenancy.platform_counters()`, filtered by bank, kind and time, paginated as every list is (default 20, max 100), carrying the id, the bank's name from the platform's own tenant table, the kind, the `error_code`, the attempts and the times. No message, no stats blob, no subject title.
- **Retry** is not served here. `retryConsoleJob` keeps answering 501 `not_built` behind `system.health`, and its `contract_drift_pending.txt` line stays, until Alex answers `q-retry-write` (section 4): the route is the one place where a platform action causes a write inside a bank, which accepted ADR 0042 does not allow. `rebuild()` exists and is proved in the worker by `c14-job-runs-b`, so serving the route afterwards is a route, a test and an ADR line.

Un-skip ADM-S5's integration half and assert the part that exists, as `c14-billing-limits-a` does for NFR-S18: with the worker stopped `/health/` answers 503 naming `worker`, and coverage, runs, lag and failed jobs are listed; with the worker back `/health/` answers 200 with the ping bounded to one attempt. Its "with a retry action per failed job" line is asserted only as far as the route exists — `retryConsoleJob` answering 501 behind `system.health` — with one note beside the scenario naming `q-retry-write`. The Gherkin is not reworded to fit.

**Owned paths:**

- `backend/apps/governance/jobs_logic.py` (new), `backend/apps/governance/tests_jobs.py` (new)
- `backend/apps/governance/tests_scenarios.py` (the ADM-S5 method and ADM-S7's failed-jobs assertion only), `backend/apps/governance/app.md` (the ADM-02 status cell and the ADM-S5 and ADM-S7 notes only)
- `backend/scripts/contract_drift_pending.txt` (the list route's line only, deleted; the retry route's line stays)

**Done when:**

- ADM-S5's integration half is green, worker down and worker up, but for its retry line, which is noted with `q-retry-write` named.
- ADM-S7's failed-jobs line is green: each bank's failed jobs are listed from `job_run` inside the window, and the read writes its own `platform_counters.read` row.
- `retryConsoleJob` still answers 501 `not_built` behind `system.health`, and 403 or 401 before it, proved; no code path in this task writes inside a tenant.
- The list holds no free text from a bank, proved by asserting the response against the model's kind columns.
- `listConsoleJobs` no longer answers 501 and its `contract_drift_pending.txt` line is gone; the retry route's line is still there, naming `q-retry-write`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.governance apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/governance/jobs_logic.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- `record()` on every write, in the same transaction, on both sides.
- A retry carries no operator input.
- Paginate: default 20, max 100.

### c14-eval-runs: the evaluation harness runs as a job from the console

**Requirements:** SRC-05, ADM-02
**Scenarios:** SRC-S8 stays green
**Depends on:** `c14-job-runs-b`, `c7-eval-routes`, `c7-eval-gate`

`c7-eval-routes` hands `startEvalRun` to chunk 14 by name, because running the harness from the console is a job and no job runner with a status endpoint existed in chunk 7. It moved the line in `contract_drift_pending.txt` to chunk 14; this task serves it.

Two operations in `apps/search/api.py` (key `searchapi`, free by this wave), both under `eval.manage` and both platform-only:

| Operation | Route | Answers |
|---|---|---|
| `startEvalRun` | `POST /eval/runs` | 202 with `{jobRunId, status}` |
| `getEvalRunStatus` | `GET /eval/runs/{jobRunId}` | the job's status, times, attempts and `error_code` |

The second is the status endpoint playbook 10 requires of every job, and it is declared and served here rather than in a separate contract task, exactly as `c7-eval-routes` argued for its own three. The eval run is a platform job with no tenant, so its `job_run` row is visible to a platform session through the mixed `FOR SELECT` policy and needs no window at all — say so in the task and prove it, so nobody widens `platform_counters` for it.

The job itself runs the recorded harness in the worker through `c14-job-runs-b`'s helper, writes the `eval_run` row the same way `manage.py record_eval_run` does (one code path, not two), and records one platform audit row naming who started it. A second start while one is running answers 409 `eval_run_in_progress`, because two concurrent runs would race on the same baseline.

Add the INPUT_DELTAS §7 row for `getEvalRunStatus`, which `docs/inputs/openapi.yaml` does not have, and delete both chunk 14 lines from `contract_drift_pending.txt`.

**Owned paths:**

- `backend/apps/search/api.py`, `backend/apps/search/schemas.py` (the two operations only)
- `backend/apps/search/eval_runs.py` (new), `backend/apps/search/tests_eval_runs.py` (new)
- `backend/apps/search/tasks.py` (the eval job only)
- `backend/apps/shared/permissions.py` (the two route lists only)
- `backend/scripts/contract_drift_pending.txt`, `docs/inputs/INPUT_DELTAS.md` (own lines only)

**Done when:**

- A holder of `eval.manage` starts a run, gets 202 with a job id, and reads its status until it finishes; a tenant session and a tenant key are refused on both routes with `requiredPermission` named.
- The finished run writes the same `eval_run` row the management command writes, proved by running both and comparing.
- A second start while one runs answers 409 and queues nothing.
- The status read works without `platform_counters` being opened, proved by asserting the setting is empty throughout.
- A failed run leaves `failed` with an `error_code` and no message.
- Both chunk 14 lines are gone from `contract_drift_pending.txt`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.search apps.shared --settings=config.test_settings --noinput && ./run.sh run coverage report --include='apps/search/eval_runs.py' (>= 95)`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `python backend/scripts/search_eval.py`
- `bash generate-types.sh && (cd backend && ./run.sh run python scripts/contract_drift.py)` as a check only

**Invariants:**

- Exports, imports and agent runs are jobs with a status endpoint; so is this.
- One code path writes an `eval_run` row, not two.
- The evaluation console is platform-only, at the route and at the database.
- No window is opened for a read that does not need one.

### c14-fe-eval-run: starting a run from the evaluation screen

**Requirements:** SRC-05, ADM-02
**Scenarios:** none (ADM-S4's console walk already covers the destination)
**Depends on:** `c14-eval-runs`, `c7-fe-console-eval-sets`

Add the Run control to the console's evaluation screen, which `c7-fe-console-eval-sets` built without one because the route answered 501 and rule 3 forbids a screen calling a stub: a button, its confirmation, the running state read from `getEvalRunStatus`, the finished state that refreshes the run list, and the 409 `eval_run_in_progress` message. The polling interval is a constant in the feature, not a literal in the component, and polling stops when the job ends or the screen unmounts.

**Owned paths:**

- `frontend/src/components/console/EvalRunControl.tsx` (new)
- `frontend/src/components/console/EvaluationScreen.tsx` (the control's mount only)
- `frontend/src/features/evaluation/{api,hooks}.ts` (the two operations only)
- the `consoleEvaluation` message namespace pair in `frontend/src/messages/` (its own keys only)
- `docs/plans/UI_Implementation_Plan.md` (its own row only)

**Done when:**

- The control starts a run, shows it running, and shows the new row when it finishes, against the real backend.
- The 409 renders as its own message, branching on `code`.
- A failed run shows its `error_code` as a message from the catalog, never as a raw value.
- Polling stops on unmount and when the job ends, proved by a unit test.
- A role without `eval.manage` sees no control.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- No string literals in JSX; every string in the catalog.
- The client branches on `code`, never on `detail`.
- No interval is a literal in a component.

### c14-e2e-seed: the plan, the figures and the failed job the journeys walk

**Requirements:** NFR-05, ADM-02
**Scenarios:** none (it seeds for `c14-e2e-billing` and `c14-e2e-health`)
**Depends on:** `c14-billing-usage-b`, `c14-health-backend-b`

Extend `backend/apps/shared/e2e_seed.py` with one call, idempotent and deterministic, anchored to the tenant-local date plus a fixed wall time (rule 10):

- Two plans: the one `c14-billing-contract-a` seeds, and a larger one, so the journey can move a bank between them and prove NFR-S18's "without a deploy" line.
- Both seeded banks on the smaller plan, one of them deliberately over its agent limit, so the usage screen has an over-limit row to draw.
- A month of `usage_record` rows for both banks, with figures that make the tenant screen and the console screen show the same numbers.
- Three `job_run` rows: one succeeded, one failed with an `error_code` and a subject that still exists, and one failed with a subject that has been removed, so the failed-jobs table has both kinds to draw and the retry journey can prove both outcomes once `q-retry-write` is answered.
- The platform admin login the health and plans journeys sign in with, if `c4-seed-proposals` has not already seeded one.

Nothing is mocked and nothing is inserted from a test: the seed is the only source, as CLAUDE.md §11 requires.

**Owned paths:**

- `backend/apps/shared/e2e_seed.py` (one seed call only)
- `backend/apps/shared/tests_seed_integrity.py` (its own entries only)

**Done when:**

- `seed_e2e` runs twice with the same result, proved.
- Every seeded figure derives from the anchor date, and no row depends on the real "today"; a test moves the clock a month and the seed still produces a full month.
- The seed integrity test covers the new rows.
- `seed_e2e` still refuses to run on a deployed environment.
- The E2E database boots and the existing `@smoke` journeys are still green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps.shared --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `cd frontend && npm run test:e2e -- --grep @smoke`

**Invariants:**

- Extend `seed_e2e`, never mock.
- Clocks anchor to the tenant-local date plus a fixed wall time.
- The seed refuses to run deployed.

### c14-fe-console-plans-a: the console's Plans screen

**Requirements:** NFR-05, ADM-02, NFR-03
**Scenarios:** none (NFR-S17's journey is `c14-e2e-billing`'s)
**Depends on:** `c14-billing-plans`, `c14-cards-console-usage-a`, `c4-console-shell`, `x-frontend-split`

Build the console Plans destination from `design/screens/console-plans.html`, on the console shell: the list with each plan's limits, price and bank count; the create and edit form; the deactivate control with its 409 `plan_in_use` path. It is the first screen in the `consolebillingfe` chain and creates `frontend/src/features/console-billing/{types,api,hooks}.ts` with the four plan operations only. The console's billing feature is separate from the bank's own, so the console chain and the tenant chain never queue behind each other.

Money is entered as a whole amount and sent as minor units, in one conversion in `plan-presentation.ts`, with a unit test for the rounding and for a value that is not a number. Every state of `states.html` is built; every string is in the console catalog namespace; no string literal appears in JSX; pills come from `Pill` and a presentation function, never from a colour chosen in the component.

**Owned paths:**

- `frontend/src/app/(console)/plans/page.tsx`, `frontend/src/components/console/PlansScreen.tsx`, `frontend/src/components/console/PlanForm.tsx`
- `frontend/src/features/console-billing/{types,api,hooks}.ts`, `frontend/src/features/console-billing/plan-presentation.ts` and its test
- the `consolePlans` message namespace pair in `frontend/src/messages/` (`x-frontend-split`'s layout)
- `frontend/src/shared/navigation/registry.ts` (its own entry only)
- `docs/plans/UI_Implementation_Plan.md` (its own row only)

**Done when:**

- The screen renders the list, the form, both write paths and all four states against the real backend.
- A decimal price is refused by the field before the request, and the server's 422 is rendered with its field named.
- `plan_in_use` is rendered as its own message, branching on `code` and never on `detail`.
- A platform role without `tenants.manage` sees no Plans entry in the navigation and the Restricted screen on the route.
- `npm run lint`, `typecheck`, `test:coverage`, `check:messages` and `build` are green, and the navigation snapshot is regenerated by the main agent at merge.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- Pills only through `Pill`; no string literals in JSX; typography roles only.
- The client branches on `code`, never on `detail`.
- Money is never a float in the client either.

### c14-fe-console-plans-b: assigning a plan to a bank

**Requirements:** NFR-05, ADM-02
**Scenarios:** none
**Depends on:** `c14-fe-console-plans-a`, `c4-fe-tenants`

The assignment lives where a platform admin already works on one bank: the console tenant detail screen, which `c4-fe-tenants` owns. Add the plan row and its change control there — the current plan, its limits, a picker of active plans, and the confirmation that says what changes and what does not (section 1.4: nothing the bank already has is removed).

This task holds `consolebillingfe` after `-a` and reads the tenants feature without taking the `ten` key: it adds no tenants operation, only the one billing call.

**Owned paths:**

- `frontend/src/components/console/TenantPlanPanel.tsx` (new)
- `frontend/src/components/console/TenantDetailScreen.tsx` (the panel mount only)
- `frontend/src/features/console-billing/{api,hooks}.ts` (the assign operation only)
- the `consolePlans` message namespace pair in `frontend/src/messages/` (its own keys only)
- `docs/plans/UI_Implementation_Plan.md` (its own row only)

**Done when:**

- The panel shows the bank's plan and limits, changes it, and shows the new limits without a reload.
- The confirmation says plainly that nothing the bank has is removed.
- A bank with no plan shows the empty state and can be given one.
- The four states are built and every string is in the catalog.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- One screen, one owner: only the panel mount is touched in another package's file.
- No string literals in JSX; pills through `Pill`.

### c14-fe-usage-a: the bank's own usage screen

**Requirements:** NFR-05, NFR-03 (not ADM-01: section 1.4 reads it as not listing plan or usage among the tenant-admin surfaces, which is why the read is gated by `security.manage`)
**Scenarios:** none (NFR-S19's journey is `c14-e2e-billing`'s)
**Depends on:** `c14-billing-usage-b`, `c14-cards-console-usage-b`, `x-frontend-split`

Build Admin → Usage from `design/screens/admin-usage.html`: runs, "Spend this month" against the cap, storage against the limit, seats against the limit, and the plan's name, with no price. An over-limit figure is a `warning` pill from the presentation function, never coloured text. It owns the `billingfe` chain alone: `frontend/src/features/billing/` holds the bank's own usage and nothing else, so no console screen queues behind it.

A member without `security.manage` never sees the entry and gets the Restricted screen on the route, which is what every other admin destination does.

**Owned paths:**

- `frontend/src/app/(tenant)/admin/usage/page.tsx`, `frontend/src/components/admin/UsageScreen.tsx`
- `frontend/src/features/billing/{types,api,hooks}.ts` (the tenant operation only)
- `frontend/src/features/billing/usage-presentation.ts` and its test
- the `usage` message namespace pair in `frontend/src/messages/` (`x-frontend-split`'s layout)
- `frontend/src/shared/navigation/registry.ts`, `frontend/src/features/shared/tone-by-kind.ts` (own entries only)
- `docs/plans/UI_Implementation_Plan.md` (its own row only)

**Done when:**

- The screen renders every metric with its limit, and an over-limit metric as a `warning` pill.
- A bank with no plan shows the figures and says no limits apply, rather than showing zeros.
- No price and no other bank appears anywhere on the screen or in the response it reads.
- All four states are built; the screen reaches real data inside its budget, measured with `c14-perf-harness-b` and recorded in the UI plan.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- Tone by kind or slot, never by a person.
- A permission-limited page is a Restricted screen, not a raw 403.
- Screen copy says what the user is doing; no requirement IDs on screen.

### c14-fe-usage-b: usage per bank in the console

**Requirements:** NFR-05, ADM-02
**Scenarios:** none
**Depends on:** `c14-fe-console-plans-b`, `c14-billing-usage-b`

The console's Usage destination from `design/screens/console-usage.html`: the month picker, one row per bank with its metrics against its plan's limits, and the note that the console reads numbers only and that every read is logged. It sorts by the bank's name and paginates as every list does.

**Owned paths:**

- `frontend/src/app/(console)/usage/page.tsx`, `frontend/src/components/console/ConsoleUsageScreen.tsx`
- `frontend/src/features/console-billing/{api,hooks}.ts` (the console operation only)
- the `consoleUsage` message namespace pair in `frontend/src/messages/` (`x-frontend-split`'s layout)
- `frontend/src/shared/navigation/registry.ts` (its own entry only)
- `docs/plans/UI_Implementation_Plan.md` (its own row only)

**Done when:**

- The screen lists every bank's metrics for the chosen month, with the over-limit rows marked.
- The month picker defaults to the current month and reads nothing before a month is chosen.
- A library editor sees no Usage entry and the Restricted screen on the route.
- The four states are built and the screen reaches real data inside its budget, recorded in the UI plan.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- Paginate: default 20, max 100.
- The screen shows numbers, kinds and times; it has nothing else to show.

### c14-fe-health-a: the console's System health screen

**Requirements:** ADM-02, NFR-04, NFR-03
**Scenarios:** none (ADM-S5's journey is `c14-e2e-health`'s)
**Depends on:** `c14-health-backend-a`, `c14-cards-console-usage-b`, `c4-console-shell`, `x-frontend-split`

Build the System health destination from `design/screens/console-health.html`: the components with their state, source coverage, recent runs and per-bank lag. A failing component is a `negative` pill and a lagging bank a `warning` pill, both from the presentation function. When the backend answers 503 the screen shows the failing component as its own state, not an error page — ADM-S5's "the screen shows it".

It creates `frontend/src/features/system-health/{types,api,hooks}.ts` (key `healthfe`) with the health operation only.

**Owned paths:**

- `frontend/src/app/(console)/health/page.tsx`, `frontend/src/components/console/SystemHealthScreen.tsx`
- `frontend/src/features/system-health/{types,api,hooks}.ts`, `frontend/src/features/system-health/health-presentation.ts` and its test
- the `systemHealth` message namespace pair in `frontend/src/messages/` (`x-frontend-split`'s layout)
- `frontend/src/shared/navigation/registry.ts`, `frontend/src/features/shared/tone-by-kind.ts` (own entries only)
- `docs/plans/UI_Implementation_Plan.md` (its own row only)

**Done when:**

- Every component, coverage row, run and lag row renders against the real backend.
- A 503 renders as the screen's own state with the component named, and the `api-guard` declaration for it is written where it happens.
- A role without `system.health` sees no entry and the Restricted screen.
- All four states are built and the screen reaches real data inside its budget, recorded in the UI plan.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- A degraded backend is a screen state, not a crash.
- Pills through `Pill`; tone by kind.

### c14-fe-health-b: failed jobs, with a retry

**Requirements:** ADM-02
**Scenarios:** none (ADM-S5's journey is `c14-e2e-health`'s)
**Depends on:** `c14-fe-health-a`, `c14-health-backend-b`

The failed-jobs table on the same page: bank, kind, error code, attempts and times. The list paginates and filters by bank and kind. No Retry action is built: `retryConsoleJob` answers 501 until Alex answers `q-retry-write` (section 4), and rule 3 forbids a screen calling a stub. The control, its confirmation and the 409 and 422 messages are built by the task that serves the route.

**Owned paths:**

- `frontend/src/components/console/FailedJobsPanel.tsx` (new)
- `frontend/src/components/console/SystemHealthScreen.tsx` (the panel mount only)
- `frontend/src/features/system-health/{api,hooks}.ts` (the jobs list operation only)
- the `systemHealth` message namespace pair in `frontend/src/messages/` (its own keys only)
- `docs/plans/UI_Implementation_Plan.md` (its own row only)

**Done when:**

- The table lists failed jobs with their filters and pagination, and shows the empty state when there are none.
- No Retry control is rendered and no component calls `retryConsoleJob`, proved by the feature holding no such operation.
- No free text from a bank appears in the table, because the response holds none.
- The four states are built and every string is in the catalog.

**Gates:**

- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run check:copy-drift && npm run build`

**Invariants:**

- The client branches on `code`, never on `detail`.
- An empty list is an empty state, not an error.

### c14-e2e-billing: the plan and usage journeys

**Requirements:** NFR-05, ADM-02
**Scenarios:** NFR-S17 and NFR-S19 (`@e2e`, un-fixmed); ADM-S6's plans clause (`@e2e`, extended)
**Depends on:** `c14-e2e-seed`, `c14-fe-console-plans-a`, `c14-fe-console-plans-b`, `c14-fe-usage-a`, `c14-fe-usage-b`

Two journeys in `frontend/tests/e2e/billing.journey.spec.ts`, against the real stack with a production Next build, signing in through the UI with a seeded passkey.

- **NFR-S17.** The platform admin signs in, opens Plans, creates "Nordic" with fifty members, three agents, a weekly cadence floor, a monthly AI budget and a price of 250 000 SEK minor units, sees it in the list with its limits, and is refused with the field named when a price is typed with a decimal separator.
- **NFR-S19.** The tenant admin signs in, opens Admin → Usage, and sees runs, spend against the cap and storage against the limit for the seeded month, with the over-limit metric marked. The platform admin then opens the console's Usage, chooses the same month, and sees the same figures for that bank beside the other bank's. The journey asserts that no value on either screen is rendered from a float, by reading the API response through the guard.

- **ADM-S6, the plans clause.** In `governance.journey.spec.ts`, where that journey lives, the platform admin assigns a plan to a bank from the console tenant detail and sees the bank's limits change to the plan's; the rest of the journey, which chunk 4 and chunk 8 own, is untouched. It is the only block this task adds to that file, and `c14-e2e-health` adds its own blocks under rule 5.

Every journey imports `test` from `support/api-guard` and declares every expected error where it happens. Teardown restores the seeded rows on failure too.

**Owned paths:**

- `frontend/tests/e2e/billing.journey.spec.ts` (its own blocks only)
- `frontend/tests/e2e/governance.journey.spec.ts` (the ADM-S6 plans block only)
- `backend/apps/billing/app.md` (the `@e2e` notes on NFR-S17 and NFR-S19 only)
- `backend/apps/governance/app.md` (ADM-S6's `@e2e` note only)

**Done when:**

- Both journeys are green against the real stack, and green twice in a row from a fresh seed.
- ADM-S6's plans clause is green in its own journey, and no other block of that file changed.
- No API is mocked, no token or cookie is injected, and sign-in goes through the UI.
- Every expected 4xx is declared at its place; no undeclared `/api/` response of 400 or above and no page exception occurs.
- The journeys run in the one pinned language and depend on no real date.

**Gates:**

- `cd frontend && npm run test:e2e -- --grep "NFR-S17|NFR-S19|ADM-S6"`
- `npm run lint && npm run typecheck && npm run build`

**Invariants:**

- Sign in through the UI with a passkey; never inject a token.
- Extend `seed_e2e`, never mock; backend down means the tests fail.
- Clocks anchor to the tenant-local date.

### c14-e2e-health: the system health journey, and the console's full walk

**Requirements:** ADM-02
**Scenarios:** ADM-S5 (`@e2e`, un-fixmed); ADM-S4 (`@e2e`, extended)
**Depends on:** `c14-e2e-seed`, `c14-fe-health-a`, `c14-fe-health-b`, `c14-fe-console-plans-a`

- **ADM-S5.** With the worker stopped, the platform admin opens System health and sees the worker named as the failing component, with source coverage, recent runs, outbox lag and the failed jobs listed; then, with the worker back, reloads and sees every component ok. Stopping and starting the worker is done through the E2E stack's own control, not by mocking the ping. The two retry steps are not walked: the route answers 501 and the screen has no control until Alex answers `q-retry-write` (section 4), so the journey's title carries the scenario id and its note names the question.
- **ADM-S4, extended.** The console walk gains the three new destinations: the platform admin reaches Plans, Usage and System health; the library editor reaches none of them and sees no entry for them in the navigation.

**Owned paths:**

- `frontend/tests/e2e/governance.journey.spec.ts` (the ADM-S4 and ADM-S5 blocks only)
- `backend/apps/governance/app.md` (the `@e2e` notes on ADM-S4 and ADM-S5 only)
- `frontend/tests/e2e/support/worker-control.ts` (new, if the stack has no control yet)

**Done when:**

- ADM-S5 is green with the worker really stopped and really restarted; nothing about the ping is mocked.
- The journey's note names `q-retry-write` for the two retry steps it does not walk, and no step works around the 501 route.
- ADM-S4 walks every console destination that exists, including the three new ones, for both platform roles.
- The journeys are green twice in a row from a fresh seed.

**Gates:**

- `cd frontend && npm run test:e2e -- --grep "ADM-S4|ADM-S5"`
- `npm run lint && npm run typecheck && npm run build`

**Invariants:**

- Never mock an API in E2E, and never mock the component the scenario is about.
- Declare an expected error where it happens.

### c14-runbooks: the operator runbooks the deployed product needs

**Requirements:** NFR-04, ADM-02
**Scenarios:** none
**Depends on:** `c13-secret-box`, `c13-webhook-delivery`, `c13-siem-stream`, `c14-health-backend-b`

Four runbooks in `docs/runbooks/`, each written so an operator who has not read the code can follow it, and each starting from a signal the product actually shows:

- `SECRET_ROTATION.md`: rotating `SECRET_KEY`, `INTEGRATION_SECRET_KEYS`, an agent key, a SCIM key and the storage credentials — in what order, what breaks during each, how to roll back, and what each rotation writes to the audit log.
- `DELIVERY_FAILURES.md`: a webhook, a SIEM stream or a ticket delivery failing — where it shows (the console's lag and failed jobs, the bank's own integration screen), what the retry does, when to retry from the console and when the bank must act, and what never to do (replaying a delivery by hand from the outbox).
- `SYSTEM_HEALTH.md`: reading `GET /console/health` and `/health/`, what each component's failure means, the bounded worker ping, and the first three checks for each failing component.
- `EU_PROCESSORS.md`: what the boot refuses and why, how to add a processor (a reviewed code change with a Verification log row, the subprocessor register updated and banks given advance notice — never an environment variable), and the checklist to run before a bank tenant is created.

Each runbook cites the code or the route it describes, so a stale step is visible.

**Owned paths:**

- `docs/runbooks/SECRET_ROTATION.md`, `docs/runbooks/DELIVERY_FAILURES.md`, `docs/runbooks/SYSTEM_HEALTH.md`, `docs/runbooks/EU_PROCESSORS.md` (new)
- `docs/runbooks/RAILWAY_VARIABLES.md` (cross-references only)

**Done when:**

- Each runbook's steps match the routes and settings on `main`, cited by name.
- Each names what it must never do and why.
- The EU runbook states plainly that an allowlist is code and that adding an entry is a reviewed change with advance notice.
- Nothing in them asks the operator to read a log the product does not write.

**Gates:**

- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- A runbook describes what exists; a missing step is written as missing.
- The owner deploys; a runbook never tells an agent to.

### c14-owasp-auth: the authentication and session review

**Requirements:** NFR-04
**Scenarios:** none
**Depends on:** `c14-owasp-scope`, `c13-sso-saml`, `c13-scim`, `c13-ip-allowlist`, `c11-credential-policy`, `c11-session-policy`

A security-review sub-agent reviews the auth area as `OWASP_REVIEW_SCOPE.md` defines it, over the code on `main`, and answers with evidence:

- **Enrolment.** Can the emailed code be replayed, brute-forced, or used after the first passkey exists? Does a code request for an enrolled user differ from one for a new one in body, status or timing? Is the code bound to its token on every path?
- **Passkeys.** Is the challenge single-use and bound to the session? Is the origin and RP ID checked on every assertion? Is the sign count or backup-eligibility change handled? Can a stricter credential policy lock a bank out (D-55), and does our own attestation check run rather than the library's result alone?
- **Sessions.** Is the refresh rotation one-flight and replay-detecting? Does revocation take effect on the next request? Are idle and absolute limits enforced server-side? Can a support session outlive its grant?
- **Step-up.** Is the freshness window enforced on every listed action, and is the assertion id on the audit row (H8)?
- **API keys and SCIM.** Is a key shown once, stored hashed, scoped, revocable and rate-limited? Can a SCIM key reach anything but SCIM? Can a tenant key reach a platform route?
- **SSO.** Can a response start at the provider, be replayed, or link an account by an email claim (D-58)? Does enforcement apply after the passkey, never instead of it?
- **The IP allow-list.** Can it be bypassed through a forwarded header, and how does a locked-out admin recover?

Run with it: `tests_route_permissions`, `tests_authentication`, `tests_rls`, `tests_four_eyes`.

**Owned paths:**

- `docs/security/OWASP_AUTH_2026-09-20.md` (new)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- Every question is answered with a file, a line and a scenario that reproduces, or with the code that makes the attack impossible.
- Each finding carries a severity, the fix asked for and the files it touches, so `c14-owasp-fixes-auth` can declare owned paths from it.
- Findings below medium become `HARDENING.md` rows with a package named.
- The four guard suites are green on `main`, with the command output in the report.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_route_permissions apps.shared.tests_authentication apps.shared.tests_rls apps.shared.tests_four_eyes --settings=config.test_settings --noinput`

**Invariants:**

- The review lowers nothing and fixes nothing; it reports.
- A finding is evidence, not opinion: each carries the code that proves it.

### c14-owasp-access: the access control and tenancy review

**Requirements:** NFR-04, NFR-01
**Scenarios:** none
**Depends on:** `c14-owasp-scope`, `c13-private-obligations`, `c13-private-sources`, `c14-billing-usage-b`, `c14-health-backend-b`, `c8-support-access-mechanism`, `c12-exit-deletion`

The area that holds the product's two zones. With evidence:

- **Row-level security.** Is every tenant table enabled, forced and policied? Does any policy allow a write outside the session's zone after `h-c-mixed-zones`? Is there any `SECURITY DEFINER` function, any foreign key that bypasses a policy, or any path where the API runs as `cw_migrator`?
- **The windows.** `identity_lookup`, `platform_counters`, and any other: does each open only for the principal it names, refuse while a tenant is active, clear on every path including an exception, and reach only the tables in its map? Can a third module call one? Does every console read through a window write its audit row?
- **Permissions.** Is every route gated? Does any 403 leak the existence of another bank's record instead of answering 404? Can a permission-filtered field become a page-level 403 or a silent empty page?
- **Four eyes.** Is every approve permission covered by a check constraint as well as by code? Can a requester approve through a batch route, a retry, or a second identity?
- **Support access.** Is the grant time-limited, read-only, revocable with immediate effect, and logged per request? Can a support session write, export, download evidence or spend the bank's AI budget?
- **Tenant exit.** Does the deletion reach every tenant table, and does the coverage guard of ruling 36 fail when a new one appears? Can one passkey erase a bank?
- **Billing and counters.** Can the console reach a bank's content through the new routes? Can a bank read another bank's plan, usage or job rows?

Run with it: `tests_rls`, `tests_tenant_isolation`, `tests_route_permissions`, `tests_four_eyes`, `tests_audit_on_write`.

**Owned paths:**

- `docs/security/OWASP_ACCESS_2026-09-20.md` (new)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- Every question is answered with evidence, and every window in the repository is listed with its tables, its callers and its guard.
- A cross-tenant read or write attempt is run as `cw_app` for each new table, and the result is in the report.
- Findings carry severity, files and a reproducing scenario.
- The five guard suites are green on `main`.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_rls apps.shared.tests_tenant_isolation apps.shared.tests_route_permissions apps.shared.tests_four_eyes apps.shared.tests_audit_on_write --settings=config.test_settings --noinput`

**Invariants:**

- The review reports; it changes nothing.
- Two zones, four eyes and the audit trail are the things it exists to check.

### c14-owasp-library-ai: the library door, the prompts and the AI log review

**Requirements:** NFR-04
**Scenarios:** none
**Depends on:** `c14-owasp-scope`, `c11-chunk-close`, `c7-chunk-close`, `c13-private-obligations`

- **The door.** Is every library write reachable only through an approved proposal, plus the re-verification stamp and the H6 confirmation kind? Has the `library_write()` allowlist grown, and does each entry still need to be there? Can an agent key, a tenant role or a seed write a library row directly?
- **Fetched content.** Is every fetched document screened for embedded instructions before it reaches a prompt (AGT-07)? Can a poisoned source steer a classification, a proposal or a So-what draft? Is a block or a challenge treated as a failed source check rather than as content?
- **Prompts and models.** Does any tenant text reach a model outside Ask and the tenant's own agents? Is the AI switch read where it must be and not where it must not (D-61: bleqq's agents ignore it)? Is every model call logged with its purpose, model, version and input reference? Can a prompt be changed from outside the repository?
- **The index.** Is `SearchChunk` derived data with its own fence and its own row-level security (D-51)? Is an owned row or a child of one ever indexed, embedded, reranked or sent to a model (D-57)? Does find-similar return shared rows only?
- **Standards.** Can licensed text enter the library through a proposal, a correction, an apply, a source document or a translation (D-35)?
- **Private records.** Who approves them, and can a platform reviewer read one?

Run with it: `tests_library_fence`, `tests_rls`, `tests_audit_on_write`, and the evaluation gate.

**Owned paths:**

- `docs/security/OWASP_LIBRARY_AI_2026-09-20.md` (new)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- The allowlist's entries are listed with the reason each is still needed, and any entry with no reason is a finding.
- A prompt-injection attempt is run against the screening function and the result is in the report.
- Every model-calling path is traced from its input to its log row.
- Findings carry severity, files and a reproducing scenario.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.shared.tests_library_fence apps.shared.tests_rls apps.shared.tests_audit_on_write --settings=config.test_settings --noinput`
- `python backend/scripts/search_eval.py`

**Invariants:**

- Proposals are the only door into the library.
- Fetched content is untrusted.
- AI output is labelled until a person confirms it.

### c14-owasp-files-data: the evidence, storage, import, export and retention review

**Requirements:** NFR-04
**Scenarios:** none
**Depends on:** `c14-owasp-scope`, `c12-close`

- **Uploads.** Is the type checked by content and not by name or extension? Is the size limit enforced before the bytes are written? Is every file scanned before it is readable, and what happens to one the scanner cannot reach? Can a file name, a path or an archive entry escape its directory?
- **Downloads.** Is every download permission-checked and audited (D-11, no presigned links)? Can an evidence id from another bank be read, and does it answer 404?
- **Imports.** Is a spreadsheet parsed without executing anything? Are formulas, links and huge sheets bounded? Does a bad row fail the row and not the file, and is nothing half-applied?
- **Exports.** Can an export contain another bank's row, a library row it should not, or a value that opens as a formula in a spreadsheet? Is the export job's output reachable only by its owner, and for how long?
- **Retention.** Does the purge delete only what D-53 allows, refuse a cutoff younger than a year, run as the owner with a pinned `search_path`, and write one run row and one audit row with counts only? Can it be aimed at another bank?
- **The case file.** Does it hold anything the reader may not read?

Run with it: `tests_rls`, `tests_tenant_isolation`, `tests_audit_on_write`, and the storage and scanner adapter tests.

**Owned paths:**

- `docs/security/OWASP_FILES_DATA_2026-09-20.md` (new)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- A malformed file, an archive with a traversal entry and a spreadsheet with a formula are each run against the real path, and the results are in the report.
- Every download route is listed with its permission check and its audit row.
- The purge is run against a seeded database with a too-young cutoff and the refusal is shown.
- Findings carry severity, files and a reproducing scenario.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.cases apps.reports apps.shared --settings=config.test_settings --noinput`

**Invariants:**

- Input from a user, an agent, the network or an external service is never an impossible case.
- Soft-deleted evidence stays soft-deleted until retention may remove it.

### c14-owasp-integrations-web: the outbound, header and frontend review

**Requirements:** NFR-04
**Scenarios:** none
**Depends on:** `c14-owasp-scope`, `c13-e2e-integrations`, `c13-tickets-jira`, `c13-fe-sso`

- **Outbound.** Can a webhook, SIEM or ticket destination be pointed at an internal address, a link-local address or a redirect chain that reaches one? Is the egress client the only way out, and is it used everywhere? Is the payload signed, and is the secret ever logged?
- **Deliveries.** Is a delivery idempotent, bounded in retries and size, and free of tenant content beyond what the bank asked to send? Can a failed delivery be replayed by hand, and should it be?
- **Headers and CORS.** Are the security headers set on every response? Is the allowed origin list exact? Is the cookie `HttpOnly`, `Secure` and `SameSite`?
- **The frontend.** Does anything render unescaped content? Does the access token ever reach storage the browser persists? Does the client branch on `code` rather than on `detail` everywhere? Does any screen log a tenant value?
- **The calendar feed.** Does the token stay out of the access log, Sentry and the referrer (D-52)? Is a revoked token indistinguishable from an unknown one, in body and in timing? Is the route rate-limited per token, and can it be enumerated?
- **Rate limits.** Is every unauthenticated and key route limited, and does a limit ever leak whether a record exists?

Run with it: the full E2E suite, `tests_route_permissions`, and the logging and Sentry scrub tests.

**Owned paths:**

- `docs/security/OWASP_INTEGRATIONS_WEB_2026-09-20.md` (new)
- `docs/plans/briefs/HARDENING.md` (its own rows only)

**Done when:**

- An internal-address destination and a redirect to one are each attempted against the real client and the results are in the report.
- Every outbound path is listed with the client it uses; one that does not use the egress client is a finding.
- The feed token is traced from the URL to every place a request line could be written.
- Findings carry severity, files and a reproducing scenario.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py test apps.integrations apps.shared --settings=config.test_settings --noinput`
- `cd frontend && npm run test:e2e`

**Invariants:**

- A secret never reaches a log.
- The review reports; it changes nothing.

### c14-owasp-fixes-auth: close the auth review's findings

**Requirements:** NFR-04
**Scenarios:** every auth-area scenario stays green
**Depends on:** `c14-owasp-auth`
**Security review:** yes (re-run over its own diff)

Fix every critical, high and medium finding of `c14-owasp-auth`, test first: write the test that reproduces the finding, watch it fail, then fix it. Re-run the review over this task's diff and repeat until nothing at medium or above remains. If the review found nothing at that level, close at once with a note in `HARDENING.md` and no code change.

Owned paths are the files the findings name and nothing else (rule 11). A finding whose file another running task owns waits for that task or becomes its own package. A finding that can be closed only by weakening an invariant in CLAUDE.md §5 is a stop-and-ask for Alex (rule 13), recorded in `TODO_FOR_alex.md`, not a quiet exception.

**Owned paths:**

- the files each finding names, declared at dispatch
- `docs/security/OWASP_AUTH_2026-09-20.md` (the re-run appended)
- `docs/plans/briefs/HARDENING.md`, `docs/TODO_FOR_alex.md` (own rows only)

**Done when:**

- No critical, high or medium finding is open, each closed by a test that failed before the fix.
- Every auth scenario that was green is still green, and no test was weakened, skipped or quarantined to get there.
- No route joined `UNGATED_BY_DESIGN` and no guard's allowlist grew without the review saying why.
- Findings below medium are `HARDENING.md` rows with a package named.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `cd frontend && npm run test:e2e -- --grep "@smoke|identity"`

**Invariants:**

- No passwords, ever; the emailed code works once and stops at the first passkey.
- A passkey step-up on every action playbook 4.2 lists.
- No gate lowered, no test skipped, no API mocked in E2E.

### c14-owasp-fixes-access: close the access review's findings

**Requirements:** NFR-04, NFR-01
**Scenarios:** every access-area scenario stays green
**Depends on:** `c14-owasp-access`
**Security review:** yes (re-run over its own diff)

As `c14-owasp-fixes-auth`, for the access area. A finding about a policy, a window or the tenant fence is fixed in the database as well as in code, and its test runs as `cw_app`, never as the table owner. A finding that a window reaches a table its map does not name is closed by narrowing the window, never by widening the map.

**Owned paths:**

- the files each finding names, declared at dispatch
- `docs/security/OWASP_ACCESS_2026-09-20.md` (the re-run appended)
- `docs/plans/briefs/HARDENING.md`, `docs/TODO_FOR_alex.md` (own rows only)

**Done when:**

- No critical, high or medium finding is open, each closed by a test that failed before the fix.
- Every isolation and four-eyes test is green and was run as `cw_app`.
- `migrate_from_zero` applies the whole graph after any policy change.
- No policy was dropped without its replacement in the same migration, and no bypass was added.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings`
- `./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Two zones, forced row-level security, no bypass for `cw_app`.
- Four eyes, enforced by a check constraint.
- `record()` on every write, in the same transaction.

### c14-owasp-fixes-library-ai: close the library and AI review's findings

**Requirements:** NFR-04
**Scenarios:** every library, proposal, watch, search and agent scenario stays green
**Depends on:** `c14-owasp-library-ai`
**Security review:** yes (re-run over its own diff)

As `c14-owasp-fixes-auth`, for the library and AI area. A finding about the fence is closed by removing a writer, never by allowlisting one; a finding about a prompt is closed in the versioned definition and its test, never by a runtime string; a finding about the index is closed without indexing an owned row.

**Owned paths:**

- the files each finding names, declared at dispatch
- `docs/security/OWASP_LIBRARY_AI_2026-09-20.md` (the re-run appended)
- `docs/plans/briefs/HARDENING.md`, `docs/TODO_FOR_alex.md` (own rows only)

**Done when:**

- No critical, high or medium finding is open, each closed by a test that failed before the fix.
- The `library_write()` allowlist is the same size or smaller than before the task.
- The evaluation gate is green and no tolerance was raised.
- Every AI-calling path still writes its log row.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `python backend/scripts/search_eval.py`

**Invariants:**

- Proposals are the only door into the library.
- Every model call is logged; fetched content is untrusted.
- A tolerance is never raised to make a gate pass.

### c14-owasp-fixes-files-data: close the files and data review's findings

**Requirements:** NFR-04
**Scenarios:** every evidence, import, export and retention scenario stays green
**Depends on:** `c14-owasp-files-data`
**Security review:** yes (re-run over its own diff)

As `c14-owasp-fixes-auth`, for the files and data area. A finding about a file is closed by refusing the file, never by accepting it with a warning; a finding about an export is closed without removing a column a bank needs; a finding about the purge is closed without widening what it may delete.

**Owned paths:**

- the files each finding names, declared at dispatch
- `docs/security/OWASP_FILES_DATA_2026-09-20.md` (the re-run appended)
- `docs/plans/briefs/HARDENING.md`, `docs/TODO_FOR_alex.md` (own rows only)

**Done when:**

- No critical, high or medium finding is open, each closed by a test that failed before the fix.
- A refused upload leaves nothing behind, proved after each fix.
- The purge still refuses a cutoff younger than a year and still writes counts only.
- Every download is still permission-checked and audited.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Validation at a trust boundary is never simplified away.
- Nothing overwritten: soft-deleted evidence stays until retention may take it.

### c14-owasp-fixes-integrations-web: close the integrations and web review's findings

**Requirements:** NFR-04
**Scenarios:** every integration, feed and frontend scenario stays green
**Depends on:** `c14-owasp-integrations-web`
**Security review:** yes (re-run over its own diff)

As `c14-owasp-fixes-auth`, for the integrations and web area. A finding about an outbound destination is closed in the egress client, so every caller gets the fix; a finding about a header is closed in the middleware, not per view; a finding about the frontend is closed with a unit test and, where a journey can see it, a journey assertion.

**Owned paths:**

- the files each finding names, declared at dispatch
- `docs/security/OWASP_INTEGRATIONS_WEB_2026-09-20.md` (the re-run appended)
- `docs/plans/briefs/HARDENING.md`, `docs/TODO_FOR_alex.md` (own rows only)

**Done when:**

- No critical, high or medium finding is open, each closed by a test that failed before the fix.
- Every outbound path goes through the egress client, proved by a guard test.
- The feed token appears in no log line, breadcrumb or referrer after the fixes.
- The full E2E suite is green.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput && ./run.sh run coverage report && ./run.sh run python scripts/coverage_gate.py`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`
- `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run build && npm run test:e2e`

**Invariants:**

- A secret never reaches a log.
- The client branches on `code`, never on `detail`.
- No API is mocked in E2E.

### c14-owasp-converge: the findings have converged

**Requirements:** NFR-04
**Scenarios:** none
**Depends on:** `c14-owasp-fixes-auth`, `c14-owasp-fixes-access`, `c14-owasp-fixes-library-ai`, `c14-owasp-fixes-files-data`, `c14-owasp-fixes-integrations-web`

Build_Plan's chunk 14 is "OWASP review until findings converge". This task decides whether they have.

A review sub-agent re-runs each area's question list over `main` as it now stands, in one pass, and counts: how many findings each area raised, how many its fix package closed, how many the fixes themselves introduced, and how many remain open at each severity. Converged means **no critical, high or medium finding is open in any area, and the last round introduced none**. If the last round introduced one, that area's fix package runs again and this task repeats; the report records each round, so a loop that is not closing is visible rather than felt.

Write `docs/security/OWASP_CONVERGENCE_2026-09-20.md` with the per-round table, the open low findings with the package named for each, and the statement — with the command output — that the guard suites, the compliance lint and the full E2E suite are green on `main`.

**Owned paths:**

- `docs/security/OWASP_CONVERGENCE_2026-09-20.md` (new)
- `docs/plans/briefs/HARDENING.md`, `docs/TODO_FOR_alex.md` (own rows only)

**Done when:**

- The table shows a round in which no area raised a new finding at medium or above.
- Every open finding is low and has a package named.
- The five area reports are each marked closed with their round count.
- `TODO_FOR_alex.md` carries the two rows playbook 18 asks for and this review cannot supply: an independent penetration test, and a certification path (ISO 27001 or SOC 2), each with what the review already covers and what it does not.
- The guard suites, `prepush.sh --quick` and the full E2E suite are green on `main`, with the output in the report.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `bash scripts/prepush.sh --quick`
- `cd frontend && npm run test:e2e`

**Invariants:**

- Convergence is measured, not declared.
- The review changes nothing; a new finding goes back to its fix package.

### c14-perf-search-home: search, Ask and the home surfaces

**Requirements:** NFR-02
**Scenarios:** none (NFR-S6 is `c14-shared-scenarios`', NFR-S7 is `c14-perf-screens`')
**Depends on:** `c14-perf-harness-a`, `c6-chunk-close`, `c7-chunk-close`, `c8-close-out`

Add every route of search, Ask, Today, the briefing, the roadmap, the upcoming list and the calendar feed to `backend/perf/routes.py` with its principal, its fixture and its budget, and run the report against a database seeded to a realistic size (the seed's own data plus a bulk fixture: the library at a few thousand obligations, a year of changes, a full roadmap).

Budgets: 250 ms server time for an endpoint, 800 ms for hybrid search, 1.5 s with the reranker, 2 s to Ask's first token. Fix what exceeds, inside the pass: a missing index, an N+1, a count that scans, a fan-out that became a chain. A fix that needs a schema change or a design change is recorded as a finding with a proposed patch and named for its chunk instead of widening the pass (section 1.4).

Record the baseline with `--record` in the same commit as the fixes, so the next pass compares against a measured number.

**Owned paths:**

- `backend/perf/routes.py` (its own rows only), `backend/perf/baseline.json` (its own entries only)
- `backend/perf/fixtures_bulk.py` (new, shared by the later passes)
- the query modules each fix names, declared at dispatch
- `docs/plans/Verification_Log.md` (its own rows only)

**Done when:**

- Every route in the area is in the list with a measured number and its budget.
- No route exceeds its budget, or exceeds it with a recorded finding naming the chunk that owns the change.
- Hybrid search meets 800 ms and Ask's first token 2 s on the bulk fixture.
- Each fix has a query-count or timing test that fails without it.
- The baseline is recorded and `perf_report.py` exits 0.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python scripts/perf_report.py`
- `./run.sh run coverage run manage.py test apps.search apps.home --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Fan out, never chain. Paginate: default 20, max 100.
- Measure against the real database; nothing is mocked to make a number look good.
- A budget is never raised to make a route pass.

### c14-perf-register-cases: the register and the case workflow

**Requirements:** NFR-02
**Scenarios:** none
**Depends on:** `c14-perf-harness-a`, `c8-close-out`, `c9-close`, `c14-perf-search-home` (which creates the bulk fixture)

The same pass over the register and the cases: applicability and its batch decision, compliance status per entity, gaps, history and interpretations, internal links, My work, the case list and detail, triage, assessment, actions, evidence listing, sign-off and the case file.

The bulk fixture grows for this area: an entity tree, a register with tens of thousands of rows, a year of cases with actions and evidence. The batch decision route is measured at `REGISTER_BULK_MAX` requests in one call, which is the size D-44 caps it at and therefore the size it must meet its budget at.

**Owned paths:**

- `backend/perf/routes.py`, `backend/perf/baseline.json`, `backend/perf/fixtures_bulk.py` (own entries only)
- the query modules each fix names, declared at dispatch

**Done when:**

- Every register and case route is measured against its budget, including the batch decision at its cap.
- No route exceeds its budget without a recorded finding naming its chunk.
- Each fix has a test that fails without it.
- The baseline is recorded and the report exits 0.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python scripts/perf_report.py`
- `./run.sh run coverage run manage.py test apps.register apps.cases --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- A cap exists so a call stays inside its budget; measure at the cap.
- No N+1 survives the pass without a test that would catch its return.

### c14-perf-core: identity, tenancy, taxonomy and the console

**Requirements:** NFR-02
**Scenarios:** none
**Depends on:** `c14-perf-harness-a`, `c4-close-b`, `c11-chunk-close`, `c13-close`, `c14-perf-search-home`

The same pass over sign-in, `GET /me` with its counts, sessions, members, roles, the organisation, the footprint and its preview, the vocabularies, the proposal queue, the tenants list, agent definitions and tenant agents. The footprint preview and `GET /me`'s counts are the two that grow with the bank, so both are measured on the bulk fixture and both get a query-count pin.

**Owned paths:**

- `backend/perf/routes.py`, `backend/perf/baseline.json`, `backend/perf/fixtures_bulk.py` (own entries only)
- the query modules each fix names, declared at dispatch

**Done when:**

- Every route in the area is measured against its budget.
- `GET /me`'s counts and the footprint preview are each one query per count, pinned.
- No route exceeds its budget without a recorded finding naming its chunk.
- The baseline is recorded and the report exits 0.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python scripts/perf_report.py`
- `./run.sh run coverage run manage.py test apps.identity apps.tenants apps.taxonomy apps.proposals --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Every count is permission-filtered before it is counted; a faster count that leaks is not a fix.
- Measure against the real database.

### c14-perf-library-watch: the library, the inventory and the watch feed

**Requirements:** NFR-02
**Scenarios:** none
**Depends on:** `c14-perf-harness-a`, `c3-close`, `c5-chunk-close`, `c13-close`, `c14-perf-search-home`

The same pass over instruments, obligations with their versions, "as of", the diff, translations, provenance, the obligations count, the watch feed with its twelve filters, a change and its timeline, source coverage and library updates. H9's anti-join is re-measured here at the bulk library's size, because it was fixed before the library could grow and this is the first pass that grows it.

**Owned paths:**

- `backend/perf/routes.py`, `backend/perf/baseline.json`, `backend/perf/fixtures_bulk.py` (own entries only)
- the query modules each fix names, declared at dispatch

**Done when:**

- Every library, inventory and watch route is measured against its budget on the bulk library.
- The obligations count and the feed's filters are each one query, pinned.
- The diff stays inside its budget at `LIBRARY_TEXT_MAX_CHARS`, which H12 introduced.
- No route exceeds its budget without a recorded finding naming its chunk.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python scripts/perf_report.py`
- `./run.sh run coverage run manage.py test apps.library apps.watch --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- The scope rule is applied in the query, not after it.
- A cost that grows with the library and not with the page is a finding, not a number.

### c14-perf-rest: collaboration, reports, integrations, billing and health

**Requirements:** NFR-02
**Scenarios:** none
**Depends on:** `c14-perf-harness-a`, `c10-close`, `c11-chunk-close`, `c12-close`, `c14-billing-usage-b`, `c14-health-backend-b`, `c14-perf-search-home`

The last API pass: comments, mentions, notifications, the digest, the dashboard, the committee pack, export and import job status, webhook and SIEM configuration, saved searches, attestations, the two usage reads, console health and the failed-jobs list. The two console reads are measured with ten banks seeded, because they are the only reads that scale with the number of banks rather than with one bank's data.

When this pass ends, `backend/perf/routes.py` holds every route in `openapi.json`; the task proves it by comparing the two lists and failing on any operation with no row.

**Owned paths:**

- `backend/perf/routes.py`, `backend/perf/baseline.json`, `backend/perf/fixtures_bulk.py` (own entries only)
- `backend/perf/tests_coverage.py` (new: every operation has a row)
- the query modules each fix names, declared at dispatch

**Done when:**

- Every remaining route is measured against its budget.
- Console health and console usage each stay inside the budget with ten banks, and each is one query, not one per bank.
- Every operation in `openapi.json` has a row in `routes.py`, proved by the new test.
- No route exceeds its budget without a recorded finding naming its chunk.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `cd backend && ./run.sh run python scripts/perf_report.py`
- `./run.sh run coverage run manage.py test apps.collab apps.reports apps.integrations apps.billing apps.governance perf --settings=config.test_settings --noinput`
- `./run.sh run ruff check . && ./run.sh run mypy`
- `python backend/scripts/compliance_check.py --all && python backend/scripts/requirements_coverage.py`

**Invariants:**

- Every endpoint is measured; none is exempt because it is new.
- Exports, imports and agent runs are jobs with a status endpoint, and the status endpoint has its own budget.

### c14-perf-screens: every screen reaches real data within its budget

**Requirements:** NFR-02, NFR-03
**Scenarios:** NFR-S7 (`@e2e`, un-fixmed)
**Depends on:** `c14-perf-core`, `c14-perf-library-watch`, `c14-perf-register-cases`, `c14-perf-search-home`, `c14-perf-rest`, `c13-i18n-wiring`, `c14-fe-health-b`, `c14-fe-usage-b`, `c14-fe-console-plans-b`

Walk every registered destination in `frontend/src/shared/navigation/registry.ts` with `measureScreen` from `c14-perf-harness-b`, against a production Next build and the seeded backend, and assert real data — not a skeleton — within 500 ms of navigation. Record each measurement beside its screen in `docs/plans/UI_Implementation_Plan.md`, which NFR-S7's Gherkin asks for.

Fix what exceeds, on the client side only: a query that waits for another, a fetch that could have been in the first render, a screen that renders after a font. A screen that exceeds because its endpoint does is a finding for the API pass that owns it, not a client change here. The navigation registry is the list, so a destination added later is measured automatically and a new screen cannot escape the sweep.

Un-fixme NFR-S7 in `shared.journey.spec.ts`.

**Owned paths:**

- `frontend/tests/e2e/performance.journey.spec.ts` (new)
- `frontend/tests/e2e/shared.journey.spec.ts` (the NFR-S7 block only)
- `backend/apps/shared/app.md` (NFR-S7's note only)
- `docs/plans/UI_Implementation_Plan.md` (the measurement column, one row per screen)
- the client modules each fix names, declared at dispatch

**Done when:**

- Every destination in the registry is measured and inside 500 ms, or over it with a recorded finding naming the API route and its pass.
- The measurement is against `next start`; a run against `next dev` fails.
- Each measurement is in the UI plan beside its screen.
- NFR-S7 is green, and green twice in a row from a fresh seed.
- No screen was made fast by removing data it is supposed to show.

**Gates:**

- `cd frontend && npm run build && npm run test:e2e -- --grep "NFR-S7"`
- `npm run lint && npm run typecheck && npm run test:coverage`

**Invariants:**

- A skeleton is not real data.
- Measure against `next start`, never `next dev`.
- No API is mocked to make a screen fast.

### c14-close: the chunk closes, and the build's last chunk with it

**Requirements:** NFR-02, NFR-04, NFR-05
**Scenarios:** every chunk 14 scenario green; every scenario in the repository un-skipped or with its chunk named
**Depends on:** `c14-owasp-converge`, `c14-perf-screens`, `c14-e2e-billing`, `c14-e2e-health`, `c14-assurance-locations-b`, `c14-assurance-continuity-b`, `c14-assurance-exit-controls-b`, `c14-runbooks`, `c14-eu-data-location-b`, `c14-shared-scenarios`, `c14-billing-limits-b`, `c14-eval-runs`, `c14-fe-eval-run` (the two that clear `startEvalRun`'s pending line this close proves gone)

Close the chunk on `main` (playbook Section 3):

- Run `bash scripts/prepush.sh --all` and the full `npm run test:e2e`.
- Prove that exactly one chunk 14 route still answers 501 — `retryConsoleJob`, waiting for `q-retry-write` (section 4) — and that the other ten of the eleven operations are served, and that no chunk 14 journey is fixme, by enumerating the seven journeys chunk 14 owns (NFR-S7, NFR-S8, NFR-S9, NFR-S17, NFR-S19, ADM-S4, ADM-S5) and ADM-S6's plans block.
- Prove `backend/scripts/contract_drift_pending.txt` holds no chunk 14 line but the retry route's, which carries `q-retry-write` as its reason.
- Prove that every scenario in every `app.md` is un-skipped, or skipped with a chunk named, and that the only ones left are the deliberate deferrals this brief names.
- Prove `docs/assurance/` holds its README and the six documents, and that each names its unverified facts rather than leaving them out.
- Check that CLAUDE.md §5 carries the two exception lines Alex approved (retention deleting ledger rows, D-53; tenant exit deleting everything, D-56). They are chunk 12's to write; if either is missing, the close names chunk 12 and the row stays open rather than being written here.
- Prove `docs/plans/briefs/HARDENING.md` has no open row: every H item is closed by a commit or has a package named, and section 8 of `PARALLEL_PLAN.md` carries a row for H11 to H15 and for H6 (ruling 2).
- Add the chunk 14 coverage floors to `backend/scripts/coverage_gate.py`, measured at this close, each with its measured value, statement count and date.
- Update the status cells: `billing/app.md` NFR-05 `built`; `governance/app.md` ADM-02 `in_progress` with ADM-S5's and ADM-S7's retry lines naming `q-retry-write`, and `built` only once that route is served; `shared/app.md` NFR-02 and NFR-04 `built`. `verified` waits for a person on a running server, as every chunk's does.
- Update `docs/plans/IMPLEMENTATION_STATUS.md`: chunk 14 implemented and tested with today's date, `in progress` until a person verifies it, and a notes cell naming what was cut and why (section 1.5).
- Update `docs/plans/UI_Implementation_Plan.md`'s chunk 14 rows from `designed` to `built`, with the measurement `c14-perf-screens` recorded.
- Write the open points into `docs/TODO_FOR_alex.md`: `q-retry-write`, still open since the main agent put it to Alex on 2026-09-20, with the route it holds at 501 and the two scenario lines it holds back, and the seven non-blocking rows of section 4.
- Add the `Verification_Log.md` rows for any provider fact the chunk relied on that is not already there.
- Update `PARALLEL_PLAN.md` 7.1: mark `q-eu-guards` and `q-platform-counters` answered, with their ADRs, so the next reader does not re-ask them (ruling 1).

**Owned paths:**

- `backend/apps/billing/app.md`, `backend/apps/governance/app.md`, `backend/apps/shared/app.md` (status cells and notes only)
- `docs/plans/IMPLEMENTATION_STATUS.md`
- `docs/plans/UI_Implementation_Plan.md` (the chunk 14 rows only)
- `docs/plans/PARALLEL_PLAN.md` (the 7.1 rows and the section 8 rows only)
- `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`, `docs/plans/briefs/HARDENING.md` (own rows only)
- `backend/scripts/coverage_gate.py` (the chunk 14 floors only)

**Done when:**

- `bash scripts/prepush.sh --all` is green on the close commit.
- The full E2E suite is green against the real stack, `@smoke` included.
- No chunk 14 route answers 501 but `retryConsoleJob`, which names `q-retry-write`; no chunk 14 journey is fixme; and no chunk 14 line is left in `contract_drift_pending.txt` but that route's, `startEvalRun`'s included.
- No `HARDENING.md` row is open without a package or a commit.
- `docs/assurance/` is complete, and CLAUDE.md §5's two exception lines are present or named as chunk 12's.
- The requirements-coverage gate is green and every remaining skipped scenario names its chunk.
- The status files, the UI plan rows and the three app.md files say what is on `main`, not what was intended.
- The coverage floors are raised to the measured values and none is lowered.

**Gates:**

- `set -a; . ./.env.worktree; set +a`
- `bash scripts/prepush.sh --all`
- `cd frontend && npm run test:e2e`
- `python backend/scripts/requirements_coverage.py`

**Invariants:**

- Status is the truth of `git log`, not intention: a row moves only when its commit is on `main`.
- No gate lowered to close a chunk; a cut is named, never hidden.
- The owner deploys; an agent never does.
