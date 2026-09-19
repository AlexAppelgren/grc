# Parallel build plan: chunks 3 to 14

Written 2026-09-19 by the planning workflow. Revised the same day after a review that sent 35 corrections (section 9 lists the parts not taken). The plan changes only the order of work and where each piece runs. No requirement, invariant or gate is lowered. The review found some pieces missing, and the plan now adds them: a fix package after every security review, an R1 performance check, owners for console surfaces nobody had picked up, and a stronger gate at each merge.

It covers 453 work packages. 8 are done, 7 are built and waiting for review or merge, 2 are running, and 436 are still to start. That is about 356 agent-hours of package work, plus about 240 agent-hours of review. The packages are:
- the package maps for chunks 5 to 14;
- the rest of chunk 3 and all of chunk 4, from `docs/plans/briefs/CHUNK3_TASKS.md` and `CHUNK4_TASKS.md`, renamed `c3-` and `c4-` (their files, gates and done-conditions stay as written there);
- the PRD 0.3 tasks, from `docs/plans/briefs/FEATURES_0_3_TASKS.md` on the p03 branch, as `f03-T01` to `f03-T83`. They replace the old `rs-` Regulatory scope tasks;
- the hardening follow-ups of `HARDENING.md` (`h10-`, `h-a-`, `h9-`);
- one frontend split (`x-frontend-split`), one CI change (`ci-e2e-shards`), an R1 performance check (`r1-perf`) and the R1 readiness check (`r1-readiness`).

In short:
- **R1 (chunks 3 to 7 with their PRD 0.3 tasks)** is ready for Alex's first test deploy about 28 hours after the start. That is the median of 10 seeded runs, which ranged from 27.5 to 28.7 hours. With a rework margin it is about 33 hours. The dependency chains alone take 21.4 hours.
- **Everything (chunks 3 to 14)** closes after about 66 hours (range 64 to 68), or about 79 hours with the margin. The chains alone take 50 hours.
- **Run chunk by chunk**, the same packages take about 78 hours to R1 and 203 hours in all.
- The first version of this plan said 19 and 40 hours. Four things moved those numbers:
  - PRD 0.3 added 77 packages, about 59 hours of work.
  - Security reviews take 45 minutes, not 15.
  - Each merge now runs the touched apps' tests.
  - Every security review gets a fix package.
- Five things set the pace:
  - **Two chains.** R1 waits on chunk 3's library reads feeding Today and the briefing. Everything waits on the PRD 0.3 My work chain through chunks 8 to 10.
  - **Merge slots.** Two are needed. With one, R1 slips 13 hours and everything 33.
  - **Cloud sessions for R2 and R3.** With none, everything takes 95 hours.
  - **Alex's answers in section 7.** Answers by hour 6 cost nothing. By hour 12 they cost about 2 hours, by hour 24 about 13.
  - **The usage allowance.** About 660 agent-hours with the orchestrator.

Dispatch is by readiness, not by wave number. A package starts once everything it depends on is merged (shipped, for a cloud package), its keys are free and a slot is free. The waves in section 4 show the simulated order. Packages already running when this plan lands keep their slot and their files.

## 0. State at the start (2026-09-19, evening)

**On main, not dispatched again:**
- c3-seed-j6 (d5fe0b0), c3-fe-presentation (4b214e1), c4-audit-read (cfc3bf4), c4-rejection-reasons (010c68c) and c4-door-proof (68ac917);
- c5-cards-console (E2, 5358b36);
- c5-content-screen (E1, 1d4629e). It is on local main but not yet on `origin/main`, which is at d66f2b1, so the next ship carries it.
- rs-t15 is done. `foundations.md` has "Restricted setting", `pills-and-labels.md` has "Added when approved", `TODO_FOR_alex.md` has the Regulatory scope items, and `Verification_Log.md` has the FI and Green rows.
- REGULATORY_SCOPE T11 to T14, which are f03-T11 to f03-T14, are on main (a9cd51b, b5ad16f, b978fe5).

**Being merged:** c4-console-shell (`wt/c4-t5-console-shell`, 018da7c). Its squash is staged in the main checkout.

**Built, waiting for review:**
- c3-append-only: `wt/c3-t1-append-only` (218291b).
- c3-no-tone: `wt/c3-t3-nfr-s10`. The branch has c26f299 and a second commit, ca76a03 (a proposal is checked like a vocabulary write when it is made). The review reads both.
- c3-obligations-read: `wt/c3-t4-obligations-read` (01d520e). It merges only after h10-log-no-query (section 8).
- c5-llm-anthropic-provider (E3): `origin/claude/e3-anthropic-adapter-xppg99` (23381a3). It already adds `stream()`, so c7-llm-streaming-adapter is deleted.
- c7-embedder-mock-reranker (E4): `origin/claude/e4-embedder-reranker-xfbzsr` (ab256a9). Confirm with `RemoteTrigger list_runs` that its run has ended before reviewing, and do not dispatch E4 again. It adds `RERANKER_PROVIDER` to the production boot guard, which its brief allowed; the review treats that as a guard change.
- c5-contract-models-agents (E5): `origin/claude/e5-agent-models-57ikse` (9cff224). Its diff goes beyond its brief:
  - `taxonomy/http.py` (`actor_for`);
  - `agents/seeds/` added to `LIBRARY_WRITE_ALLOWED_DIRS` in `tests_library_fence.py`, which is a fence change (rule 8);
  - its own YAML-subset reader, which ruling 19 now accepts.
- p03-consolidation: `origin/claude/prd-0-3-fvrh1l` (260179b). It goes back for one change before merging (ruling 26), then merges before anything else that touches its files. It is based on fc8da9c, and f03-T02 merges after it.

**Running:**
- h10-log-no-query (`wt/log-no-query`);
- f03-T02, the old rs-t02 (`wt/scope-t02-one-decision`, uncommitted, taxonomy migration 0003). Before it merges, it un-skips the `test_fp_s6` stub that p03 adds, instead of adding a second one.
- f03-T01: `HARDENING.md` H5 says it is in progress in the cloud, but no branch has reached origin. Check `RemoteTrigger list_runs` before dispatching it, so it is not built twice.

**Housekeeping for the main agent:**
- Remove the worktree `agent-aef88127e88cb8e49` (28d820a, superseded by 18a935b; it is locked, so unlock it first).
- Remove `intelligent-pike-51fc42` (da0a5e7, already contained in main).
- `agent-a1267c5dd58671ae5` (c50acfe, locked) holds the first attempt at F29. e604de7 on main is the fix, and the two differ in 10 files. Compare them before removing it.

## 1. The rule

### 1.1 What may run in parallel

1. **Owned paths.** Two packages run at the same time only when their owned paths are disjoint and they share no serialization key (section 3.4). Before dispatch, the main agent also compares the package's owned paths, or for a built branch its diff, with those of every running package. An overlap outside the append ledgers blocks the dispatch, whatever the key table says.
2. **Contracts land first.** A chunk's models and migrations, its routes and schemas, the regenerated types and its scenario stubs are separate early packages.
   - A contract package writes `api.py` and `schemas.py` once. It sends each operation to a named function in the module of the logic package that will build it, for example `cases/assessment.py`, and that function answers `not_built`.
   - A logic package owns only its module and its tests, never the app's `api.py`.
   - A logic package that finds the contract wrong stops and reports. A small contract package holding the app's API key fixes the contract.
3. **Stubs.** A route whose logic has not landed answers 501 `not_built` behind its real permission gate. Its mutating operation ids are named in the skipped scenario.
   - **No screen calls a stub.** A screen package depends on every backend package whose routes it calls.
   - Each chunk close proves no 501 is left, and so does `r1-readiness` for R1.
4. **Scenario stubs.** One package per chunk writes the scenario stubs, which stay `@skip("pending: <ID>")` or `test.fixme()`. The package that builds a scenario deletes only its own skip line. A pending skip is not a quarantine.
5. **Shared files come in three classes.**
   - **Owned files**, the default: one running package at a time. The serialization keys name the busy ones.
   - **Append ledgers**: several running packages may add to them. Each adds only its own rows, entries, test blocks, test classes or settings banner, and never edits, moves or deletes another's lines. The later merge takes the union inside its own worktree and reruns its gates. The list:
     - `docs/inputs/INPUT_DELTAS.md`, `backend/scripts/contract_drift_pending.txt`, `docs/TODO_FOR_alex.md`, `docs/plans/Verification_Log.md`, `docs/plans/briefs/HARDENING.md`, and the ledger rows and status cells of `docs/plans/UI_Implementation_Plan.md`;
     - `backend/.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`, `.gitleaks.toml` allowlist entries, new settings banners in `backend/config/settings.py`, router mounts in `backend/config/api.py`;
     - `backend/apps/shared/kinds.py`, `factories.py` and `routes.py`, the route lists in `permissions.py` (never its decorators or descriptions), and the guarded-table lists in `tests_rls.py`, `tests_four_eyes.py` and `tests_seed_integrity.py`;
     - the tenant-exit exception list of `c12-exit-export` and `c12-exit-deletion` (ruling 36);
     - `backend/apps/shared/e2e_seed.py`, `e2e_logins.py` and `e2e_passkeys.py`, and `frontend/tests/e2e/support/passkeys.ts` (the LOGINS map): one seed call or one login per package;
     - `frontend/src/shared/navigation/registry.ts` entries and `frontend/src/features/shared/tone-by-kind.ts` entries;
     - each app's `app.md` status cells and `tests_scenarios.py` skip lines;
     - each `frontend/tests/e2e/*.journey.spec.ts`, where a package edits only its own scenarios' test blocks;
     - other shared test modules (`tests_vocabulary.py`, `tests_matching.py` and the like): new test classes only.

     Adding a table to a guarded-table list is an append. Adding an entry to an **allowlist** loosens a guard, so it is a guard change under rule 8, not an append. The allowlists are the fence allowlist and its allowed directories, and `UNGATED_BY_DESIGN`.
   - **Generated files.** No package commits them. The main agent regenerates them after each merge that needs it, in the same commit:
     - `openapi.json`, `frontend/src/types/api.generated.ts` and `frontend/tests/e2e/support/e2e-passkeys.generated.ts`, when a route, schema or seed login changed;
     - the navigation and pill-gallery snapshot baselines (win32 and linux), when `registry.ts` or `tone-by-kind.ts` changed, reviewed image by image. A cloud session cannot produce the win32 baseline.
6. **The frontend split comes before the frontend fans out.**
   - `x-frontend-split` waits for c4-console-shell, which edits both catalogs. It moves `frontend/src/messages/en.json` and `sv.json` into one en and sv file pair per feature namespace, and teaches `check:messages` and `check:copy-drift` to read the directory.
   - After the split, each namespace pair belongs to the key of the feature that owns it (section 3.4).
   - Before the split, any catalog edit holds `cat`.
7. **Migrations.** One package per app's migration directory at a time, under the key `mig:<app>`. The later package renumbers after the earlier one merges.
8. **Guards.** A guard changes only in the package named for it, and only after a security review. The named changes:
   - **Library fence allowlist:** E5 (`agents/seeds/`, found in its diff), then `c5-contract-models-watch`, then `c7-search-index`.
   - **`authentication.py`, `tenancy.py`, `middleware.py` (key `auth`):** E5 (the agent on the principal), `c4-report-window`, `c8-support-access-mechanism`, `c12-tenant-deleted-status`, `c13-ip-allowlist` and `c14-job-runs`.
   - **The production boot guard (key `bootguard`):** E4 and `c14-eu-data-location`.
   - **`UNGATED_BY_DESIGN`:** `c3-obligations-read` and `f03-T52`.
   - **The requirements-coverage gate:** p03.
9. **The 60-minute limit.** A package that grows past 60 minutes stops at a green point. The rest becomes a new package; its scope does not stretch.
10. **R1 comes first.** An R2 or R3 package does not take a key that an R1 package needs once that R1 package's dependencies have all started. When merge slots are contended, a reviewed package that others wait on merges first.
11. **Later-release changes to security-critical code wait for R1.**
    - These R2 and R3 packages wait for `r1-readiness`:
      - every one that changes authentication or sessions (`auth`, `idp`), the production boot guard or a dependency;
      - `c11-batch-proposals-contract` and `c13-private-contract`, which change the proposal door.
    - `c9-case-contract` waits for `c5-chunk-close`, because it changes the cases and watch API that chunk 5's journeys test.
    - Any other R2 change to `prop`, `apply` or the fence before `r1-readiness`, today only `adm-lang-jur-kinds`, is additive only (a new kind, route or file), and its security review confirms that.
12. **Cloud sessions stop on invariant questions.** In the commit that adds this plan, the main agent amends cloud rule 3 in `WORKTREES.md`: a cloud session takes the documented default except on a question that touches an invariant, where it stops, commits nothing further and reports the question.
    - Packages that change a guard or row-level security carry that instruction explicitly: `c8-support-access-mechanism`, `c12-tenant-deleted-status`, `c13-ip-allowlist`, `c13-private-*` and `c14-eu-data-location`.
    - The two on the R1 path, `c7-search-index` and `c4-report-window`, run locally.

### 1.2 What never changes

- **Tests first, in every package.** The failing test comes first, then the code, then green. A package that cannot write its test first stops and reports.
- **E2E journeys run against the real stack.** That means a production Next build and the real backend on a freshly seeded database. Sign-in is by passkey through the UI with the virtual authenticator. `test` is imported from `support/api-guard`, and expected errors are declared where they happen. Tokens and cookies are never injected, and no API response is mocked. The main agent pastes CLAUDE.md section 11 in full into every package prompt that touches UI or journeys.
- **Security review.**
  - Before merge, a security-review sub-agent reads `git diff main...<branch>` for every package marked `yes` in the SR column. The guard suites run with it: `tests_rls`, `tests_tenant_isolation`, `tests_library_fence`, `tests_route_permissions`, `tests_audit_on_write` and `tests_four_eyes`. That covers auth, tenancy and RLS, the library fence, audit, four eyes, step-up, API keys, outbound calls, secrets and fetched content.
  - Every chunk has its own review: chunks 6, 7 and 11 now have one too, as does the R1 work of PRD 0.3 (`f03-security-review`). Each review is followed by a fix package (`*-review-fixes`). The fix package fixes the findings, reruns the review on its diff and repeats until nothing critical, high or medium remains. When a review finds nothing at medium or above, its fix package closes at once with a note.
  - A critical or high finding blocks the merge. A finding that does not block becomes a row in `HARDENING.md` and a package.
- **Every model call goes through one wrapper that logs it, from chunk 5 on.** `c5-ai-log-contract` builds the wrapper and a guard test that fails on any other call to the LLM adapter.
- **The full gate set runs before every push to main** (section 6).
- **No gate is ever lowered.** No test is skipped or quarantined, and no API is mocked in E2E. Coverage floors only ratchet up.
- **R1 deploy readiness.** `r1-readiness` runs on main after every other R1 package. It:
  - records the exact commit Alex deploys, so later merges do not change what is deployed;
  - runs `bash scripts/prepush.sh --all` and the full `npm run test:e2e` on that commit;
  - proves that no R1 route answers 501 and no R1 journey is fixme;
  - checks per scenario: every scenario that references an R1 requirement is un-skipped and green. It does not check that every status cell reads built, because NFR-02, I18N-02, ADM-01 and ADM-02 span releases; for those it lists the R1 part;
  - confirms `r1-perf` is green: endpoints under 250 ms, search under 800 ms, Ask's first token under 2 s and screens under 500 ms, measured against `next start`;
  - includes AUD-03 through `c4-close-b`. If q-Q1 is late, AUD-03 is named open, and Alex decides whether R1 deploys without it;
  - checks `RAILWAY_VARIABLES.md` and `FIRST_RUN_SETUP.md` against the settings, and lists the first-deploy items of `docs/TODO_FOR_alex.md`.

  Then Alex deploys. An agent never does.
- **Invariant questions go to Alex.** A question that touches an invariant stops its package until Alex answers (section 7). Every other open point takes the documented default, and the commit body says so.
- **Simplicity.** A package builds what its requirement asks, not what a later package might want. Where two maps planned the same thing, section 3.2 keeps one.

## 2. Lanes

The laptop has 8 logical CPUs and 15.6 GB of RAM. Docker's VM takes 3.5 GB. An E2E stack needs about 2.5 GB: gunicorn, a Celery worker, `next start` after a production build, and Chromium. Three E2E stacks and three unit packages would leave too little for the merge gates and the orchestrator. The **memory rule** is therefore at most 3 E2E stacks and 3 unit packages, and never more than 2 × E2E + unit = 7. That allows three E2E stacks with one unit package, or two with three. The two merge slots come on top. In the simulation, the rule costs about half an hour on R1.

| Lane | At once | What runs there | Packages (simulated placement) |
|---|---|---|---|
| local-e2e | 3 (memory rule) | Journey packages on or near the critical path, and every chunk close | about 104 |
| local-unit | 3 (memory rule) | Packages without journeys that are on the critical path, change a dependency, change CI, change a guard on the R1 path, or need a secret | about 189, of which 3 wait for a key |
| cloud | 6 (to confirm) | Unit packages whose dependencies are already on `origin/main` | about 138 |
| cloud+e2e | counted in the 6 | Journey packages off the critical path | about 9 |
| merge slots | 2 | The main agent's gate runs: one on main and one on a stacked tree (section 6) | every merge |

A package is **cloud-eligible** when all of these hold:
- everything it depends on is on `origin/main`, because a cloud session clones GitHub, not the laptop;
- it changes no dependency (key `deps`) and no CI workflow (key `ci`), because a cloud session's GitHub app may not be allowed to push workflow files;
- it needs no secret, paid live call, sandbox account or local-only tool;
- it is not a chunk close, a review, `r1-readiness` or other work of the main agent;
- if it changes a guard or row-level security, it carries the stop-and-report instruction (rule 12).

The table in section 3 marks eligible packages that the plan still places locally with `(c)`. Critical-path packages stay local even when eligible, because merged work reaches `origin/main` only with the next green ship. Any package placed in `cloud` may also run locally when a local slot is free.

The cloud facts come from the probe of 2026-09-19 recorded in `WORKTREES.md` and `scripts/cloud-setup.sh`:
- Ubuntu 24.04 with PostgreSQL 16 and pgvector from PGDG, Redis 7 and Node 22.22;
- 4 CPUs and 15 GB per session, enough for its own E2E stack with `cloud-setup.sh --e2e`.

Two things are still to confirm. The first is how many sessions may run at once; the plan assumes 6. The second is that a journey passes in the cloud. The first `cloud+e2e` package in the schedule, `f03-T05` in wave 2, is the pilot. Until it passes, `cloud+e2e` packages fall back to local-e2e. If the pilot fails for good, the simulation puts R1 at 28.6 hours and everything at 66.7.

## 3. Cross-chunk dependency graph

### 3.1 Names

The chunk 3 and chunk 4 task files map to package ids as follows.

| Task | Package | Task | Package |
|---|---|---|---|
| chunk3-rest-T1 | c3-append-only | chunk4-T1 | c4-proposal-kind |
| chunk3-rest-T2 | c3-seed-j6 | chunk4-T2 | c4-rejection-reasons |
| chunk3-rest-T3 | c3-no-tone | chunk4-T3 | c4-audit-read |
| chunk3-rest-T4 | c3-obligations-read | chunk4-T4 | c4-second-editor |
| chunk3-rest-T5 | c3-fe-presentation | chunk4-T5 | c4-console-shell |
| chunk3-rest-T6 | c3-obligation-detail-read | chunk4-T6 | c4-approve-apply |
| chunk3-rest-T7 | c3-footprint-counts | chunk4-T7 | c4-console-tenants-api |
| chunk3-rest-T8 | c3-seed-provisions | chunk4-T8 | c4-seed-proposals |
| chunk3-rest-T9 | c3-fe-inventory | chunk4-T9 | c4-fe-audit-log |
| chunk3-rest-T11a | c3-reports-verify-logic | chunk4-T10 | c4-queue-reads |
| chunk3-rest-T11b | c3-reports-verify-routes | chunk4-T11 | c4-door-proof |
| chunk3-rest-T12 | c3-fe-obligation-card | chunk4-T12 | c4-fe-tenants |
| chunk3-rest-T13 | c3-instruments-read | chunk4-T13a | c4-mark-seen |
| chunk3-rest-T14 | c3-fe-obligation-versions | chunk4-T13b | c4-library-updates |
| chunk3-rest-T16 | c3-provision-read | chunk4-T14 | c4-fe-queue |
| chunk3-rest-T17 | c3-fe-instruments | chunk4-T15 | c4-security-review-1 |
| chunk3-rest-T18 | c3-fe-provision-tree | chunk4-T16a | c4-report-window |
| chunk3-rest-T19 | c3-security-review | chunk4-T16b | c4-reports-console-api |
| chunk3-rest-T20 | c3-close | chunk4-T17 | c4-fe-approve |
| | | chunk4-T18 | c4-report-resolves |
| | | chunk4-T19 | c4-fe-library-updates |
| | | chunk4-T20 | c4-fe-tenant-proposals |
| | | chunk4-T21 | c4-fe-console-reports |
| | | chunk4-T22 | c4-security-review-2 |
| | | chunk4-T23 | c4-fe-report-loop |
| | | chunk4-T24a | c4-close-a |
| | | chunk4-T24b | c4-close-b |

The PRD 0.3 tasks keep their ids from `FEATURES_0_3_TASKS.md`:
- REGULATORY_SCOPE T01 to T10 are f03-T01 to f03-T10, the old rs-t01 to rs-t10.
- f03-T03 is built once, as `c3-footprint-counts`.
- f03-T11 to f03-T14 and rs-t15 are on main.
- f03-T40 is folded into `adm-lang-jur-kinds` (ruling 28).
- `FEATURES_0_3_TASKS.md` lands on main with p03.

The maps also name packages from other chunks. Each name resolves as follows.

| Name used in a map or brief | Package here |
|---|---|
| E1, E2, E3, E4, E5 (`EARLY_R1_PACKAGES.md`) | c5-content-screen, c5-cards-console, c5-llm-anthropic-provider, c7-embedder-mock-reranker, c5-contract-models-agents |
| H10, H-A, H9 (`HARDENING.md`) | h10-log-no-query, h-a-guards, h9-footprint-antijoin |
| rs-t01 to rs-t10 | f03-T01 to f03-T10 |
| c3-library-read-api, c3-obligations-read-api | c3-provision-read (the end of the library backend chain) |
| c3-inventory-footprint | c3-footprint-counts |
| c3-seed-e2e-library, c3-library-seed | c3-seed-provisions |
| c3-inventory-screens, c3-ui-obligation-page, c3-obligation-screen | c3-fe-obligation-versions |
| c3-ui-inventory | c3-fe-instruments (the last chunk 3 package to edit the inventory screen) |
| c3-append-only-trigger | c3-append-only |
| c3-library-data-layer | already on main (51f9efa) |
| c4-proposals-kinds, c4-proposal-kinds, c4-proposals-contract | c4-proposal-kind; c4-approve-apply where `apply.py` is used; c4-library-updates where proposals logic is edited |
| c4-proposals-apply | c4-approve-apply |
| c4-fe-console-shell | c4-console-shell |
| c4-console-queue, c4-fe-console-queue | c4-fe-approve |
| c4-library-updates (the screen) | c4-fe-library-updates |
| c4-console-tenants | c4-console-tenants-api |
| c4-audit-events-read, c4-audit-log-screen | c4-audit-read, c4-fe-audit-log |
| c4-proposed-by-tenant | c4-queue-reads (the `proposal_tenant` link and `GET /tenant/proposals`) |
| c4-ai-generation, c4-ai-generation-model, c4-ai-log-read, c4-governance-models, c7-ai-generation | c5-ai-log-contract (ruling 1) |
| c4-console-health, c5-console-health-feeds | c14-health-backend (ruling 2) |
| c4-console-sources-page | dropped (ruling 3) |
| console language and jurisdiction edits (cut by chunk 4) | adm-lang-jur-kinds, adm-fe-lang-jur (ruling 28) |
| c5-cases-new, c5-case-creation, c5-case-fanout | c5-contract-models-cases for the model, c5-cases-creation for the behaviour |
| c5-watch-models, c5-watch-contract, c5-watch-read-contract | c5-contract-models-watch for models, c5-contract-api-screens for schemas |
| c5-agents-contract | c5-contract-models-agents and c5-contract-api-agent |
| c5-e2e-seed | c5-seed-watch |
| c5-change-screen, c5-watch-screen, c5-watch-feed | c5-fe-change-detail with c5-fe-so-what-panel, c5-fe-watch-feed, c5-watch-feed-read |
| c5-so-what, c5-so-what-drafts | c5-cases-so-what-and-links; c5-ai-log-and-so-what-draft for the draft |
| c5-register-change, c5-agent-change-api | c5-watch-registration |
| c5-console-sources, c5-source-coverage | c5-fe-console-sources, c5-watch-sources-coverage |
| c5-classifier-eval | c5-classification-baseline |
| c5-outbox-relay | c5-outbox-cursor (ruling 9) |
| c5-search-similar | c7-hybrid-search-backend (ruling 4) |
| c6-roadmap, c6-roadmap-api, c6-today-api | c6-roadmap-backend, c6-home-backend |
| c6-today, c6-ui-today, c6-ui-roadmap | c6-today-screen, c6-roadmap-screen |
| c7-ask, c7-search-api, c7-search-chunks | c7-ask-backend and c7-ask-screen, c7-search-api-contract, c7-search-index |
| c7-llm-streaming-adapter | deleted: c5-llm-anthropic-provider (E3) adds `stream()` (ruling 5) |
| c8-teams, c8-delegation, c8-support-access | c8-ten-teams, c8-ten-out-of-office, c8-support-access-mechanism |
| c8-register-contract, c8-register-cards, c8-register-screen, c8-gaps | c8-register-models with c8-register-api-contract, c8-card-obligation-register, c8-ui-where-we-stand, c8-reg-gaps |
| c8-reference-members | c9-case-contract (ruling 11) |
| c9-cases-contract, c9-case-workflow-contract, c9-case-screen, c9-case-cards | c9-case-contract, c9-fe-cases-feature, c9-case-design |
| c9-case-close | c9-signoff |
| c9-ticket-export | c13-tickets-export (ruling 6) |
| c9-contributor-vocab | dropped: f03-T51, f03-T53 and f03-T76 (ruling 26) |
| c9-my-work | dropped: f03-T50 to f03-T62 and f03-T77 (ruling 26) |
| c9-workflow-policy-contract | c10-workflow-policy |
| c10-notify, c10-notifications, c10-notifications-contract | c10-collab-models (`notify()`), c10-notifications-api |
| c10-comments-contract, c10-notifications-screen | c10-comments-api, c10-fe-notifications |
| c11-security-policy-contract, c11-tenant-agents, c11-tenant-runs | c11-security-policy, c11-tenant-agent-controls, c11-run-scheduler |
| c12-jobs, c12-tenant-exit | c12-exports-contract, c12-exit-deletion with c12-exit-export |
| c14-owasp-fixes | c14-owasp-fixes-auth, -access, -library-ai, -files-data, -integrations-web |

### 3.2 Rulings where the sources disagree

The maps, task files and briefs were written separately. Where they plan the same thing twice, lean on something nobody builds or contradict PRD 0.3, one ruling applies.

| # | Where the sources disagree | Ruling |
|---|---|---|
| 1 | Chunk 4 cut `AiGeneration` and `GET /ai-generations` to chunk 7, but chunk 5 already logs model outputs | `c5-ai-log-contract` builds the model to schema v0.3 with chunk 7's columns (asker, input, prompt hash, tokens and feedback), `log_generation()` and the read. It also builds the one wrapper that calls the model and logs it, with its guard test. `c7-ai-log-backend` keeps only feedback and filters |
| 2 | Chunk 4 moved console health to chunk 14, and `c5-console-health-feeds` extends it | Folded into `c14-health-backend`. ADM-S5 stays pending until chunk 14. Failed jobs with retry come from `c14-job-runs` (ruling 34) |
| 3 | Chunk 4 cut the read-only console Sources page | `c5-fe-console-sources` builds the page on chunk 4's shell, after `c5-watch-sources-coverage` |
| 4 | `POST /search/similar` is planned twice: trigram in chunk 5, hybrid in chunk 7 | `c7-search-api-contract` declares it once and `c7-hybrid-search-backend` serves it; its keyword leg works without embeddings. `c5-agent-api-flow` waits for it and for `c7-index-changes`. If the search-fence decision is not in by hour 6, build `c5-search-similar` as its map describes and let chunk 7 replace its body |
| 5 | The Anthropic provider and streaming land in chunk 5 or chunk 7 | E3 (`c5-llm-anthropic-provider`) built both, `stream()` included. `c7-llm-streaming-adapter` is deleted, and Ask waits on no LLM package but E3's merge |
| 6 | "Send as tickets" is planned in chunk 9 and chunk 13, with different tables | Built once, in `c13-tickets-export`: the `action_ticket` table, the adapter seam and the job. `c13-fe-tickets-screen` adds the button to the actions panel |
| 7 | The export job framework is planned in chunk 9 and chunk 12 | `c12-exports-contract` owns `ExportJob` and `/exports` and starts early. `c9-case-file-export` is the case-file exporter on top of it |
| 8 | The malware scanner adapter is planned in chunk 9 or chunk 12 | Only `c9-scanner-adapter` builds it. `c12-imports-contract` depends on it |
| 9 | Solution_Design routes case creation, embeddings, notifications and deliveries through outbox → worker, but no package built a trigger | `c5-outbox-cursor` builds the one ordered cursor over `outbox_event`. It activates each tenant in the worker (`@tenant_task`) and dispatches by event kind. `c5-cases-creation`, `c7-index-changes`, `c10-collab-models` and `c13-int-contract` build on it; `c13-int-contract` only adds delivery targets. No second relay is built |
| 10 | Case ownership by team, and the case halves of TEN-S3 and TEN-S5 | `c9-case-models` adds `change_case.owner_team`. `c9-triage` un-skips the case half of TEN-S3, and `c9-actions` adds cases and actions to the TEN-S5 open-work list. Chunk 8 closes with those halves named |
| 11 | `GET /reference/members?permission=` has no owner | `c9-case-contract` adds it |
| 12 | Chunk 5 (So what) and chunk 9 (My work) both claimed `cases/work_logic.py` | HOM-05 makes My work its own page. Its service is `home/my_work.py` (f03-T56 to f03-T59, key `mywork`), and cases keep their own logic |
| 13 | Two AI switches: Ask off in chunk 7, all AI off in chunk 11 | One column, `Tenant.ai_enabled`, built by `c7-ask-switch`. Chunk 11's settings row holds only the monthly cap. `c11-ai-off-switch` adds only the AI-off check inside ruling 1's wrapper |
| 14 | Chunk 4 cut the `obligation_scope` proposal kind, which re-tag batches need | `c11-batch-proposals-contract` adds it |
| 15 | Several packages change `tenants/models.py` | Key `mig:tenants` runs them one at a time: `c8-tenants-contract`, `c11-security-policy`, `c8-ten-support-grants`, `f03-T51`, `f03-T66`, `c13-ip-allowlist` |
| 16 | `c7-index-changes` hooks `watch/logic.py` | It hooks no watch writer: it consumes the change events through `c5-outbox-cursor`, as Solution_Design routes embeddings. The watch writers keep their own key, `watchwrite` |
| 17 | The chunk 6 seed waits for the briefing snapshot builder | `c6-e2e-seed` seeds only the dates and the lead item. The seeded emailed snapshot moves into `c6-briefing-screen` |
| 18 | Chunk 12 has no close package | `c12-close` is added |
| 19 | Agent definitions: a runtime pyyaml or E5's own reader | E5's reader stays. It reads five top-level scalars from repository files, refuses anything else so a deploy stops rather than guesses, and a test pins it to PyYAML. Its review treats it as input parsing. pyyaml stays a development dependency, and if chunk 11 needs full YAML at runtime, that package moves the dependency locally, in its own ship |
| 20 | Today's "Where we stand" and `GET /reports/summary` | Today reads its own home endpoint (`c8-home-register-feeds`). `/reports/*` belongs to `c12-dashboard-api` |
| 21 | Server-rendered mail text | `c10-mail-catalog` extends chunk 6's briefing mail composer in sv and en, and `c12-committee-pack` uses it. `c13-i18n-server` adds da, nb and fi to the mail catalogs and to `User.locale`, whose schema CHECK allows only en and sv today |
| 22 | The da, nb and fi catalogs wait for chunk closes | They wait for every R2 and R3 screen package (the catalog freeze), not for the closes. `c13-i18n-seed-labels` waits for every package that seeds a vocabulary or library list |
| 23 | Every OWASP review waits for `c13-close` | Each review starts when its area is merged, and each has its own fix package. Convergence still comes before `c14-close` |
| 24 | Chunk 4 made all of chunk 3 a hard precondition | Replaced by `x-frontend-split`, the file keys and the functional dependencies |
| 25 | Some dependencies in the maps only order edits to one file | Replaced by serialization keys, so whichever package is ready first goes first |
| 26 | PRD 0.3 contradicts `c9-contributor-vocab` and `c9-my-work` | Both are dropped. CAS-03 records contributor teams as the case's team participants: `c9-case-models` depends on f03-T51 and f03-T53, and f03-T76 adds case participants. HOM-05 makes My work its own page with "Decisions stay on Today": f03-T50 to f03-T62 and f03-T77. `c9-e2e-triage-journeys` depends on f03-T62 and f03-T77 |
| 27 | COL-02 escalates to the head of the owner's department, and f03-T81 also escalates | Escalation is built once, in `c10-reminders-escalation`, which depends on f03-T51. f03-T81 keeps the digest built on the My work service, and `c10-digest` sends it and depends on f03-T81 |
| 28 | f03-T40 needs a console jurisdiction edit that chunk 4 cut, because a direct edit bypasses the proposal door | `adm-lang-jur-kinds` adds language and jurisdiction proposal kinds, applied through `apply.py`, and updates the mirrored term in the same transaction; that is f03-T40's done-condition. `adm-fe-lang-jur` adds the console screen. Both are R2 (ADM-02 spans R1 to R3). Until then, jurisdictions change only through seeds, which f03-T16's mirror guard keeps exact |
| 29 | `c3-fe-obligation-card` strengthens FP-S5 with a preview count, which needs f03-T03 and its PRD 0.3 dependencies | FP-S5's count step moves to f03-T08, the package that builds the change panel. `c3-fe-obligation-card` no longer depends on `c3-footprint-counts`, so chunk 3's frontend chain stays off the Regulatory scope chain |
| 30 | f03-T36 extends `library/reading.py` while the chunk 3 read chain edits it | f03-T36 takes `libread` after `c3-provision-read`, so the chunk 3 chain runs unbroken |
| 31 | The change page needs the So-what drafts, which come late in chunk 5 | The page splits. `c5-fe-change-detail` (header, timeline, flags and links) waits for `c5-watch-feed-read`. `c5-fe-so-what-panel` waits for `c5-cases-so-what-and-links` |
| 32 | Registering a change is what creates the cases (CAS-01), yet both packages ran side by side | `c5-cases-creation` registers the per-tenant handler for the change-registered event on `c5-outbox-cursor`. `c5-watch-registration` depends on it and proves CAS-01 end to end |
| 33 | f03-T47 waits on "chunk 5's classifier" and was given the `ci` key | The classifier is the mock one the evaluation gate runs, wired by `c7-eval-gate`. f03-T46, f03-T47 and f03-T49 edit only `backend/eval/` and `search_eval.py`, so they take the `eval` key |
| 34 | ADM-02's evaluation sets and failed jobs have no owner | `c7-eval-sets` (`eval_question`, `eval_run`, `eval.manage`) and `c7-fe-console-eval-sets` in chunk 7. `c14-job-runs` (a `job_run` row per worker job, and retry) in chunk 14, feeding `c14-health-backend` and `c14-fe-health` |
| 35 | NFR-02 is R1, but the performance pass sits in chunk 14 | `c14-perf-harness` depends on nothing and runs in R1. `r1-perf` measures R1's budgets with it, and each chunk 14 performance pass depends only on its own area |
| 36 | Tenant export and deletion would miss tenant tables built after chunk 12 | `c12-exit-export` and `c12-exit-deletion` go over every model with a `tenant_id`, as `tests_rls` does. A guard test fails on any tenant table they do not cover. Its exception list, for tables deliberately kept, each with a reason, is an append ledger. The guard runs in every backend suite, and `c12-close` and `c14-close` check it |

### 3.3 Every package

Columns:
- **ch**: the chunk. X is the frontend split, P the PRD 0.3 consolidation, H the hardening follow-ups, CI the CI change, RS the Regulatory scope tasks, R1 the R1 checks and ADM the console language and jurisdiction work.
- **rel**: the release the package belongs to.
- **depends on**: a `q-` entry waits for an Alex decision and a `k-` entry for a key or account (section 7). For a package in review or running, it means "merges after".
- **lane**: the simulated placement (section 2). `(c)` marks a cloud-eligible package that the plan still runs locally. `local` or `cloud` for a built package says where its branch is.
- **min**: estimated minutes of package work. A package that goes back for a change shows the minutes of that change.
- **wave**: section 4. `done`, `review`, `merging` and `running` give the state at the start. `after key` means the package waits for a key or account.
- **serializes on**: its keys (section 3.4).
- **SR**: a security review is required before merge.

| id | ch | rel | depends on | lane | min | wave | serializes on | SR |
|---|---|---|---|---|---|---|---|---|
| x-frontend-split | X | R1 | c4-console-shell | local-unit | 45 | 0 | cat |  |
| p03-consolidation | P | R1 | none | local-unit (c) | 20 | 0 | gates | yes |
| h10-log-no-query | H | R1 | none | local-unit | 45 | running | - | yes |
| h-a-guards | H | R1 | c3-no-tone | local-unit (c) | 45 | 1 | shschema idp | yes |
| h9-footprint-antijoin | H | R1 | c3-obligations-read | local-unit (c) | 45 | 3 | libread | yes |
| ci-e2e-shards | CI | R1 | none | local-unit | 45 | 0 | ci |  |
| rs-t15 | RS | R1 | - | - | 30 | done | - |  |
| f03-T02 | RS | R1 | p03-consolidation | local-unit | 45 | running | mig:taxonomy fp taxapi | yes |
| f03-T01 | RS | R1 | none | cloud | 35 | 2 | seedlib taxseed | yes |
| f03-T04 | RS | R1 | x-frontend-split | local-e2e (c) | 45 | 2 | shellfe today fpscreen roles |  |
| f03-T05 | RS | R1 | x-frontend-split | cloud+e2e | 40 | 2 | uiprim |  |
| f03-T06 | RS | R1 | f03-T04 | local-unit (c) | 40 | 3 | fpscreen |  |
| f03-T07 | RS | R1 | f03-T05, f03-T06 | local-e2e (c) | 45 | 4 | fpscreen |  |
| f03-T08 | RS | R1 | f03-T07, c3-footprint-counts | local-e2e (c) | 55 | 5 | fpscreen |  |
| f03-T09 | RS | R1 | f03-T08 | local-e2e (c) | 45 | 6 | fpscreen |  |
| f03-T10 | RS | R1 | f03-T09 | local-e2e (c) | 40 | 8 | fpscreen today shellfe |  |
| c3-seed-j6 | 3 | R1 | - | - | 35 | done | - | yes |
| c3-fe-presentation | 3 | R1 | - | - | 45 | done | - |  |
| c3-append-only | 3 | R1 | none | local | 45 | review | mig:library | yes |
| c3-no-tone | 3 | R1 | none | local | 35 | review | prop taxapi shschema | yes |
| c3-obligations-read | 3 | R1 | h10-log-no-query | local | 60 | review | libread taxhttp | yes |
| f03-T15 | 3 | R1 | none | cloud | 40 | 0 | mig:library seedlib |  |
| f03-T22 | 3 | R1 | none | local-unit (c) | 45 | 0 | - |  |
| f03-T34 | 3 | R1 | none | cloud | 45 | 0 | - |  |
| f03-T18 | 3 | R1 | none | cloud | 40 | 1 | mig:taxonomy | yes |
| c3-obligation-detail-read | 3 | R1 | c3-obligations-read, c3-append-only | local-unit (c) | 55 | 1 | libread | yes |
| c3-seed-provisions | 3 | R1 | c3-append-only | local-e2e (c) | 45 | 1 | seedlib | yes |
| c3-fe-inventory | 3 | R1 | c3-obligations-read, x-frontend-split | local-e2e (c) | 55 | 1 | libfe invscreen |  |
| c3-reports-verify-logic | 3 | R1 | c3-append-only | local-unit (c) | 40 | 1 | mig:library apply | yes |
| f03-T25 | 3 | R1 | f03-T02 | local-unit (c) | 50 | 2 | mig:taxonomy fp match | yes |
| c3-fe-obligation-card | 3 | R1 | c3-obligation-detail-read, c3-fe-inventory, c3-seed-provisions | local-e2e (c) | 55 | 3 | libfe obpage |  |
| f03-T26 | 3 | R1 | f03-T25 | local-unit (c) | 45 | 4 | mig:taxonomy | yes |
| c3-footprint-counts | 3 | R1 | c3-obligations-read, f03-T02, f03-T25 | local-e2e (c) | 40 | 4 | taxreg fp | yes |
| c3-reports-verify-routes | 3 | R1 | c3-obligation-detail-read, c3-reports-verify-logic | cloud | 45 | 4 | libread | yes |
| f03-T16 | 3 | R1 | f03-T15 | cloud | 45 | 5 | mig:taxonomy taxseed |  |
| c3-urgency-rule | 3 | R1 | q-urgency, c3-no-tone | cloud | 30 | 5 | taxreg | yes |
| c3-instruments-read | 3 | R1 | c3-reports-verify-routes, c3-seed-provisions | local-unit (c) | 50 | 6 | libread | yes |
| c3-fe-obligation-versions | 3 | R1 | c3-fe-obligation-card, c3-reports-verify-routes | local-e2e (c) | 55 | 6 | libfe obpage |  |
| f03-T27 | 3 | R1 | f03-T26, f03-T01 | cloud | 40 | 7 | taxseed seedlib |  |
| c3-fe-instruments | 3 | R1 | c3-instruments-read, c3-fe-obligation-versions | local-e2e (c) | 55 | 7 | libfe invscreen |  |
| f03-T17 | 3 | R1 | f03-T16 | cloud | 45 | 8 | apply liblists | yes |
| f03-T19 | 3 | R1 | f03-T16, f03-T18 | cloud | 50 | 8 | - | yes |
| f03-T29 | 3 | R1 | f03-T26, c3-append-only, c3-seed-provisions | cloud | 55 | 8 | mig:taxonomy taxreg mig:library seedlib | yes |
| c3-provision-read | 3 | R1 | c3-instruments-read, c3-seed-provisions, c3-append-only | local-unit (c) | 45 | 8 | libread | yes |
| f03-T30 | 3 | R1 | c3-append-only, f03-T16 | cloud | 45 | 9 | mig:library seedlib |  |
| c3-fe-provision-tree | 3 | R1 | c3-provision-read, c3-fe-instruments | local-e2e (c) | 45 | 9 | libfe |  |
| f03-T28 | 3 | R1 | f03-T27, f03-T06, f03-T07 | cloud | 45 | 10 | taxapi fpscreen |  |
| f03-T32 | 3 | R1 | f03-T29, c3-instruments-read, x-frontend-split | cloud | 40 | 10 | libfe |  |
| f03-T31 | 3 | R1 | f03-T30 | local-unit (c) | 35 | 11 | mig:library |  |
| f03-T36 | 3 | R1 | f03-T16, c3-provision-read | cloud | 50 | 11 | libread | yes |
| c3-security-review | 3 | R1 | c3-fe-provision-tree, c3-provision-read, c3-footprint-counts, c3-no-tone, c3-seed-provisions | local-unit | 45 | 11 | - |  |
| f03-T20 | 3 | R1 | f03-T19 | local-unit (c) | 45 | 12 | taxapi taxhttp | yes |
| f03-T35 | 3 | R1 | f03-T34, f03-T27, f03-T29, f03-T30, f03-T31, c3-instruments-read | local-unit (c) | 45 | 12 | seedlib |  |
| f03-T37 | 3 | R1 | f03-T36, f03-T19, c3-fe-instruments | local-e2e (c) | 60 | 12 | libread libfe invscreen | yes |
| c3-review-fixes | 3 | R1 | c3-security-review | local-unit | 45 | 13 | - | yes |
| f03-T21 | 3 | R1 | f03-T20 | local-unit (c) | 30 | 14 | - |  |
| f03-T23 | 3 | R1 | f03-T22, f03-T20, f03-T09 | local-e2e (c) | 55 | 14 | fpscreen |  |
| f03-T33 | 3 | R1 | f03-T32, c3-fe-provision-tree, f03-T35 | cloud+e2e | 45 | 14 | libfe |  |
| c3-close | 3 | R1 | c3-review-fixes | local-e2e | 45 | 15 | - |  |
| f03-T24 | 3 | R1 | f03-T36, f03-T23 | cloud+e2e | 45 | 16 | fpscreen |  |
| f03-security-review | 3 | R1 | every R1 f03 task marked SR | local-unit | 45 | 17 | - |  |
| f03-review-fixes | 3 | R1 | f03-security-review | local-unit | 45 | 18 | - | yes |
| c4-rejection-reasons | 4 | R1 | - | - | 40 | done | - | yes |
| c4-audit-read | 4 | R1 | - | - | 50 | done | - | yes |
| c4-door-proof | 4 | R1 | - | - | 30 | done | - | yes |
| c4-console-shell | 4 | R1 | none | local | 60 | merging | cat shellfe |  |
| f03-T39 | 4 | R1 | none | cloud | 25 | 0 | taxseed |  |
| c4-proposal-kind | 4 | R1 | none | cloud | 55 | 0 | mig:proposals prop | yes |
| c4-second-editor | 4 | R1 | none | local-e2e (c) | 40 | 0 | - | yes |
| c4-fe-audit-log | 4 | R1 | c4-console-shell, x-frontend-split | local-e2e (c) | 50 | 1 | - |  |
| c4-mark-seen | 4 | R1 | none | cloud | 35 | 1 | idapi | yes |
| c4-console-tenants-api | 4 | R1 | c4-second-editor | local-unit (c) | 50 | 2 | ten gov | yes |
| c4-seed-proposals | 4 | R1 | c4-proposal-kind, c4-second-editor, c3-seed-provisions | local-unit (c) | 40 | 2 | - |  |
| c4-approve-apply | 4 | R1 | c4-proposal-kind, c3-append-only, c3-reports-verify-logic | local-unit (c) | 60 | 3 | apply prop | yes |
| c4-fe-tenants | 4 | R1 | c4-console-tenants-api, c4-fe-audit-log, c4-second-editor | local-e2e (c) | 50 | 3 | - |  |
| c4-report-window | 4 | R1 | c4-proposal-kind, c3-reports-verify-logic, q-Q1 | local-unit | 50 | 4 | auth mig:library | yes |
| c4-queue-reads | 4 | R1 | c4-approve-apply | local-unit (c) | 55 | 5 | prop | yes |
| c4-library-updates | 4 | R1 | c4-queue-reads, c4-mark-seen | local-unit | 50 | 7 | prop | yes |
| c4-fe-queue | 4 | R1 | c4-queue-reads, c4-fe-tenants, c4-seed-proposals | local-e2e (c) | 55 | 7 | consoleq |  |
| c4-reports-console-api | 4 | R1 | c4-report-window, c4-console-tenants-api, c4-mark-seen | local-unit | 50 | 8 | gov | yes |
| c4-security-review-1 | 4 | R1 | c4-library-updates, c4-fe-queue, c4-seed-proposals, c4-fe-tenants | local-unit | 45 | 9 | - |  |
| c4-fe-approve | 4 | R1 | c4-fe-queue, c4-approve-apply, c4-queue-reads | local-e2e (c) | 55 | 9 | consoleq |  |
| c4-report-resolves | 4 | R1 | c4-reports-console-api, c4-library-updates, c4-approve-apply, c4-queue-reads | local-unit (c) | 50 | 10 | gov prop | yes |
| c4-fe-library-updates | 4 | R1 | c4-mark-seen, c4-library-updates, c4-fe-approve, c3-fe-instruments | local-e2e | 50 | 10 | libupd |  |
| c4-review-fixes-1 | 4 | R1 | c4-security-review-1 | local-unit | 45 | 11 | - | yes |
| c4-fe-tenant-proposals | 4 | R1 | c4-queue-reads, c4-fe-queue, c4-fe-approve, c4-second-editor | local-e2e (c) | 45 | 11 | vocabfe |  |
| c4-fe-console-reports | 4 | R1 | c4-reports-console-api, c4-report-resolves, c4-fe-library-updates | local-e2e (c) | 55 | 12 | - |  |
| f03-T38 | 4 | R1 | f03-T25, f03-T29, c4-proposal-kind, c4-approve-apply | local-unit (c) | 50 | 13 | prop apply | yes |
| c4-security-review-2 | 4 | R1 | c4-report-window, c4-reports-console-api, c4-report-resolves, c4-review-fixes-1 | local-unit (c) | 40 | 13 | - |  |
| c4-review-fixes-2 | 4 | R1 | c4-security-review-2 | local-unit | 45 | 14 | - | yes |
| c4-close-a | 4 | R1 | c4-fe-approve, c4-fe-library-updates, c4-fe-tenant-proposals, c3-close, c4-review-fixes-1 | local-e2e | 45 | 16 | - |  |
| c4-fe-report-loop | 4 | R1 | c4-fe-console-reports, c4-report-resolves, c4-review-fixes-2 | local-e2e (c) | 50 | 16 | libupd |  |
| c4-close-b | 4 | R1 | c4-close-a, c4-fe-report-loop, c4-review-fixes-2 | local-unit | 30 | 17 | - |  |
| c5-content-screen | 5 | R1 | - | - | 45 | done | - | yes |
| c5-cards-console | 5 | R1 | - | - | 45 | done | - |  |
| c5-contract-models-agents | 5 | R1 | none | cloud | 40 | review | mig:agents mig:identity auth idkeys fence taxhttp | yes |
| c5-llm-anthropic-provider | 5 | R1 | none | cloud | 45 | review | llm | yes |
| f03-T44 | 5 | R1 | none | cloud | 30 | 0 | sweeper |  |
| c5-contract-models-watch | 5 | R1 | c5-contract-models-agents | local-unit (c) | 60 | 0 | mig:watch fence | yes |
| c5-contract-api-agent | 5 | R1 | none | cloud | 50 | 0 | agentsapi watchapi idapi | yes |
| c5-outbox-cursor | 5 | R1 | none | cloud | 50 | 0 | mig:shared | yes |
| c5-contract-api-screens | 5 | R1 | c5-contract-api-agent | local-unit (c) | 60 | 1 | watchapi casesapi | yes |
| c5-contract-models-cases | 5 | R1 | c5-contract-models-watch | local-unit (c) | 35 | 2 | mig:cases | yes |
| c5-fe-copy-nav | 5 | R1 | x-frontend-split | cloud | 45 | 3 | shellfe |  |
| c5-integration-scenarios | 5 | R1 | c5-contract-models-cases, c5-contract-api-screens | local-unit (c) | 55 | 4 | - |  |
| c5-ai-log-contract | 5 | R1 | c4-console-tenants-api | local-unit (c) | 60 | 4 | mig:governance gov | yes |
| c5-agent-runs | 5 | R1 | c5-contract-models-agents, c5-contract-api-agent, c5-integration-scenarios | local-unit (c) | 45 | 5 | - | yes |
| c5-cases-creation | 5 | R1 | c5-contract-models-cases, c5-contract-api-screens, c5-integration-scenarios, c5-outbox-cursor | local-unit (c) | 55 | 5 | - | yes |
| c5-watch-curation | 5 | R1 | c5-contract-models-watch, c5-contract-api-screens, c5-integration-scenarios | cloud | 50 | 6 | watchwrite | yes |
| c5-platform-agent-keys | 5 | R1 | c5-contract-models-agents, c5-contract-api-agent, c5-integration-scenarios | cloud | 45 | 6 | idkeys | yes |
| f03-T45 | 5 | R1 | f03-T44, c5-agent-runs | cloud | 40 | 7 | agentsapi sweeper |  |
| c5-watch-sources-coverage | 5 | R1 | c5-contract-models-watch, c5-contract-api-screens, c5-integration-scenarios, c5-agent-runs | local-unit (c) | 50 | 7 | - | yes |
| c5-watch-registration | 5 | R1 | c5-contract-models-watch, c5-contract-api-agent, c5-integration-scenarios, c5-content-screen, c5-agent-runs, c5-cases-creation | cloud | 60 | 7 | watchwrite | yes |
| c5-cases-footprint-hooks | 5 | R1 | c5-cases-creation, c3-footprint-counts, c4-console-tenants-api | cloud | 35 | 7 | fp | yes |
| c5-seed-watch | 5 | R1 | c5-contract-models-watch, c5-contract-models-cases, c5-cases-creation, c3-seed-provisions | local-e2e (c) | 60 | 7 | - | yes |
| c5-fe-watch-data-layer | 5 | R1 | c5-contract-api-screens, c5-fe-copy-nav, c3-urgency-rule | local-unit (c) | 45 | 8 | watchfe |  |
| c5-fe-console-change-facts | 5 | R1 | c5-fe-copy-nav, c5-contract-api-screens, c4-console-shell, c5-watch-curation | cloud | 55 | 8 | - |  |
| c5-fe-console-agent-keys | 5 | R1 | c5-fe-copy-nav, c5-contract-api-agent, c4-console-shell, c5-platform-agent-keys | local-e2e (c) | 50 | 8 | - |  |
| c5-ai-log-and-so-what-draft | 5 | R1 | c5-watch-registration, c5-cases-creation, c5-ai-log-contract | local-unit (c) | 50 | 9 | - | yes |
| c5-watch-feed-read | 5 | R1 | c5-contract-models-watch, c5-contract-api-screens, c5-cases-creation, c3-provision-read | local-unit (c) | 60 | 9 | libread | yes |
| c5-fe-console-sources | 5 | R1 | c5-contract-api-screens, c5-fe-copy-nav, c4-console-shell, c5-watch-sources-coverage | cloud | 50 | 9 | - |  |
| c5-vocab-usage-merge | 5 | R1 | c5-watch-curation, c4-approve-apply | cloud | 40 | 10 | taxreg apply | yes |
| c5-cases-so-what-and-links | 5 | R1 | c5-cases-creation, c5-contract-api-screens, c5-integration-scenarios, c5-ai-log-and-so-what-draft | local-unit (c) | 55 | 11 | - | yes |
| c5-fe-change-detail | 5 | R1 | c5-fe-watch-data-layer, c3-fe-instruments, c5-watch-feed-read | local-unit (c) | 45 | 11 | changescreen watchfe |  |
| c5-library-links-provenance | 5 | R1 | c5-contract-models-watch, c5-agent-runs, c4-library-updates, c3-provision-read | cloud | 55 | 12 | mig:proposals mig:library apply prop watchwrite | yes |
| c5-fe-watch-feed | 5 | R1 | c5-fe-watch-data-layer, c5-watch-feed-read | cloud | 60 | 12 | watchfe |  |
| f03-T43 | 5 | R1 | f03-T30, f03-T35, c5-watch-sources-coverage, c5-watch-registration, c5-cases-creation | cloud | 55 | 13 | watchwrite watchapi seedlib | yes |
| c5-fe-so-what-panel | 5 | R1 | c5-fe-change-detail, c5-cases-so-what-and-links | cloud | 30 | 13 | changescreen watchfe |  |
| c5-e2e-vocab-footprint-feed | 5 | R1 | c5-vocab-usage-merge, c5-cases-footprint-hooks, c5-seed-watch, c5-fe-watch-feed, c5-fe-console-change-facts | local-e2e (c) | 40 | 13 | - |  |
| f03-T46 | 5 | R1 | f03-T35 | cloud | 40 | 14 | eval |  |
| c5-agent-api-flow | 5 | R1 | c5-agent-runs, c5-watch-sources-coverage, c5-watch-registration, c7-hybrid-search-backend, c5-library-links-provenance, c5-platform-agent-keys, c7-index-changes | local-unit (c) | 45 | 14 | - | yes |
| c5-fe-obligation-related-changes | 5 | R1 | c5-fe-watch-data-layer, c3-fe-obligation-versions, c5-watch-feed-read, c5-library-links-provenance | local-unit (c) | 35 | 14 | obpage |  |
| f03-T41 | 5 | R1 | f03-T37, c5-contract-models-watch, c5-watch-feed-read, c5-fe-watch-feed | cloud+e2e | 55 | 15 | watchapi watchwrite watchfe | yes |
| f03-T42 | 5 | R1 | f03-T38, f03-T31, c5-library-links-provenance | local-unit (c) | 50 | 15 | prop apply | yes |
| c5-e2e-watch-journeys | 5 | R1 | c5-seed-watch, c5-fe-watch-feed, c5-fe-change-detail, c5-fe-console-sources, c5-fe-console-change-facts, c5-fe-obligation-related-changes, c5-watch-sources-coverage, c5-watch-registration, c5-watch-curation, c5-cases-so-what-and-links, c5-watch-feed-read, c5-fe-so-what-panel | local-e2e (c) | 60 | 15 | - |  |
| c5-e2e-j4-agent | 5 | R1 | c5-seed-watch, c5-agent-runs, c5-watch-registration, c5-library-links-provenance, c5-cases-creation, c5-fe-watch-feed, c4-fe-approve, c4-fe-library-updates, c3-fe-obligation-versions, c5-agent-api-flow, c5-platform-agent-keys | local-e2e (c) | 45 | 15 | - |  |
| c5-security-review | 5 | R1 | c5-agent-api-flow, c5-cases-so-what-and-links, c5-watch-feed-read, c5-watch-curation, c5-ai-log-and-so-what-draft, c5-fe-change-detail, c5-fe-console-agent-keys, c5-fe-so-what-panel | local-unit | 60 | 15 | - |  |
| f03-T47 | 5 | R1 | f03-T46, c7-eval-gate | local-unit (c) | 45 | 16 | eval |  |
| c5-review-fixes | 5 | R1 | c5-security-review | local-unit | 45 | 16 | - | yes |
| c5-chunk-close | 5 | R1 | c5-e2e-watch-journeys, c5-e2e-j4-agent, c5-e2e-vocab-footprint-feed, c5-cases-footprint-hooks, c5-review-fixes | local-e2e | 45 | 18 | - |  |
| c5-classification-baseline | 5 | R1 | c5-content-screen, c5-llm-anthropic-provider, c7-eval-gate, k-anthropic | local-unit | 45 | after key | eval ci |  |
| c6-home-api-contract | 6 | R1 | c5-contract-api-screens | local-unit (c) | 50 | 3 | homecore | yes |
| c6-home-models | 6 | R1 | c5-contract-models-cases | cloud | 40 | 4 | mig:home | yes |
| c6-roadmap-backend | 6 | R1 | c6-home-api-contract, c5-contract-models-watch, c5-cases-creation | local-unit (c) | 45 | 7 | - |  |
| c6-home-backend | 6 | R1 | c6-home-api-contract, c6-roadmap-backend, c5-watch-sources-coverage, c5-cases-creation, c4-queue-reads, c4-mark-seen | local-unit | 55 | 8 | homecore idapi |  |
| c6-upcoming-calendar-backend | 6 | R1 | c6-home-models, c6-home-api-contract, c6-roadmap-backend, c5-contract-models-watch, q-feed-token | local-unit (c) | 60 | 9 | - | yes |
| c6-e2e-seed | 6 | R1 | c5-seed-watch, c6-home-models | local-e2e (c) | 35 | 9 | - |  |
| c6-briefing-backend | 6 | R1 | c6-home-models, c6-home-api-contract, c6-home-backend, c6-roadmap-backend | local-unit (c) | 60 | 10 | - |  |
| c6-roadmap-screen | 6 | R1 | c6-home-api-contract, c6-roadmap-backend, c6-e2e-seed | local-e2e (c) | 60 | 10 | - |  |
| c6-calendar-feeds-screen | 6 | R1 | c6-home-api-contract, c6-upcoming-calendar-backend, c6-e2e-seed | local-e2e (c) | 45 | 11 | - |  |
| c6-today-screen | 6 | R1 | c6-home-api-contract, c6-home-backend, c6-e2e-seed, c5-fe-change-detail, c4-console-shell | local-e2e (c) | 60 | 12 | today |  |
| f03-T48 | 6 | R1 | c6-today-screen, c6-home-backend | local-e2e (c) | 40 | 14 | idapi today |  |
| c6-briefing-screen | 6 | R1 | c6-home-api-contract, c6-briefing-backend, c6-e2e-seed, c6-today-screen | local-e2e (c) | 55 | 14 | - |  |
| c6-security-review | 6 | R1 | c6-briefing-screen, c6-roadmap-screen, c6-calendar-feeds-screen, c6-today-screen, c6-upcoming-calendar-backend, c6-briefing-backend | local-unit | 45 | 15 | - |  |
| c6-review-fixes | 6 | R1 | c6-security-review | local-unit | 45 | 16 | - | yes |
| c6-chunk-close | 6 | R1 | c6-briefing-screen, c6-roadmap-screen, c6-calendar-feeds-screen, c6-today-screen, c6-upcoming-calendar-backend, c6-review-fixes | local-e2e | 45 | 17 | - |  |
| c7-embedder-mock-reranker | 7 | R1 | none | cloud | 40 | review | embed bootguard | yes |
| c7-search-api-contract | 7 | R1 | none | cloud | 45 | 0 | searchapi | yes |
| c7-ask-switch | 7 | R1 | c4-console-tenants-api, x-frontend-split | local-e2e (c) | 40 | 3 | mig:shared ten orgscreen | yes |
| c7-search-index | 7 | R1 | c4-approve-apply, c5-contract-models-watch, q-search-fence | local-unit | 60 | 5 | mig:search fence | yes |
| c7-hybrid-search-backend | 7 | R1 | c7-search-index, c7-search-api-contract, c7-embedder-mock-reranker | local-unit | 60 | 6 | searchapi | yes |
| c7-ai-log-backend | 7 | R1 | c5-ai-log-contract, c7-search-api-contract | local-unit (c) | 35 | 6 | gov |  |
| c7-ask-backend | 7 | R1 | c7-hybrid-search-backend, c7-ai-log-backend, c7-ask-switch, c5-contract-models-watch, c5-llm-anthropic-provider | local-unit | 60 | 8 | - | yes |
| c7-e2e-seed | 7 | R1 | c7-search-index, c7-ask-switch, c5-seed-watch | local-e2e | 35 | 8 | - |  |
| c7-eval-gate | 7 | R1 | c7-hybrid-search-backend | local-unit | 40 | 8 | eval ci |  |
| c7-index-changes | 7 | R1 | c7-search-index, c5-watch-registration, c5-watch-curation, c5-outbox-cursor | local-unit (c) | 35 | 10 | - | yes |
| c7-search-screen | 7 | R1 | c7-search-api-contract, c7-hybrid-search-backend, c7-e2e-seed, c3-fe-obligation-versions | local-e2e (c) | 60 | 10 | searchscreen |  |
| c7-eval-sets | 7 | R1 | c7-eval-gate | local-unit (c) | 55 | 10 | mig:search searchapi | yes |
| c7-ask-screen | 7 | R1 | c7-search-screen, c7-ask-backend, c7-ai-log-backend, c7-e2e-seed | local-e2e | 60 | 11 | searchscreen |  |
| c7-fe-console-eval-sets | 7 | R1 | c7-eval-sets, c4-console-shell, x-frontend-split | local-e2e (c) | 50 | 12 | - |  |
| f03-T49 | 7 | R1 | f03-T35, c7-ask-backend | local-unit (c) | 40 | 13 | eval |  |
| c7-ai-log-screen | 7 | R1 | c7-ai-log-backend, c7-ask-screen, c7-e2e-seed, c4-fe-audit-log | local-e2e | 45 | 13 | - |  |
| c7-j7-journey | 7 | R1 | c7-search-screen, c7-ask-screen, c7-e2e-seed, f03-T49 | local-e2e | 30 | 14 | - |  |
| c7-security-review | 7 | R1 | c7-j7-journey, c7-ai-log-screen, c7-index-changes, c7-eval-gate, c7-search-index, c7-ask-backend, c7-fe-console-eval-sets | local-unit | 60 | 15 | - |  |
| c7-review-fixes | 7 | R1 | c7-security-review | local-unit | 45 | 17 | - | yes |
| c7-chunk-close | 7 | R1 | c7-j7-journey, c7-ai-log-screen, c7-index-changes, c7-eval-gate, c7-review-fixes | local-e2e | 45 | 19 | - |  |
| c7-embedder-selection-baseline | 7 | R1 | c7-hybrid-search-backend, c7-eval-gate, c7-embedder-mock-reranker, k-embedder | local-unit | 60 | after key | embed ci eval deps |  |
| r1-perf | R1 | R1 | c14-perf-harness, c3-security-review, c4-security-review-2, c5-security-review, c6-security-review, c7-security-review, f03-security-review, h9-footprint-antijoin | local-e2e | 60 | 18 | - |  |
| r1-readiness | R1 | R1 | every other R1 package (the rel column), including every R1 f03 task, the reviews, their fixes and r1-perf | local-e2e | 60 | 20 | - |  |
| f03-T50 | 8 | R2 | p03-consolidation | cloud | 30 | 1 | - |  |
| c8-card-organisation | 8 | R2 | p03-consolidation | cloud | 45 | 1 | - |  |
| c8-tenants-contract | 8 | R2 | p03-consolidation | cloud | 50 | 1 | mig:tenants | yes |
| c8-register-api-contract | 8 | R2 | p03-consolidation | cloud | 50 | 1 | regapi | yes |
| f03-T60 | 8 | R2 | none | cloud | 50 | 2 | - |  |
| c8-card-obligation-register | 8 | R2 | p03-consolidation | cloud | 50 | 2 | - |  |
| c8-card-gaps | 8 | R2 | p03-consolidation | cloud | 45 | 2 | - |  |
| c8-card-people-access | 8 | R2 | q-support-access, p03-consolidation | local-unit (c) | 50 | 4 | - |  |
| c8-tenants-api-contract | 8 | R2 | c4-console-tenants-api | cloud | 40 | 5 | ten | yes |
| c8-ten-org-api | 8 | R2 | c8-tenants-contract, c8-tenants-api-contract | local-unit (c) | 55 | 6 | - |  |
| c8-ten-out-of-office | 8 | R2 | c8-tenants-api-contract | cloud | 40 | 7 | - |  |
| c8-ten-support-grants | 8 | R2 | c8-tenants-contract, c8-tenants-api-contract, q-support-access | cloud | 45 | 8 | mig:tenants | yes |
| c8-vocab-scales-reasons | 8 | R2 | c3-no-tone | cloud | 60 | 12 | taxreg mig:taxonomy taxseed | yes |
| c8-register-models | 8 | R2 | c8-tenants-contract, c8-vocab-scales-reasons | local-unit (c) | 60 | 14 | mig:register | yes |
| c8-reg-status | 8 | R2 | c8-register-models, c8-register-api-contract | local-unit (c) | 55 | 16 | regstatus |  |
| c8-e2e-seed-register | 8 | R2 | c8-register-models, c8-tenants-contract, c8-vocab-scales-reasons | local-unit (c) | 50 | 16 | - |  |
| c8-vocab-register-usage | 8 | R2 | c8-register-models, c8-vocab-scales-reasons | cloud | 35 | 17 | taxreg |  |
| c8-reg-applicability | 8 | R2 | c8-register-models, c8-register-api-contract | cloud | 50 | 17 | - | yes |
| c8-reg-gaps | 8 | R2 | c8-register-models, c8-register-api-contract, c8-vocab-scales-reasons | cloud | 55 | 17 | - |  |
| c8-reg-history-interpretation | 8 | R2 | c8-register-models, c8-register-api-contract | cloud | 45 | 17 | - |  |
| c8-reg-internal-links | 8 | R2 | c8-register-models, c8-register-api-contract | cloud | 50 | 17 | - |  |
| c8-ten-reassignment | 8 | R2 | c8-register-models, c8-tenants-contract, c8-tenants-api-contract | cloud | 55 | 17 | - | yes |
| c8-ui-organisation | 8 | R2 | c8-card-organisation, c8-ten-org-api, c8-e2e-seed-register, x-frontend-split | local-e2e (c) | 60 | 17 | orgscreen |  |
| c8-ui-out-of-office | 8 | R2 | c8-card-people-access, c8-ten-out-of-office, x-frontend-split | local-e2e (c) | 35 | 17 | - |  |
| c8-reg-entity-status | 8 | R2 | c8-reg-status, c8-tenants-contract | local-unit (c) | 50 | 18 | regstatus |  |
| c8-ten-teams | 8 | R2 | c8-tenants-contract, c8-tenants-api-contract, c8-reg-status | local-unit (c) | 40 | 18 | - |  |
| f03-T67 | 8 | R2 | c8-register-models, c8-reg-applicability, f03-T25 | local-unit (c) | 55 | 19 | mig:register reglogic | yes |
| c8-reg-risk-acceptance | 8 | R2 | c8-reg-gaps | local-unit (c) | 45 | 19 | - | yes |
| c8-reg-inventory-overlay-api | 8 | R2 | c3-provision-read, c8-reg-entity-status, c8-reg-applicability, c5-watch-feed-read | local-unit (c) | 45 | 19 | libread |  |
| c8-ui-teams | 8 | R2 | c8-card-organisation, c8-ten-teams, c8-ui-organisation | local-e2e (c) | 40 | 19 | orgscreen |  |
| f03-T51 | 8 | R2 | f03-T50, c8-tenants-contract, c8-ten-org-api, c8-ten-teams, c8-ui-teams | local-e2e (c) | 60 | 20 | mig:tenants ten idapi orgscreen | yes |
| c8-ui-applicability | 8 | R2 | c8-card-obligation-register, c8-reg-applicability, c8-reg-status, c3-fe-obligation-versions, c8-e2e-seed-register | local-e2e (c) | 55 | 20 | regfe |  |
| c8-ui-member-removal | 8 | R2 | c8-card-people-access, c8-ten-reassignment, c8-e2e-seed-register, x-frontend-split | local-e2e (c) | 50 | 20 | members |  |
| f03-T68 | 8 | R2 | f03-T67 | local-unit (c) | 50 | 21 | mig:register reglogic | yes |
| c8-recurring-duty-library | 8 | R2 | c3-close, c4-library-updates, c5-library-links-provenance, r1-readiness | local-unit | 45 | 21 | mig:library apply prop deps | yes |
| c8-ui-where-we-stand | 8 | R2 | c8-card-obligation-register, c8-reg-entity-status, c8-ten-teams, c8-ui-applicability, c8-e2e-seed-register | local-e2e (c) | 60 | 21 | regfe |  |
| f03-T53 | 8 | R2 | f03-T50, f03-T51, c8-register-models | local-unit (c) | 45 | 22 | mig:collab | yes |
| f03-T70 | 8 | R2 | f03-T68 | local-unit (c) | 50 | 22 | regapi reglogic | yes |
| c8-ui-history-interpretation | 8 | R2 | c8-card-obligation-register, c8-reg-history-interpretation, c8-ui-applicability, c8-e2e-seed-register | local-e2e (c) | 45 | 22 | regfe |  |
| c8-ui-inventory-overlay | 8 | R2 | c8-reg-inventory-overlay-api, c3-fe-instruments, c8-ui-where-we-stand | local-e2e (c) | 40 | 22 | invscreen |  |
| f03-T52 | 8 | R2 | f03-T51 | cloud | 35 | 23 | ten | yes |
| f03-T73 | 8 | R2 | f03-T68, c7-search-index, c7-hybrid-search-backend, c7-ai-log-backend | cloud | 40 | 23 | - |  |
| c8-reg-duty-occurrences | 8 | R2 | c8-recurring-duty-library, c8-register-models, c8-register-api-contract | local-unit (c) | 60 | 23 | mig:register | yes |
| c8-support-access-mechanism | 8 | R2 | c8-ten-support-grants, r1-readiness | cloud | 60 | 23 | auth | yes |
| c8-ui-internal-links | 8 | R2 | c8-card-obligation-register, c8-reg-internal-links, c8-ui-applicability, c8-e2e-seed-register | local-e2e (c) | 45 | 23 | regfe |  |
| f03-T54 | 8 | R2 | f03-T53 | local-unit (c) | 50 | 24 | collabcore reglogic | yes |
| f03-T66 | 8 | R2 | f03-T51, c8-tenants-contract, c8-ten-org-api | cloud | 55 | 24 | mig:tenants ten | yes |
| f03-T69 | 8 | R2 | f03-T68 | cloud | 50 | 24 | regapi |  |
| f03-T55 | 8 | R2 | f03-T54 | local-unit (c) | 50 | 25 | collabapi | yes |
| f03-T64 | 8 | R2 | f03-T54, f03-T51, c8-ten-reassignment, c8-ui-member-removal | local-unit (c) | 50 | 25 | members | yes |
| f03-T71 | 8 | R2 | f03-T69, f03-T70, c8-ui-where-we-stand, f03-T60 | local-e2e (c) | 60 | 25 | regfe |  |
| c8-home-register-feeds | 8 | R2 | c6-briefing-backend, c6-home-backend, c8-reg-gaps, c8-reg-duty-occurrences, c8-reg-entity-status, c8-reg-applicability, c8-reg-risk-acceptance | local-unit (c) | 45 | 25 | homecore |  |
| c8-ui-support-access | 8 | R2 | c8-card-people-access, c8-ten-support-grants, c8-support-access-mechanism, c4-console-shell | local-e2e (c) | 55 | 25 | - |  |
| c8-ui-gaps | 8 | R2 | c8-card-gaps, c8-reg-gaps, c8-ui-applicability, c8-e2e-seed-register, c8-home-register-feeds, c6-roadmap-screen | local-e2e (c) | 60 | 26 | regfe |  |
| c8-ui-home-register | 8 | R2 | c8-home-register-feeds, c6-roadmap-screen, c6-today-screen | local-e2e (c) | 45 | 26 | today |  |
| f03-T56 | 8 | R2 | f03-T55, c8-reg-entity-status, c8-reg-gaps, c8-reg-duty-occurrences, c8-reg-history-interpretation | local-unit (c) | 50 | 27 | mywork |  |
| f03-T74 | 8 | R2 | f03-T66, c6-roadmap-backend, c6-upcoming-calendar-backend, c8-reg-gaps, c8-reg-duty-occurrences | cloud | 50 | 27 | mig:home homecore |  |
| c8-ui-risk-acceptance | 8 | R2 | c8-ui-gaps, c8-reg-risk-acceptance | local-e2e (c) | 45 | 28 | regfe |  |
| f03-T57 | 8 | R2 | f03-T56 | local-unit (c) | 50 | 29 | mywork |  |
| f03-T72 | 8 | R2 | f03-T70, f03-T71 | local-e2e (c) | 55 | 29 | regapi reglogic regfe |  |
| f03-T58 | 8 | R2 | f03-T57 | local-unit (c) | 40 | 30 | mywork |  |
| f03-T75 | 8 | R2 | f03-T28, f03-T66, f03-T71, f03-T72, f03-T74 | local-e2e (c) | 45 | 30 | - |  |
| f03-T59 | 8 | R2 | f03-T58 | local-unit (c) | 45 | 31 | homecore | yes |
| f03-T61 | 8 | R2 | f03-T59, f03-T60 | local-unit (c) | 45 | 32 | workfe |  |
| f03-T63 | 8 | R2 | f03-T55, f03-T52, f03-T60, c8-ui-applicability | local-e2e (c) | 55 | 32 | collabfe regfe |  |
| f03-T62 | 8 | R2 | f03-T61 | local-e2e (c) | 55 | 33 | workfe |  |
| c8-security-review | 8 | R2 | c8-reg-status, c8-reg-entity-status, c8-reg-applicability, c8-reg-gaps, c8-reg-risk-acceptance, c8-reg-history-interpretation, c8-reg-internal-links, c8-reg-duty-occurrences, c8-reg-inventory-overlay-api, c8-ten-org-api, c8-ten-teams, c8-ten-out-of-office, c8-ten-reassignment, c8-ten-support-grants, c8-support-access-mechanism, and every chunk 8 f03 task marked SR | cloud | 60 | 33 | - |  |
| f03-T65 | 8 | R2 | f03-T62, f03-T63 | cloud+e2e | 45 | 36 | - |  |
| c8-review-fixes | 8 | R2 | c8-security-review | local-unit | 45 | 36 | - | yes |
| c8-close-out | 8 | R2 | c8-ui-applicability, c8-ui-where-we-stand, c8-ui-gaps, c8-ui-risk-acceptance, c8-ui-history-interpretation, c8-ui-internal-links, c8-ui-inventory-overlay, c8-ui-home-register, c8-ui-organisation, c8-ui-teams, c8-ui-out-of-office, c8-ui-member-removal, c8-ui-support-access, c8-vocab-register-usage, c8-review-fixes, f03-T65, f03-T75, f03-T64, f03-T73 | local-e2e | 60 | 37 | - |  |
| c9-case-design | 9 | R2 | none | cloud | 45 | 0 | - |  |
| c9-scanner-adapter | 9 | R2 | none | cloud | 40 | 0 | - | yes |
| c9-state-machine | 9 | R2 | none | cloud | 35 | 0 | - |  |
| c9-case-models | 9 | R2 | c5-contract-models-cases, c8-tenants-contract, f03-T51, f03-T53 | local-unit (c) | 60 | 24 | mig:cases | yes |
| c9-case-contract | 9 | R2 | c9-case-models, c9-state-machine, c5-cases-creation, c5-cases-so-what-and-links, c5-watch-feed-read, c5-cases-footprint-hooks, c5-chunk-close | local-unit (c) | 60 | 26 | casesapi watchapi | yes |
| c9-e2e-seed | 9 | R2 | c9-case-models, c5-seed-watch | cloud | 45 | 26 | - |  |
| c9-assessment | 9 | R2 | c9-case-contract | local-unit (c) | 50 | 27 | - |  |
| c9-fe-cases-feature | 9 | R2 | c9-case-contract, c9-case-design, c5-fe-change-detail | local-e2e (c) | 60 | 27 | changescreen casesfe |  |
| c9-triage | 9 | R2 | c9-case-contract, c10-collab-models | local-unit (c) | 45 | 28 | - |  |
| c9-actions | 9 | R2 | c9-case-contract, c8-ten-reassignment | local-unit (c) | 45 | 28 | - |  |
| c9-evidence | 9 | R2 | c9-case-contract, c9-scanner-adapter | local-unit (c) | 60 | 28 | casestasks | yes |
| c9-signoff | 9 | R2 | c9-case-contract, c10-collab-models | cloud | 45 | 28 | - | yes |
| c9-case-file | 9 | R2 | c9-case-contract | cloud | 45 | 28 | - |  |
| c9-fe-assessment-panel | 9 | R2 | c9-fe-cases-feature, c9-assessment | local-unit (c) | 45 | 29 | casesfe |  |
| f03-T76 | 9 | R2 | f03-T55, c9-triage, c9-assessment, c9-fe-assessment-panel | local-e2e (c) | 55 | 30 | collabapi casesfe collabfe caseslogic | yes |
| c9-case-file-export | 9 | R2 | c9-case-file, c12-exports-contract | local-unit (c) | 30 | 30 | - |  |
| f03-T77 | 9 | R2 | f03-T76, c9-actions, f03-T59 | local-unit (c) | 45 | 32 | mywork |  |
| c9-fe-triage-panel | 9 | R2 | c9-fe-cases-feature, c9-triage | local-unit (c) | 40 | 32 | casesfe |  |
| c9-fe-actions-panel | 9 | R2 | c9-fe-cases-feature, c9-actions | cloud | 45 | 33 | casesfe |  |
| c9-fe-evidence-panel | 9 | R2 | c9-fe-cases-feature, c9-evidence | cloud | 45 | 34 | casesfe |  |
| c9-fe-signoff-panel | 9 | R2 | c9-fe-cases-feature, c9-signoff | cloud | 45 | 35 | casesfe |  |
| c9-e2e-triage-journeys | 9 | R2 | c9-fe-triage-panel, c9-e2e-seed, c6-today-screen, c5-cases-so-what-and-links, f03-T77, f03-T62 | local-e2e (c) | 45 | 35 | - |  |
| c9-fe-case-file | 9 | R2 | c9-fe-cases-feature, c9-case-file, c9-case-file-export | local-unit (c) | 45 | 36 | casesfe |  |
| c9-e2e-work-journeys | 9 | R2 | c9-fe-assessment-panel, c9-fe-actions-panel, c9-fe-evidence-panel, c9-e2e-seed, c9-e2e-triage-journeys | local-e2e (c) | 50 | 36 | - |  |
| c9-e2e-signoff-journeys | 9 | R2 | c9-fe-signoff-panel, c9-fe-case-file, c9-e2e-seed, c9-e2e-work-journeys | local-e2e (c) | 55 | 37 | - |  |
| c9-security-review | 9 | R2 | c9-e2e-signoff-journeys, c9-case-file-export, c9-evidence, c9-signoff, f03-T76 | local-unit (c) | 45 | 39 | - |  |
| c9-review-fixes | 9 | R2 | c9-security-review | local-unit | 45 | 40 | - | yes |
| c9-close | 9 | R2 | c9-review-fixes, f03-T77 | local-e2e | 30 | 42 | - |  |
| c10-collab-design | 10 | R2 | none | cloud | 50 | 2 | - |  |
| c10-collab-models | 10 | R2 | p03-consolidation, c5-outbox-cursor | local-unit (c) | 60 | 2 | mig:collab collabcore | yes |
| c10-notifications-api | 10 | R2 | c10-collab-models | cloud | 40 | 4 | collabapi | yes |
| c10-comments-api | 10 | R2 | c10-notifications-api, c5-contract-models-cases | local-unit (c) | 55 | 6 | collabapi | yes |
| c10-workflow-policy | 10 | R2 | c10-collab-models, c8-tenants-api-contract | cloud | 40 | 8 | mig:shared ten | yes |
| c10-fe-collab-feature | 10 | R2 | c10-notifications-api, c10-comments-api, c10-collab-design, x-frontend-split | cloud | 45 | 9 | collabfe |  |
| c10-notification-prefs | 10 | R2 | c10-collab-models, c4-mark-seen, c6-home-backend | cloud | 35 | 10 | idapi |  |
| c10-mail-catalog | 10 | R2 | c10-collab-models, c6-briefing-backend | local-unit (c) | 45 | 12 | collabtasks |  |
| c10-tagging-api | 10 | R2 | c3-provision-read | cloud | 55 | 14 | libread |  |
| c10-delegation | 10 | R2 | c10-collab-models, c8-ten-out-of-office | local-unit (c) | 40 | 17 | collabcore | yes |
| c10-fe-suggest | 10 | R2 | c10-tagging-api, c10-fe-collab-feature, c4-fe-tenant-proposals, c3-fe-obligation-versions | local-e2e (c) | 55 | 17 | obpage vocabfe |  |
| c10-fe-bulk-tagging | 10 | R2 | c10-fe-suggest, c3-fe-instruments | local-e2e (c) | 45 | 18 | invscreen |  |
| c10-reminders-escalation | 10 | R2 | c10-mail-catalog, c10-workflow-policy, c10-notification-prefs, c9-case-models, c8-ten-teams, f03-T51 | local-unit (c) | 55 | 26 | collabtasks |  |
| f03-T78 | 10 | R2 | f03-T77, c10-reminders-escalation | local-unit (c) | 55 | 33 | mig:collab collabcore collabtasks | yes |
| f03-T80 | 10 | R2 | f03-T78, c10-comments-api, f03-T62 | local-e2e (c) | 55 | 35 | collabapi mywork workfe gates | yes |
| f03-T81 | 10 | R2 | f03-T78 | local-unit (c) | 40 | 35 | collabtasks |  |
| f03-T79 | 10 | R2 | f03-T78 | cloud | 40 | 36 | collabtasks |  |
| c10-digest | 10 | R2 | c10-mail-catalog, c10-workflow-policy, c10-notification-prefs, c10-reminders-escalation, f03-T81 | cloud | 50 | 37 | collabtasks |  |
| c10-e2e-seed | 10 | R2 | c9-e2e-seed, c10-reminders-escalation, c10-digest, c10-comments-api | local-unit (c) | 45 | 38 | - | yes |
| c10-fe-notifications | 10 | R2 | c10-fe-collab-feature, c10-notification-prefs, c10-e2e-seed, c4-console-shell | local-e2e (c) | 55 | 40 | collabfe |  |
| c10-fe-comments-panel | 10 | R2 | c10-fe-collab-feature, c10-fe-notifications, c9-case-contract, c5-fe-change-detail, c3-fe-obligation-versions, c10-e2e-seed | local-e2e (c) | 55 | 41 | changescreen obpage collabfe |  |
| c10-fe-workflow-policy | 10 | R2 | c10-fe-collab-feature, c10-workflow-policy, c10-fe-notifications | local-e2e (c) | 40 | 41 | - |  |
| c10-j8-extension | 10 | R2 | c8-support-access-mechanism, c9-e2e-seed, c10-e2e-seed, c9-fe-evidence-panel, c10-fe-comments-panel | local-e2e (c) | 30 | 42 | - |  |
| c10-security-review | 10 | R2 | c10-fe-notifications, c10-fe-comments-panel, c10-fe-workflow-policy, c10-fe-bulk-tagging, c10-delegation, c10-j8-extension, f03-T78, f03-T80 | local-unit (c) | 45 | 43 | - |  |
| c10-review-fixes | 10 | R2 | c10-security-review | local-unit | 45 | 44 | - | yes |
| c10-close | 10 | R2 | c10-review-fixes, f03-T79, f03-T80, f03-T81 | local-e2e | 30 | 45 | - |  |
| c11-runner-adapter | 11 | R2 | none | cloud | 40 | 0 | runner | yes |
| c11-cards-agents | 11 | R2 | none | cloud | 50 | 1 | - |  |
| c11-cards-security-batch | 11 | R2 | none | cloud | 45 | 2 | - |  |
| c11-security-policy | 11 | R2 | none | cloud | 50 | 6 | mig:tenants ten | yes |
| c11-fe-admin-security | 11 | R2 | c11-security-policy, c11-cards-security-batch, x-frontend-split | cloud+e2e | 55 | 9 | - |  |
| c11-agent-definitions-contract | 11 | R2 | c5-contract-models-agents, c5-contract-api-agent, c5-agent-api-flow | cloud | 45 | 16 | mig:agents agentsapi | yes |
| c11-tenant-agents-contract | 11 | R2 | c11-agent-definitions-contract, c5-contract-models-watch, p03-consolidation | local-unit (c) | 60 | 18 | mig:agents agentsapi | yes |
| c11-agent-definitions | 11 | R2 | c11-agent-definitions-contract | local-unit (c) | 45 | 18 | - |  |
| c11-tenant-agent-controls | 11 | R2 | c11-tenant-agents-contract, c7-ask-switch | local-unit (c) | 60 | 19 | - | yes |
| c11-run-history | 11 | R2 | c11-tenant-agents-contract | local-unit (c) | 30 | 20 | - |  |
| c11-fe-console-agent-definitions | 11 | R2 | c11-agent-definitions-contract, c11-cards-agents, c4-console-shell, c11-agent-definitions, x-frontend-split | local-unit (c) | 50 | 20 | - |  |
| c11-run-scheduler | 11 | R2 | c11-tenant-agents-contract, c11-agent-definitions, c11-tenant-agent-controls, c11-runner-adapter, c11-run-history, c10-notifications-api | local-unit (c) | 60 | 21 | agentstasks | yes |
| c11-fe-admin-agents | 11 | R2 | c11-tenant-agents-contract, c11-cards-agents, c11-tenant-agent-controls | local-unit (c) | 60 | 21 | agentsfe |  |
| c11-fe-agents-budget-ai | 11 | R2 | c11-fe-admin-agents | local-unit (c) | 45 | 22 | agentsfe |  |
| c11-batch-proposals-contract | 11 | R2 | c4-library-updates, c5-library-links-provenance, r1-readiness | cloud | 50 | 23 | mig:proposals prop | yes |
| c11-credential-policy | 11 | R2 | c11-security-policy, q-credential, r1-readiness | cloud | 60 | 23 | idp | yes |
| c11-ai-off-switch | 11 | R2 | c11-tenant-agent-controls, c11-run-scheduler, c7-ask-backend, c7-ask-screen | local-unit (c) | 30 | 23 | searchscreen | yes |
| f03-T82 | 11 | R2 | f03-T19, c11-tenant-agent-controls, c11-run-scheduler | cloud | 50 | 24 | mig:agents | yes |
| c11-batch-proposals | 11 | R2 | c11-batch-proposals-contract, c4-approve-apply | local-unit (c) | 60 | 24 | apply prop | yes |
| c11-platform-runs | 11 | R2 | c11-run-scheduler, c5-watch-sources-coverage, c5-fe-console-sources | cloud | 45 | 24 | agentsapi | yes |
| c11-session-policy | 11 | R2 | c11-security-policy, r1-readiness | cloud | 30 | 25 | idp | yes |
| c11-research-requests | 11 | R2 | c11-tenant-agents-contract, c11-run-scheduler, c11-batch-proposals, c5-watch-sources-coverage | local-unit (c) | 60 | 27 | - | yes |
| c11-e2e-seed | 11 | R2 | c11-agent-definitions, c11-batch-proposals, c11-tenant-agents-contract, c3-seed-provisions | cloud | 45 | 27 | - |  |
| c11-fe-console-batch-review | 11 | R2 | c11-batch-proposals-contract, c11-cards-security-batch, c11-batch-proposals, c11-e2e-seed, c4-fe-approve | local-e2e (c) | 60 | 28 | consoleq |  |
| c11-e2e-agent-controls | 11 | R2 | c11-fe-admin-agents, c11-fe-agents-budget-ai, c11-tenant-agent-controls, c11-run-scheduler, c11-run-history, c11-ai-off-switch, c11-e2e-seed | local-e2e (c) | 50 | 28 | - |  |
| c11-fe-research-requests | 11 | R2 | c11-tenant-agents-contract, c11-cards-agents, c11-research-requests | cloud | 50 | 30 | - |  |
| c11-e2e-definitions-requests | 11 | R2 | c11-e2e-agent-controls, c11-fe-research-requests, c11-fe-console-agent-definitions, c11-agent-definitions, c11-research-requests, c11-e2e-seed | local-e2e (c) | 50 | 31 | - |  |
| c11-security-review | 11 | R2 | c11-e2e-definitions-requests, c11-fe-console-batch-review, c11-fe-admin-security, c11-session-policy, c11-credential-policy, c11-platform-runs, c11-run-scheduler, c11-research-requests, f03-T82 | local-unit | 60 | 32 | - |  |
| c11-review-fixes | 11 | R2 | c11-security-review | local-unit | 45 | 35 | - | yes |
| c11-chunk-close | 11 | R2 | c11-e2e-definitions-requests, c11-fe-console-batch-review, c11-fe-admin-security, c11-session-policy, c11-credential-policy, c11-platform-runs, c11-review-fixes, f03-T82 | local-e2e | 60 | 37 | - |  |
| c11-runner-managed-agents | 11 | R2 | c11-runner-adapter, c11-run-scheduler, k-managed-agents | local-unit | 60 | after key | runner | yes |
| adm-lang-jur-kinds | ADM | R2 | c4-approve-apply, f03-T16 | cloud | 55 | 16 | prop apply libread taxseed | yes |
| adm-fe-lang-jur | ADM | R2 | adm-lang-jur-kinds, c4-console-shell, c4-fe-approve | cloud+e2e | 50 | 19 | consoleq |  |
| c12-card-reports | 12 | R3 | none | cloud | 45 | 2 | - |  |
| c12-exports-contract | 12 | R3 | none | cloud | 60 | 2 | reportscore mig:reports | yes |
| c12-card-data | 12 | R3 | none | cloud | 60 | 3 | - |  |
| c12-config-logic | 12 | R3 | c3-no-tone | cloud | 60 | 3 | taxapi |  |
| c12-export-audit-log | 12 | R3 | c12-exports-contract | cloud | 40 | 6 | - |  |
| c12-retention-contract | 12 | R3 | c5-ai-log-contract, c7-ai-log-backend, c4-close-a, q-retention | cloud | 45 | 18 | mig:governance gov | yes |
| c12-config-policies | 12 | R3 | c12-config-logic, c10-workflow-policy, c11-security-policy, c12-retention-contract | local-unit (c) | 40 | 20 | taxapi |  |
| c12-fe-data-retention | 12 | R3 | c12-card-data, c12-retention-contract | cloud+e2e | 40 | 21 | datafe |  |
| c12-tenant-deleted-status | 12 | R3 | c5-contract-models-agents, r1-readiness | local-unit (c) | 30 | 22 | mig:shared auth idp | yes |
| c12-exit-deletion | 12 | R3 | c12-exports-contract, c12-tenant-deleted-status, q-exit | local-unit (c) | 60 | 23 | reportscore mig:reports | yes |
| c12-deps-spreadsheets | 12 | R3 | r1-readiness | local-unit | 30 | 29 | deps |  |
| c12-dashboard-api | 12 | R3 | c12-exports-contract, c9-actions, c9-assessment, c8-reg-gaps, c8-reg-entity-status, c8-ten-teams, c5-cases-so-what-and-links, c5-watch-feed-read | local-unit (c) | 60 | 29 | reportscore |  |
| c12-export-inventory | 12 | R3 | c12-exports-contract, c3-provision-read, c8-reg-entity-status, c12-deps-spreadsheets | local-unit (c) | 45 | 30 | - |  |
| c12-export-changes-cases | 12 | R3 | c12-exports-contract, c5-cases-so-what-and-links, c9-assessment, c9-actions, c9-evidence, c9-signoff | local-unit (c) | 60 | 30 | - |  |
| c12-imports-contract | 12 | R3 | c12-exports-contract, c9-scanner-adapter, c12-deps-spreadsheets | cloud | 60 | 31 | reportscore mig:reports | yes |
| c12-retention-purge | 12 | R3 | c12-retention-contract, c10-notifications-api, c9-evidence | cloud | 60 | 31 | - | yes |
| c12-exit-export | 12 | R3 | c12-exit-deletion, c12-export-inventory, c12-export-changes-cases, c12-export-audit-log, c12-config-logic, c9-evidence, c9-case-file-export, c10-comments-api | local-unit (c) | 60 | 31 | - |  |
| c12-fe-reports-dashboard | 12 | R3 | c12-card-reports, c12-dashboard-api, c9-e2e-seed, c8-e2e-seed-register | local-e2e (c) | 60 | 31 | reportsfe |  |
| c12-committee-pack | 12 | R3 | c12-dashboard-api, c12-export-inventory, c12-export-changes-cases, c12-export-audit-log, c6-roadmap-backend, c5-watch-sources-coverage, c10-mail-catalog | cloud | 50 | 33 | reportscore |  |
| c12-config-jobs | 12 | R3 | c12-config-logic, c12-exports-contract, c12-imports-contract | local-unit (c) | 30 | 33 | - | yes |
| c12-import-register | 12 | R3 | c12-imports-contract, c8-reg-status, c8-reg-entity-status, c8-reg-applicability, c8-ten-teams, c3-provision-read | local-unit (c) | 60 | 33 | - | yes |
| f03-T83 | 12 | R3 | f03-T72, c12-exports-contract, c12-export-inventory | cloud | 50 | 34 | reportscore | yes |
| c12-fe-exports | 12 | R3 | c12-fe-reports-dashboard, c12-committee-pack, c12-export-inventory, c12-export-changes-cases, c12-export-audit-log, c4-fe-audit-log | local-e2e (c) | 60 | 34 | reportsfe |  |
| c12-fe-data-import | 12 | R3 | c12-card-data, c12-imports-contract, c12-import-register, c8-e2e-seed-register | local-e2e (c) | 60 | 34 | datafe |  |
| c12-security-review | 12 | R3 | c12-exports-contract, c12-imports-contract, c12-import-register, c12-retention-purge, c12-tenant-deleted-status, c12-exit-deletion, c12-exit-export, c12-config-jobs | local-unit (c) | 60 | 34 | - |  |
| c12-fe-data-exit | 12 | R3 | c12-card-data, c12-exit-export, c12-exit-deletion, c12-tenant-deleted-status, c12-fe-exports | cloud+e2e | 60 | 36 | datafe |  |
| c12-review-fixes | 12 | R3 | c12-security-review | local-unit | 45 | 36 | - | yes |
| c12-fe-data-configuration | 12 | R3 | c12-card-data, c12-config-jobs, c12-fe-exports | local-e2e (c) | 45 | 38 | datafe |  |
| c12-close | 12 | R3 | c12-fe-reports-dashboard, c12-fe-exports, c12-fe-data-import, c12-fe-data-configuration, c12-fe-data-retention, c12-fe-data-exit, c12-config-policies, c12-review-fixes, f03-T83 | local-e2e | 45 | 39 | - |  |
| c13-cards-admin | 13 | R3 | none | cloud | 60 | 3 | - |  |
| c13-cards-tenant-other | 13 | R3 | c9-case-design | cloud | 50 | 3 | - |  |
| c13-cards-tenant-register | 13 | R3 | c8-card-obligation-register | cloud | 50 | 6 | - |  |
| c13-follow-contract | 13 | R3 | c3-provision-read, c10-collab-models | cloud | 45 | 10 | mig:collab collabapi | yes |
| c13-saved-search-contract | 13 | R3 | c7-hybrid-search-backend, c7-search-index | cloud | 50 | 12 | mig:search searchapi | yes |
| c13-fe-saved-searches | 13 | R3 | c13-saved-search-contract, c7-ask-screen, c13-cards-tenant-other | cloud | 50 | 18 | searchscreen |  |
| c13-i18n-seed-labels | 13 | R3 | every package that seeds a vocabulary or library list (keys taxseed or seedlib) | local-unit (c) | 45 | 19 | taxseed seedlib |  |
| c13-fe-follow | 13 | R3 | c13-follow-contract, c3-fe-instruments, c13-cards-tenant-register | local-unit (c) | 40 | 19 | obpage |  |
| c13-egress-client | 13 | R3 | r1-readiness | local-unit | 50 | 23 | deps | yes |
| c13-secret-box | 13 | R3 | c13-egress-client, r1-readiness | local-unit | 50 | 25 | deps | yes |
| c13-reg06-attestations | 13 | R3 | c8-register-models, c8-ten-teams, c6-roadmap-backend, c8-reg-duty-occurrences, c8-home-register-feeds | local-unit (c) | 60 | 26 | mig:register homecore | yes |
| c13-int-contract | 13 | R3 | c13-secret-box, c13-egress-client, c5-outbox-cursor | local-unit (c) | 60 | 27 | mig:integrations intapi | yes |
| c13-ip-allowlist | 13 | R3 | c11-security-policy, r1-readiness | cloud | 60 | 27 | mig:tenants ten auth idp | yes |
| c13-sso-domains | 13 | R3 | q-sso, r1-readiness | local-unit | 50 | 27 | mig:identity idapi deps | yes |
| c13-private-contract | 13 | R3 | c5-contract-models-watch, c5-fe-console-sources, c4-proposal-kind, c5-library-links-provenance, q-private, r1-readiness | cloud | 60 | 27 | mig:watch mig:proposals watchapi prop | yes |
| c13-sso-idp-contract | 13 | R3 | c13-sso-domains, c13-secret-box, c13-egress-client | local-unit (c) | 45 | 28 | mig:identity idapi | yes |
| c13-reg06-waivers | 13 | R3 | c13-reg06-attestations, c8-reg-gaps | cloud | 50 | 28 | - |  |
| c13-siem-stream | 13 | R3 | c13-int-contract | cloud | 55 | 29 | inttasks | yes |
| c13-tickets-export | 13 | R3 | c13-int-contract, c9-actions | local-unit (c) | 60 | 29 | mig:integrations intapi | yes |
| c13-library-change-fanout | 13 | R3 | c13-int-contract, c4-approve-apply, c10-collab-models | cloud | 45 | 29 | collabtasks | yes |
| c13-fe-integrations-screen | 13 | R3 | c13-int-contract, c13-cards-admin | cloud | 60 | 29 | intfe |  |
| c13-sso-oidc | 13 | R3 | c13-sso-idp-contract, q-sso, r1-readiness | local-unit | 60 | 30 | idapi idp deps | yes |
| c13-private-sources | 13 | R3 | c13-private-contract, c11-research-requests, c11-run-scheduler, c5-watch-registration, c5-cases-creation | cloud | 60 | 30 | - | yes |
| c13-private-obligations | 13 | R3 | c13-private-contract, c4-approve-apply, c7-search-index, q-private | cloud | 60 | 30 | apply prop mig:search | yes |
| c13-fe-allowlist | 13 | R3 | c13-ip-allowlist, c13-cards-admin, c11-fe-admin-security | cloud | 45 | 30 | - |  |
| c13-webhook-delivery | 13 | R3 | c13-int-contract, c9-signoff, c5-watch-registration | cloud | 60 | 31 | inttasks | yes |
| c13-follow-notify | 13 | R3 | c13-follow-contract, c13-library-change-fanout, c10-notifications-api | local-unit (c) | 40 | 31 | - |  |
| c13-saved-search-notify | 13 | R3 | c13-saved-search-contract, c13-library-change-fanout, c10-notifications-api | local-unit (c) | 45 | 31 | - |  |
| c13-fe-attest-waive | 13 | R3 | c13-reg06-waivers, c8-ui-where-we-stand, c8-ui-risk-acceptance, c13-cards-tenant-register | cloud | 60 | 31 | obpage |  |
| c13-scim | 13 | R3 | c13-sso-oidc | local-unit (c) | 60 | 32 | idkeys | yes |
| c13-e2e-register | 13 | R3 | c13-fe-attest-waive | local-e2e (c) | 45 | 32 | - |  |
| c13-tickets-inbound | 13 | R3 | c13-tickets-export, c13-webhook-delivery | local-unit (c) | 50 | 33 | intapi | yes |
| c13-fe-source-requests | 13 | R3 | c13-private-contract, c5-fe-watch-feed, c3-fe-instruments, c13-cards-tenant-other, c13-cards-tenant-register, c13-private-sources | cloud | 60 | 33 | - |  |
| c13-fe-console-source-requests | 13 | R3 | c13-private-contract, c5-fe-console-sources, c4-console-shell, c13-cards-tenant-other, c13-private-sources | cloud | 45 | 33 | - |  |
| c13-tickets-jira | 13 | R3 | c13-tickets-inbound | local-unit (c) | 45 | 34 | - |  |
| c13-sso-saml | 13 | R3 | c13-sso-idp-contract, c13-scim, q-sso, r1-readiness | local-unit | 60 | 34 | idapi deps | yes |
| c13-fe-sso | 13 | R3 | c13-sso-domains, c13-sso-idp-contract, c13-sso-oidc, c13-scim, c13-cards-admin, c13-cards-tenant-other | local-unit (c) | 60 | 34 | - |  |
| c13-e2e-private | 13 | R3 | c13-private-sources, c13-private-obligations, c13-fe-source-requests, c13-fe-console-source-requests | local-e2e (c) | 60 | 34 | - |  |
| c13-security-review | 13 | R3 | c13-egress-client, c13-secret-box, c13-int-contract, c13-webhook-delivery, c13-siem-stream, c13-tickets-inbound, c13-tickets-jira, c13-ip-allowlist, c13-sso-oidc, c13-scim, c13-sso-saml, c13-follow-notify, c13-saved-search-notify, c13-reg06-waivers, c13-private-sources, c13-private-obligations | local-unit (c) | 60 | 35 | - |  |
| c13-e2e-identity-admin | 13 | R3 | c13-fe-allowlist, c13-fe-sso | local-e2e (c) | 50 | 36 | - |  |
| c13-fe-tickets-screen | 13 | R3 | c13-tickets-export, c13-fe-integrations-screen, c9-fe-actions-panel, c13-cards-tenant-other | cloud | 50 | 37 | intfe casesfe |  |
| c13-review-fixes | 13 | R3 | c13-security-review | local-unit | 45 | 37 | - | yes |
| c13-e2e-integrations | 13 | R3 | c13-webhook-delivery, c13-siem-stream, c13-tickets-inbound, c13-fe-integrations-screen, c13-fe-tickets-screen | local-e2e (c) | 60 | 38 | - |  |
| c13-i18n-server | 13 | R3 | c10-mail-catalog, c6-briefing-backend, c12-committee-pack, f03-T79 | cloud | 55 | 38 | mig:identity idapi collabtasks |  |
| c13-e2e-saved-searches | 13 | R3 | c13-saved-search-notify, c13-fe-saved-searches, c10-fe-notifications, c4-fe-approve | local-e2e (c) | 45 | 42 | - |  |
| c13-e2e-follow | 13 | R3 | c13-follow-notify, c13-fe-follow, c10-fe-notifications, c4-fe-approve | local-e2e (c) | 45 | 42 | - |  |
| c13-i18n-da | 13 | R3 | every R2 and R3 screen package (61 packages: the catalog freeze) | local-unit (c) | 45 | 42 | - |  |
| c13-i18n-nb | 13 | R3 | every R2 and R3 screen package (61 packages: the catalog freeze) | local-unit (c) | 45 | 42 | - |  |
| c13-i18n-fi | 13 | R3 | every R2 and R3 screen package (61 packages: the catalog freeze) | local-unit (c) | 45 | 42 | - |  |
| c13-i18n-wiring | 13 | R3 | c13-i18n-da, c13-i18n-nb, c13-i18n-fi, c13-i18n-seed-labels, c13-i18n-server | local-e2e (c) | 50 | 43 | - |  |
| c13-close | 13 | R3 | c13-e2e-integrations, c13-e2e-identity-admin, c13-e2e-saved-searches, c13-e2e-follow, c13-e2e-register, c13-e2e-private, c13-i18n-wiring, c13-review-fixes, c13-i18n-server | local-e2e | 45 | 44 | - |  |
| c14-perf-harness | 14 | R1 | none | local-unit (c) | 60 | 0 | - |  |
| c14-cards-console-usage | 14 | R3 | none | cloud | 50 | 3 | - |  |
| c14-owasp-scope | 14 | R3 | none | cloud | 30 | 3 | - |  |
| c14-shared-scenarios | 14 | R3 | c3-no-tone | cloud | 50 | 4 | - |  |
| c14-assurance-locations | 14 | R3 | none | cloud | 60 | 4 | - |  |
| c14-assurance-continuity | 14 | R3 | none | cloud | 60 | 4 | - |  |
| c14-billing-contract | 14 | R3 | c4-console-tenants-api | cloud | 60 | 5 | mig:billing mig:shared | yes |
| c14-eu-data-location | 14 | R3 | q-eu-guards, r1-readiness | local-unit (c) | 45 | 22 | bootguard | yes |
| c14-job-runs | 14 | R3 | r1-readiness | local-unit | 55 | 25 | auth mig:shared | yes |
| c14-billing-limits | 14 | R3 | c14-billing-contract, c11-tenant-agent-controls, c9-evidence, c12-exports-contract, c8-ten-reassignment | cloud | 60 | 31 | - |  |
| c14-billing-usage | 14 | R3 | c14-billing-contract, c7-ai-log-backend, c11-run-scheduler, c9-evidence, c12-exports-contract, q-platform-counters | cloud | 60 | 31 | mig:billing | yes |
| c14-assurance-exit-controls | 14 | R3 | c12-exit-deletion, c12-exit-export, c13-siem-stream, c13-ip-allowlist, c13-sso-oidc, c8-support-access-mechanism | cloud | 60 | 34 | - |  |
| c14-fe-console-plans | 14 | R3 | c14-billing-contract, c4-fe-tenants, c14-cards-console-usage, c14-billing-usage | cloud | 60 | 34 | - |  |
| c14-fe-usage | 14 | R3 | c14-billing-contract, c14-cards-console-usage, c14-billing-usage | cloud | 45 | 34 | - |  |
| c14-health-backend | 14 | R3 | c13-int-contract, c11-run-scheduler, c12-exports-contract, c13-webhook-delivery, c13-siem-stream, c5-watch-sources-coverage, c5-agent-runs, q-platform-counters, c14-job-runs | local-unit (c) | 60 | 34 | gov | yes |
| c14-fe-health | 14 | R3 | c14-health-backend, c14-cards-console-usage, c4-console-shell, c14-job-runs | local-unit (c) | 45 | 35 | - |  |
| c14-runbooks | 14 | R3 | c13-secret-box, c13-webhook-delivery, c13-siem-stream, c14-health-backend | cloud | 45 | 36 | - |  |
| c14-e2e-billing | 14 | R3 | c14-fe-console-plans, c14-fe-usage, c14-billing-usage | local-e2e (c) | 45 | 36 | - |  |
| c14-e2e-health | 14 | R3 | c14-fe-health | local-e2e (c) | 45 | 36 | - |  |
| c14-owasp-auth | 14 | R3 | c14-owasp-scope, c13-sso-saml, c13-scim, c13-ip-allowlist, c11-credential-policy, c11-session-policy | cloud | 60 | 36 | - |  |
| c14-owasp-access | 14 | R3 | c14-owasp-scope, c13-private-obligations, c13-private-sources, c14-billing-usage, c14-health-backend, c8-support-access-mechanism, c12-exit-deletion | cloud | 60 | 36 | - |  |
| c14-owasp-fixes-auth | 14 | R3 | c14-owasp-auth | local-unit | 60 | 38 | - | yes |
| c14-owasp-fixes-access | 14 | R3 | c14-owasp-access | local-unit | 60 | 38 | - | yes |
| c14-owasp-library-ai | 14 | R3 | c14-owasp-scope, c11-chunk-close, c7-chunk-close, c13-private-obligations | local-unit (c) | 60 | 38 | - |  |
| c14-perf-search-home | 14 | R3 | c14-perf-harness, c6-chunk-close, c7-chunk-close, c8-close-out | local-unit (c) | 60 | 39 | - |  |
| c14-owasp-fixes-library-ai | 14 | R3 | c14-owasp-library-ai | local-unit | 60 | 39 | - | yes |
| c14-owasp-files-data | 14 | R3 | c14-owasp-scope, c12-close | local-unit (c) | 60 | 40 | - |  |
| c14-owasp-integrations-web | 14 | R3 | c14-owasp-scope, c13-e2e-integrations, c13-tickets-jira, c13-fe-sso | local-e2e (c) | 60 | 40 | - |  |
| c14-owasp-fixes-files-data | 14 | R3 | c14-owasp-files-data | local-unit | 60 | 41 | - | yes |
| c14-owasp-fixes-integrations-web | 14 | R3 | c14-owasp-integrations-web | local-unit | 60 | 41 | - | yes |
| c14-perf-register-cases | 14 | R3 | c14-perf-harness, c8-close-out, c9-close | local-unit (c) | 60 | 43 | - |  |
| c14-owasp-converge | 14 | R3 | c14-owasp-fixes-auth, c14-owasp-fixes-access, c14-owasp-fixes-library-ai, c14-owasp-fixes-files-data, c14-owasp-fixes-integrations-web | local-unit (c) | 45 | 43 | - |  |
| c14-perf-core | 14 | R3 | c14-perf-harness, c4-close-b, c11-chunk-close, c13-close | local-unit (c) | 60 | 45 | - |  |
| c14-perf-library-watch | 14 | R3 | c14-perf-harness, c3-close, c5-chunk-close, c13-close | local-unit (c) | 60 | 45 | - |  |
| c14-perf-rest | 14 | R3 | c14-perf-harness, c10-close, c11-chunk-close, c12-close, c14-billing-usage, c14-health-backend | local-unit (c) | 60 | 46 | - |  |
| c14-perf-screens | 14 | R3 | c14-perf-core, c14-perf-library-watch, c14-perf-register-cases, c14-perf-search-home, c14-perf-rest, c13-i18n-wiring, c14-fe-health, c14-fe-usage, c14-fe-console-plans | local-e2e (c) | 60 | 47 | - |  |
| c14-close | 14 | R3 | c14-owasp-converge, c14-perf-screens, c14-e2e-billing, c14-e2e-health, c14-assurance-locations, c14-assurance-continuity, c14-assurance-exit-controls, c14-runbooks, c14-eu-data-location, c14-shared-scenarios, c14-billing-limits | local-e2e | 45 | 48 | - |  |

### 3.4 Serialization keys

A key stands for files that only one running package may edit. Append ledgers (rule 5) are not keys.

The keys of the chunk 3, chunk 4 and PRD 0.3 packages come from their owned paths. The keys of the built branches come from their diffs. The chunk 5 to 14 maps are not in the repository, so their keys come from the maps, and rule 1's dispatch check compares their owned paths before each start.

| Key | Files |
|---|---|
| `mig:<app>` | `backend/apps/<app>/models.py` and `migrations/`. `mig:shared` is the models in `apps/shared`: Tenant, the outbox cursor and `job_run` |
| `libread` | library `api.py`, `schemas.py`, `reading.py`, `testing.py`, `logic.py`, `tests_reading.py` |
| `libfe` | `frontend/src/features/library/` and the library catalog namespace |
| `prop`, `apply` | proposals `logic.py`, `schemas.py`, `api.py`, `standards.py`; `proposals/apply.py` |
| `fence` | `backend/apps/shared/tests_library_fence.py` and its allowlists |
| `auth` | `backend/apps/shared/authentication.py`, `tenancy.py`, `middleware.py` |
| `bootguard` | the production boot guard in `backend/config/settings.py` and `tests_production_guard.py` |
| `idp`, `idapi`, `idkeys` | identity `passkey_logic.py`, `session_logic.py`, `code_logic.py`, `invitation_logic.py`; identity `api.py`, `schemas.py`, `me_logic.py`; identity `api_keys_logic.py` |
| `roles`, `members` | identity `roles_logic.py` and the permission descriptions in `permissions.py`; identity `members_logic.py` and `components/admin/MemberDetailScreen.tsx` |
| `gov`, `ten` | governance `api.py`, `logic.py`, `schemas.py`; tenants `api.py`, `logic.py`, `schemas.py` |
| `taxreg`, `taxapi`, `fp`, `taxhttp`, `match`, `liblists`, `taxseed` | taxonomy `registry.py`; `api.py` and `schemas.py`; `footprint_logic.py` and `tenant_hooks.py`; `http.py`; `matching.py`; `library_lists_logic.py`; `seeds/__init__.py` |
| `shschema` | `backend/apps/shared/schemas.py` |
| `seedlib` | `backend/apps/library/seeds/` and `library/fixtures/` |
| `watchapi`, `casesapi`, `agentsapi`, `searchapi`, `intapi`, `regapi` | that app's `api.py` and `schemas.py` |
| `watchwrite` | `watch/registration.py` and `watch/curation.py`, and `watch/logic.py` until chunk 5 splits it |
| `homecore`, `reportscore`, `regstatus`, `reglogic`, `mywork`, `caseslogic` | home `logic.py`, `api.py`, `schemas.py`; reports `api.py`, `schemas.py`, `tasks.py`; `register/status_logic.py`; `register/logic.py`; `home/my_work.py`; `cases/logic.py` |
| `collabcore`, `collabapi`, `collabtasks` | collab `logic.py`; collab `api.py`, `schemas.py`; collab `tasks.py` |
| `casestasks`, `inttasks`, `agentstasks` | that app's `tasks.py` |
| `llm`, `embed`, `runner` | `shared/adapters/llm.py`; `embedder.py` and `reranker.py`; `agent_runner.py` |
| `sweeper` | `agents/watch-sweeper/v1/` |
| `eval` | `backend/eval/` and `backend/scripts/search_eval.py` |
| `ci` | `.github/workflows/`, `scripts/prepush.sh`, `scripts/ship.sh`. Local only |
| `gates` | `backend/scripts/requirements_coverage.py`, `compliance_check.py`, `contract_drift.py` |
| `deps` | `backend/pyproject.toml` and `poetry.lock`, `frontend/package.json` and `package-lock.json`. One dependency change at a time, local only |
| `cat` | `frontend/src/messages/en.json` and `sv.json`, until `x-frontend-split` lands |
| `uiprim` | `components/ui/{Button,PageHead,Field}.tsx`, `styles/theme.css`, `styles/contrast.test.ts` |
| `obpage`, `invscreen`, `changescreen`, `today`, `searchscreen`, `orgscreen`, `fpscreen` | the screen component of the obligation page, the inventory, the change page, Today, search, admin organisation and admin Regulatory scope, each with its catalog namespace |
| `consoleq`, `libupd`, `vocabfe`, `agentsfe`, `reportsfe`, `intfe` | the screen component of the console queue detail, library updates, the vocabulary screen and picker, admin agents, reports and admin integrations, each with its catalog namespace |
| `shellfe`, `casesfe`, `regfe`, `watchfe`, `collabfe`, `workfe`, `datafe` | `components/shell/` and the nav namespace; `features/cases/`, the case page and the cases namespace; `features/register/` and its namespace; `features/watch/` and its namespace; `features/collab/` and its namespace; `features/my-work/` and `components/work/`; the admin data screens and their namespace |

## 4. Waves

The waves come from the plan's simulated schedule, a run with no noise that applies every rule of sections 1 and 2:
- R1 packages first;
- then the package with the longest chain still behind it;
- the lane limits and the memory rule;
- keys held from start to merge, with R1's first claim;
- cloud packages starting only from shipped work;
- two merge slots;
- Alex's decisions in by hour 6.

A wave is a 75-minute window. A package sits in the wave in which it starts. The three packages that wait for a key are not in any wave.

| Wave | Starts about hour | Packages |
|---|---|---|
| W0 | 0.0 | local-e2e: c4-second-editor<br>local-unit: p03-consolidation, x-frontend-split, c14-perf-harness, f03-T22, c5-contract-models-watch, ci-e2e-shards<br>cloud: c4-proposal-kind, c5-contract-api-agent, c7-search-api-contract, f03-T15, f03-T34, c5-outbox-cursor, f03-T44, c9-state-machine, f03-T39, c9-case-design, c11-runner-adapter, c9-scanner-adapter |
| W1 | 1.2 | local-e2e: c3-seed-provisions, c3-fe-inventory, c4-fe-audit-log<br>local-unit: h-a-guards, c3-obligation-detail-read, c3-reports-verify-logic, c5-contract-api-screens<br>cloud: c8-tenants-contract, f03-T18, c8-register-api-contract, c8-card-organisation, c11-cards-agents, f03-T50, c4-mark-seen |
| W2 | 2.5 | local-e2e: f03-T04<br>local-unit: c4-console-tenants-api, c10-collab-models, c5-contract-models-cases, f03-T25, c4-seed-proposals<br>cloud+e2e: f03-T05<br>cloud: c12-exports-contract, c8-card-obligation-register, f03-T60, c10-collab-design, c12-card-reports, c8-card-gaps, c11-cards-security-batch, f03-T01 |
| W3 | 3.8 | local-e2e: c3-fe-obligation-card, c7-ask-switch, c4-fe-tenants<br>local-unit: h9-footprint-antijoin, c4-approve-apply, c6-home-api-contract, f03-T06<br>cloud: c12-config-logic, c13-cards-admin, c12-card-data, c5-fe-copy-nav, c13-cards-tenant-other, c14-cards-console-usage, c14-owasp-scope |
| W4 | 5.0 | local-e2e: c3-footprint-counts, f03-T07<br>local-unit: c5-integration-scenarios, c5-ai-log-contract, f03-T26, c4-report-window, c8-card-people-access<br>cloud: c14-assurance-locations, c14-assurance-continuity, c14-shared-scenarios, c3-reports-verify-routes, c6-home-models, c10-notifications-api |
| W5 | 6.2 | local-e2e: f03-T08<br>local-unit: c7-search-index, c5-agent-runs, c5-cases-creation, c4-queue-reads<br>cloud: c8-tenants-api-contract, c14-billing-contract, c3-urgency-rule, f03-T16 |
| W6 | 7.5 | local-e2e: c3-fe-obligation-versions, f03-T09<br>local-unit: c3-instruments-read, c7-ai-log-backend, c10-comments-api, c7-hybrid-search-backend, c8-ten-org-api<br>cloud: c5-watch-curation, c5-platform-agent-keys, c13-cards-tenant-register, c12-export-audit-log, c11-security-policy |
| W7 | 8.8 | local-e2e: c5-seed-watch, c4-fe-queue, c3-fe-instruments<br>local-unit: c5-watch-sources-coverage, c4-library-updates, c6-roadmap-backend<br>cloud: f03-T27, c5-watch-registration, c5-cases-footprint-hooks, c8-ten-out-of-office, f03-T45 |
| W8 | 10.0 | local-e2e: c5-fe-console-agent-keys, f03-T10, c7-e2e-seed<br>local-unit: c3-provision-read, c5-fe-watch-data-layer, c4-reports-console-api, c7-ask-backend, c7-eval-gate, c6-home-backend<br>cloud: f03-T29, f03-T17, f03-T19, c5-fe-console-change-facts, c10-workflow-policy, c8-ten-support-grants |
| W9 | 11.2 | local-e2e: c6-e2e-seed, c4-fe-approve, c3-fe-provision-tree<br>local-unit: c4-security-review-1, c6-upcoming-calendar-backend, c5-watch-feed-read, c5-ai-log-and-so-what-draft<br>cloud+e2e: c11-fe-admin-security<br>cloud: c10-fe-collab-feature, c5-fe-console-sources, f03-T30 |
| W10 | 12.5 | local-e2e: c7-search-screen, c6-roadmap-screen, c4-fe-library-updates<br>local-unit: c7-index-changes, c7-eval-sets, c6-briefing-backend, c4-report-resolves<br>cloud: c13-follow-contract, c5-vocab-usage-merge, f03-T28, c10-notification-prefs, f03-T32 |
| W11 | 13.8 | local-e2e: c4-fe-tenant-proposals, c7-ask-screen, c6-calendar-feeds-screen<br>local-unit: f03-T31, c5-fe-change-detail, c5-cases-so-what-and-links, c4-review-fixes-1, c3-security-review<br>cloud: f03-T36 |
| W12 | 15.0 | local-e2e: c7-fe-console-eval-sets, c4-fe-console-reports, c6-today-screen, f03-T37<br>local-unit: f03-T35, c10-mail-catalog, f03-T20<br>cloud: c8-vocab-scales-reasons, c5-library-links-provenance, c13-saved-search-contract, c5-fe-watch-feed |
| W13 | 16.2 | local-e2e: c7-ai-log-screen, c5-e2e-vocab-footprint-feed<br>local-unit: f03-T49, c4-security-review-2, c3-review-fixes, f03-T38<br>cloud: f03-T43, c5-fe-so-what-panel |
| W14 | 17.5 | local-e2e: c6-briefing-screen, c7-j7-journey, f03-T23, f03-T48<br>local-unit: c5-agent-api-flow, c5-fe-obligation-related-changes, f03-T21, c4-review-fixes-2, c8-register-models<br>cloud+e2e: f03-T33<br>cloud: f03-T46, c10-tagging-api |
| W15 | 18.8 | local-e2e: c3-close, c5-e2e-watch-journeys, c5-e2e-j4-agent<br>local-unit: f03-T42, c6-security-review, c5-security-review, c7-security-review<br>cloud+e2e: f03-T41 |
| W16 | 20.0 | local-e2e: c4-fe-report-loop, c4-close-a<br>local-unit: f03-T47, c6-review-fixes, c8-e2e-seed-register, c8-reg-status, c5-review-fixes<br>cloud+e2e: f03-T24<br>cloud: c11-agent-definitions-contract, adm-lang-jur-kinds |
| W17 | 21.2 | local-e2e: c10-fe-suggest, c8-ui-out-of-office, c6-chunk-close, c8-ui-organisation<br>local-unit: c7-review-fixes, f03-security-review, c10-delegation, c4-close-b<br>cloud: c8-reg-applicability, c8-reg-gaps, c8-reg-history-interpretation, c8-ten-reassignment, c8-reg-internal-links, c8-vocab-register-usage |
| W18 | 22.5 | local-e2e: c10-fe-bulk-tagging, r1-perf, c5-chunk-close<br>local-unit: c8-ten-teams, c8-reg-entity-status, c11-tenant-agents-contract, f03-review-fixes, c11-agent-definitions<br>cloud: c13-fe-saved-searches, c12-retention-contract |
| W19 | 23.8 | local-e2e: c7-chunk-close, c8-ui-teams<br>local-unit: c13-fe-follow, c13-i18n-seed-labels, c8-reg-risk-acceptance, f03-T67, c8-reg-inventory-overlay-api, c11-tenant-agent-controls<br>cloud+e2e: adm-fe-lang-jur |
| W20 | 25.0 | local-e2e: c8-ui-applicability, c8-ui-member-removal, r1-readiness, f03-T51<br>local-unit: c11-run-history, c11-fe-console-agent-definitions, c12-config-policies |
| W21 | 26.2 | local-e2e: c8-ui-where-we-stand<br>local-unit: f03-T68, c11-run-scheduler, c11-fe-admin-agents, c8-recurring-duty-library<br>cloud+e2e: c12-fe-data-retention |
| W22 | 27.5 | local-e2e: c8-ui-history-interpretation, c8-ui-inventory-overlay<br>local-unit: c12-tenant-deleted-status, c14-eu-data-location, f03-T53, f03-T70, c11-fe-agents-budget-ai |
| W23 | 28.8 | local-e2e: c8-ui-internal-links<br>local-unit: c11-ai-off-switch, c8-reg-duty-occurrences, c13-egress-client, c12-exit-deletion<br>cloud: c11-batch-proposals-contract, f03-T52, f03-T73, c8-support-access-mechanism, c11-credential-policy |
| W24 | 30.0 | local-unit: c9-case-models, f03-T54, c11-batch-proposals<br>cloud: c11-platform-runs, f03-T82, f03-T69, f03-T66 |
| W25 | 31.2 | local-e2e: c8-ui-support-access, f03-T71<br>local-unit: c8-home-register-feeds, c13-secret-box, c14-job-runs, f03-T55, f03-T64<br>cloud: c11-session-policy |
| W26 | 32.5 | local-e2e: c8-ui-home-register, c8-ui-gaps<br>local-unit: c9-case-contract, c10-reminders-escalation, c13-reg06-attestations<br>cloud: c9-e2e-seed |
| W27 | 33.8 | local-e2e: c9-fe-cases-feature<br>local-unit: c13-sso-domains, c13-int-contract, c11-research-requests, f03-T56, c9-assessment<br>cloud: c13-ip-allowlist, c11-e2e-seed, c13-private-contract, f03-T74 |
| W28 | 35.0 | local-e2e: c8-ui-risk-acceptance, c11-e2e-agent-controls, c11-fe-console-batch-review<br>local-unit: c9-triage, c9-actions, c13-sso-idp-contract, c9-evidence<br>cloud: c9-signoff, c9-case-file, c13-reg06-waivers |
| W29 | 36.2 | local-e2e: f03-T72<br>local-unit: f03-T57, c12-deps-spreadsheets, c9-fe-assessment-panel, c12-dashboard-api, c13-tickets-export<br>cloud: c13-siem-stream, c13-library-change-fanout, c13-fe-integrations-screen |
| W30 | 37.5 | local-e2e: f03-T76, f03-T75<br>local-unit: c9-case-file-export, f03-T58, c13-sso-oidc, c12-export-changes-cases, c12-export-inventory<br>cloud: c11-fe-research-requests, c13-fe-allowlist, c13-private-sources, c13-private-obligations |
| W31 | 38.8 | local-e2e: c12-fe-reports-dashboard, c11-e2e-definitions-requests<br>local-unit: c13-saved-search-notify, f03-T59, c13-follow-notify, c12-exit-export<br>cloud: c12-imports-contract, c12-retention-purge, c13-webhook-delivery, c14-billing-usage, c13-fe-attest-waive, c14-billing-limits |
| W32 | 40.0 | local-e2e: f03-T63, c13-e2e-register<br>local-unit: c13-scim, c9-fe-triage-panel, c11-security-review, f03-T77, f03-T61 |
| W33 | 41.2 | local-e2e: f03-T62<br>local-unit: c12-import-register, c12-config-jobs, c13-tickets-inbound, f03-T78<br>cloud: c12-committee-pack, c13-fe-source-requests, c13-fe-console-source-requests, c9-fe-actions-panel, c8-security-review |
| W34 | 42.5 | local-e2e: c12-fe-exports, c13-e2e-private, c12-fe-data-import<br>local-unit: c14-health-backend, c13-sso-saml, c13-fe-sso, c12-security-review, c13-tickets-jira<br>cloud: f03-T83, c14-assurance-exit-controls, c14-fe-console-plans, c14-fe-usage, c9-fe-evidence-panel |
| W35 | 43.8 | local-e2e: c9-e2e-triage-journeys, f03-T80<br>local-unit: f03-T81, c11-review-fixes, c14-fe-health, c13-security-review<br>cloud: c9-fe-signoff-panel |
| W36 | 45.0 | local-e2e: c14-e2e-billing, c9-e2e-work-journeys, c13-e2e-identity-admin, c14-e2e-health<br>local-unit: c12-review-fixes, c8-review-fixes, c9-fe-case-file<br>cloud+e2e: f03-T65, c12-fe-data-exit<br>cloud: f03-T79, c14-runbooks, c14-owasp-auth, c14-owasp-access |
| W37 | 46.2 | local-e2e: c11-chunk-close, c9-e2e-signoff-journeys, c8-close-out<br>local-unit: c13-review-fixes<br>cloud: c10-digest, c13-fe-tickets-screen |
| W38 | 47.5 | local-e2e: c12-fe-data-configuration, c13-e2e-integrations<br>local-unit: c14-owasp-fixes-auth, c14-owasp-library-ai, c14-owasp-fixes-access, c10-e2e-seed<br>cloud: c13-i18n-server |
| W39 | 48.8 | local-e2e: c12-close<br>local-unit: c9-security-review, c14-perf-search-home, c14-owasp-fixes-library-ai |
| W40 | 50.0 | local-e2e: c14-owasp-integrations-web, c10-fe-notifications<br>local-unit: c14-owasp-files-data, c9-review-fixes |
| W41 | 51.2 | local-e2e: c10-fe-comments-panel, c10-fe-workflow-policy<br>local-unit: c14-owasp-fixes-integrations-web, c14-owasp-fixes-files-data |
| W42 | 52.5 | local-e2e: c13-e2e-saved-searches, c13-e2e-follow, c9-close, c10-j8-extension<br>local-unit: c13-i18n-da, c13-i18n-nb, c13-i18n-fi |
| W43 | 53.8 | local-e2e: c13-i18n-wiring<br>local-unit: c14-owasp-converge, c14-perf-register-cases, c10-security-review |
| W44 | 55.0 | local-e2e: c13-close<br>local-unit: c10-review-fixes |
| W45 | 56.2 | local-e2e: c10-close<br>local-unit: c14-perf-core, c14-perf-library-watch |
| W46 | 57.5 | local-unit: c14-perf-rest |
| W47 | 58.8 | local-e2e: c14-perf-screens |
| W48 | 60.0 | local-e2e: c14-close |

What the waves show:
- **The R1 path goes first.** Chunk 3's reads, chunk 4's backend and the chunk 5 contracts all start in waves 0 and 1.
  - Chunk 3 closes in wave 15 (hour 20.7).
  - Chunk 4 closes in waves 16 and 17 (hours 22.1 and 23.6).
  - Chunk 6 closes in wave 17 (23.6), chunk 5 in wave 18 (25.1) and chunk 7 in wave 19 (25.6).
  - `r1-perf` runs in wave 18, and `r1-readiness` in wave 20, merged at about hour 27.5 in this run.
- **R2 and R3 work that needs nothing from R1 fills the cloud slots from wave 0:**
  - `c9-state-machine`, `c9-case-design`, `c9-scanner-adapter` and `c11-runner-adapter` in wave 0;
  - `c8-tenants-contract`, `c8-register-api-contract` and the design cards in waves 1 and 2;
  - `c10-collab-models` and `c12-exports-contract` in wave 2;
  - the assurance documents and `c14-billing-contract` by wave 5.
- **Security-critical R2 and R3 work waits for R1 (rule 11).** `c12-tenant-deleted-status`, `c13-egress-client`, the SSO packages, the IP allow-list, `c14-job-runs` and `c14-eu-data-location` start from wave 22.
- **R2 and R3 are bound by chains and capacity.** The closes land in this order: chunk 11 in wave 37 (hour 48.0), chunk 8 in 37 (48.9), chunk 12 in 39 (50.3), chunk 9 in 42 (54.1), chunk 13 in 44 (57.4), chunk 10 in 45 (58.2) and chunk 14 in 48 (62.5).
- **When reality differs, dispatch by readiness.**
  - A late decision holds only the packages behind it, and the lanes fill with the next ready packages.
  - If the cloud pilot fails, `cloud+e2e` becomes `local-e2e`, and R2 journeys queue behind R1.
  - A new request becomes a new package, never a change to a running one.

## 5. Critical path and wall clock

### 5.1 Critical paths

Each step on these chains counts its work, its review (15 minutes, or 45 with a security review) and its merge.

**R1** takes 21.4 hours of dependency time. The cumulative hour follows each package:
`h10-log-no-query` (1.4) → `c3-obligations-read` (2.4) → `c3-obligation-detail-read` (4.3) → `c3-reports-verify-routes` (6.0) → `c3-instruments-read` (7.9) → `c3-provision-read` (9.6) → `c5-watch-feed-read` (11.6) → `c5-fe-change-detail` (12.9) → `c6-today-screen` (14.4) → `c6-briefing-screen` (15.8) → `c6-security-review` (16.9) → `c6-review-fixes` (18.6) → `c6-chunk-close` (19.9) → `r1-readiness` (21.4).

The path is the same whether Alex's decisions are in before the start or at hour 6. Three chains run within about an hour of it, so any slip in them moves R1:
- chunk 7's search and Ask chain, 21.1 hours to `r1-readiness`: the chunk 5 contracts → `c5-cases-creation` → `c5-seed-watch` → `c7-e2e-seed` → `c7-search-screen` → `c7-ask-screen` → `c7-ai-log-screen` → review → fixes → `c7-chunk-close`;
- chunk 5's So-what chain, 20.5 hours: `c5-watch-registration` → `c5-ai-log-and-so-what-draft` → `c5-cases-so-what-and-links` → `c5-fe-so-what-panel` → review → fixes → `c5-chunk-close`;
- the PRD 0.3 chain, 19.7 hours: `c3-provision-read` → `f03-T36` → `f03-T37` → `f03-T41` → `f03-security-review` → `f03-review-fixes`.

The Regulatory scope screen chain, `f03-T04` → `f03-T06` → `f03-T07` → `f03-T08` → `f03-T09` → `f03-T23` → `f03-T24`, is 7 journey packages. It starts at about hour 1 and ends near hour 13, so it does not bind.

**Everything** takes 50.0 hours of dependency time. It runs through the R1 path above, then:
`r1-readiness` → `c8-recurring-duty-library`, which waits for R1 because it changes a dependency and the proposal door → `c8-reg-duty-occurrences` → `f03-T56` → `f03-T57` → `f03-T58` → `f03-T59` → `f03-T77` → `f03-T78` → `f03-T81` → `c10-digest` → `c10-e2e-seed` → `c10-fe-notifications` → `c10-fe-comments-panel` → `c10-j8-extension` → `c10-security-review` → `c10-review-fixes` → `c10-close` → `c14-perf-rest` → `c14-perf-screens` → `c14-close`.

With real lane limits, the finish is set by this chain plus contention for the local lanes and the merge slots.

### 5.2 Estimates

Assumptions:
- **Package sizes** are as estimated in the maps and task files: 20 to 60 minutes each. Each seeded run multiplies every package's work and review by a random factor between 0.8 and 1.3.
- **Review:** 15 minutes, and 45 minutes when a security review is required. The two reviewers run side by side.
- **Merge gate** (section 6.1): the quick gates plus the package's own gate commands on the merged tree. About 12 minutes for a backend package, 15 for a frontend one, 18 for a journey package and 5 for docs, on two merge slots. The average is 13.1 minutes, so the 442 merges alone need about 48 hours of slot time on two slots.
- **Ships:** a ship takes 45 minutes. A cloud package starts only from shipped work and spends 10 minutes on `cloud-setup.sh`.
- **Lanes:** 3 local E2E stacks, 3 local unit slots under the memory rule, and 6 cloud sessions.
- **Decisions:** the section 7 decisions are in by hour 6. The three key-gated packages hold no close.
- **Starting state:** packages built at the start begin their review at hour 0, and running packages need half their size.
- **Hours** are hours of continuous orchestration, not calendar hours, with no usage-limit stops.

| | R1 ready (`r1-readiness` merged) | Everything (`c14-close` merged) |
|---|---|---|
| Dependency chains only, unlimited lanes | 21.4 h | 50.0 h |
| This plan: median of 10 seeded runs (range) | 27.9 h (27.5 to 28.7) | 65.6 h (64.2 to 67.5) |
| With a 20 percent margin for red gates, security findings and conflicts | about 33 h | about 79 h |
| The same packages and rules, one chunk after another: median (range) | 78 h (76 to 81) | 203 h (201 to 208) |
| The first version of this plan | 19 h | 40 h |
| The earlier chunk-by-chunk estimate | | 50 to 70 h |

Against the chunk-by-chunk run of the same packages, parallel work saves about 50 hours on R1 and about 137 hours in all.

The first version's 19 and 40 hours did not hold. Six things moved them:
- PRD 0.3 added 77 packages (about 59 hours of work).
- Security reviews take 45 minutes, which costs about 2.4 hours on R1 and 5.5 overall.
- Each merge now runs the touched apps' tests.
- Chunk and PRD 0.3 reviews gained fix packages.
- R1 gained `r1-perf` and the evaluation sets.
- The memory rule costs about half an hour.

The earlier chunk-by-chunk estimate of 50 to 70 hours predates PRD 0.3 and assumed larger tasks with fewer reviews and merges.

### 5.3 What moves the numbers

Each row gives the median of 10 seeded runs and the range. Differences under about 1 hour for R1 and 3 hours overall are within the run-to-run spread.

| Change from the plan | R1 | Everything |
|---|---|---|
| None (the plan) | 27.9 h (27.5 to 28.7) | 65.6 h (64.2 to 67.5) |
| One merge slot instead of two | 41.3 h (40.7 to 41.8) | 98.3 h (97.9 to 98.6) |
| Three merge slots | 27.5 h (26.3 to 28.7) | 64.3 h (61.2 to 66.8) |
| No cloud sessions | 33.0 h (32.7 to 33.9) | 95.0 h (94.1 to 96.0) |
| 4 cloud sessions | 28.4 h (27.6 to 30.4) | 65.9 h (63.3 to 68.9) |
| 10 cloud sessions | 28.1 h (27.4 to 29.3) | 65.2 h (62.9 to 66.3) |
| Three merge slots and 10 cloud sessions | 27.3 h (25.8 to 28.4) | 63.4 h (62.0 to 65.2) |
| Decisions in before the start | 28.1 h (27.0 to 29.1) | 65.4 h (63.0 to 67.1) |
| Decisions in at hour 12 | 30.0 h (29.4 to 30.9) | 67.0 h (64.2 to 72.0) |
| Decisions in at hour 24 | 40.9 h (40.1 to 41.9) | 75.7 h (73.9 to 77.8) |
| No memory rule (3 E2E + 3 unit at once) | 27.4 h (26.4 to 28.2) | 65.1 h (63.3 to 66.5) |
| Security reviews of 15 minutes (the old assumption) | 25.5 h (24.4 to 28.2) | 60.1 h (58.7 to 63.0) |
| The cloud E2E pilot fails | 28.6 h (27.6 to 29.8) | 66.7 h (65.1 to 68.1) |

What the runs show:
- **R1 is bound by its dependencies and the local lanes.** R1 has 52 journey packages still to run. Decisions by hour 6 cost nothing; by hour 12 they cost 2 hours, and by hour 24 about 13.
- **Two merge slots are the minimum.** With one, R1 slips 13 hours and everything 33. A third slot helps little, because the chains and the local lanes bind first.
- **The cloud carries R2 and R3.** Without it, everything takes 95 hours. Between 4 and 10 sessions the finish barely moves.
- **The main agent's attention is a limit the model does not count.** At about 6 minutes per merge it is busy for most of the run. Reviewer sub-agents do the first read, and the main agent reads their verdicts.

## 6. Integration cadence

### 6.1 Each package, merged at once

1. **Dispatch.**
   - The main agent runs rule 1's owned-path check.
   - It creates the worktree (`bash scripts/worktree.sh new <id>`) or a one-off cloud routine (`WORKTREES.md`, "Cloud tasks").
   - The prompt names the package and its map entry or task file. It includes CLAUDE.md section 11 when the package touches UI or journeys, and for a cloud session the stop-and-report rule (rule 12).
   - `model` is set explicitly.
2. **Build.** The sub-agent works test-first in its own slot and runs its own gates and journeys. Before it reports, it merges current main into its branch and reruns them. It commits on its branch only.
3. **Review.**
   - A reviewer sub-agent reads the diff against the package and the invariants.
   - Where SR says yes, a security-review sub-agent runs beside it; allow about 45 minutes.
   - The main agent reads both verdicts. A critical or high finding sends the work back. A finding that does not block becomes a `HARDENING.md` row.
4. **Merge.**
   - The main agent squash-merges into main at once, never waiting for the rest of the chunk.
   - It regenerates the generated files the merge needs, including the snapshot baselines when `registry.ts` or `tone-by-kind.ts` changed.
   - It runs `bash scripts/prepush.sh --quick` plus the package's own gate commands on that exact tree:
     - the touched apps' backend tests;
     - `migrate_from_zero` when a migration changed;
     - the frontend unit tests and the production build when the frontend changed.
   - On green it commits with a playbook 13.4 message that names no model or tool. A red gate means no commit.
   - The full backend suite, E2E and CodeQL run in the ship's CI.
5. **Two merge slots.** While one merge gates on main, the next reviewed package may be squash-merged on top of it in a second slot. It is gated there with its own gate commands and those of the package below it, so two stacked packages are tested together before either commits. Main moves only by fast-forward to a commit whose own tree passed. If the lower merge fails, the upper one is rebuilt on the fixed main and gated again.
6. **Clean up.** The worktree is removed, or the cloud branch deleted.

### 6.2 Pushes

- **A push is `bash scripts/ship.sh`, run in the background.** It runs the quick gates and pushes to `candidate`. There it runs the full `ci.yml`, meaning every gate and the full E2E suite (the same set as `prepush.sh --all`), together with CodeQL. It moves `main` only when both are green.
- **Locally, the main agent also runs `bash scripts/prepush.sh --all`** at every chunk close, at `r1-readiness`, and before any ship when GitHub Actions cannot run.
- **Merges per ship.** One ship runs at a time and carries every merge since the last. The next one starts as soon as the previous is green and something is merged, and at least every 90 minutes while merges wait. Expect about 5 merges per ship and about 87 ships in all.
- **Ship time.** The full E2E suite grows with every journey package. `ci-e2e-shards`, in wave 0 and local because it edits a workflow, splits the E2E job across runners so a ship stays near 45 minutes. If a ship still passes 60 minutes, another `ci` package adds shards.
- **A ship carries at most one dependency change, one CI workflow change and one guard change.** Then a red run points at its cause.
- **A red ship leaves main where it is.** Merging stops. Each merge is one commit on main, so the main agent runs the failing job's reproduce command (`prepush.sh` prints it) with `git bisect run` over the ship's commits to find the culprit. It then fixes or reverts it within about 30 minutes and ships again. Cloud dispatch waits for green.

### 6.3 Ledgers and the orchestrator

- **Status cells.** `app.md` status cells change in the package that builds the requirement. `IMPLEMENTATION_STATUS.md` and the UI plan statuses change only at chunk closes and `r1-readiness`. Status is the truth of `git log`.
- **Coverage floors** are set by ratchet at each close and are never lowered.
- **Orchestration sessions.** The main agent runs the plan in sessions of 6 to 8 hours. It keeps a handover file in `docs/plans/` current after every ship, listing what is running, merged, shipped and waiting on Alex. A usage-limit stop then loses at most the uncommitted work of the running packages.

## 7. External needs

Every row below needs Alex. The main agent copies the rows into `docs/TODO_FOR_alex.md` in the commit that adds this plan; the urgency-tone question is not there yet. "Needed by" is the hour at which the first waiting package could start if every decision were already in.

### 7.1 Decisions that block packages (a product invariant is involved)

| Key | Question | Blocks | Needed by | If late |
|---|---|---|---|---|
| q-urgency | Is urgency's tone fixed by its ordinal? Option A: the rows are fixed, create is refused, and only labels and SLA days can be edited. Option B: an editor may add a level and pick its tone, which lets a person choose a pill tone. This is chunk 3's NFR-S10 question | `c3-urgency-rule`, and through `c5-fe-watch-data-layer` every watch and case screen that shows urgency; NFR-S10's status | hour 1.4 | NFR-S10 stays in progress. The watch screens wait from about hour 8, and R1 moves with them |
| q-Q1 | How may platform staff read and resolve tenants' problem reports? This is chunk 4's Q1; option A is recommended | `c4-report-window` and the chunk 4 tail; AUD-03 | hour 5 | Chunk 4 closes with `c4-close-a`. AUD-03 is R1, so `r1-readiness` names it open and Alex decides whether R1 deploys without it |
| q-search-fence | Is `search_chunk` a LibraryModel, with `search/indexing.py` on the library-fence allowlist, or a derived model with its own write guard? H7 applies either way: the index carries the owner and its own row-level security | `c7-search-index`, and through it hybrid search, `POST /search/similar`, Ask, J-7 and R1 | hour 6 | Chunk 7 has about an hour of slack. After that, each hour late moves R1 by about an hour. Ruling 4's fallback unblocks chunk 5, not chunk 7 |
| q-feed-token | The calendar feed token sits in the feed URL, so the hosting edge's logs hold it. That is the class of problem fixed for invitation tokens (F29, e604de7). Accept it with rotation, or change the design? | `c6-upcoming-calendar-backend`, `c6-calendar-feeds-screen` | hour 11 | Chunk 6 cannot close, and R1 waits |
| q-support-access | Who grants support access? TEN-S6 says a tenant admin, while PRD section 6 gives `support_access.grant` to the platform admin. Is it read-only in R2? How does the console name the tenant? | `c8-card-people-access`, `c8-ten-support-grants`, `c8-support-access-mechanism`, `c8-ui-support-access`, `c10-j8-extension` | hour 4 | Those packages wait, and chunk 8 closes with TEN-06 named open |
| q-retention | Is retention set per tenant for cases, evidence and audit (AUD-04), and how does a purge treat append-only tables? The earlier default purged notifications only, which cuts AUD-04 | `c12-retention-contract`, `c12-retention-purge`, `c12-fe-data-retention`, `c12-config-policies` | hour 22 | Those packages wait, and chunk 12 closes with AUD-04 open |
| q-eu-guards | Which processing locations outside the EU should the production boot refuse? | `c14-eu-data-location` | hour 27 | That package waits |
| q-credential | Does a stricter credential policy apply at sign-in, so existing synced passkeys stop working, or only when a passkey is registered? | `c11-credential-policy` | hour 28 | Chunk 11 closes with the credential policy named open |
| q-exit | Does tenant deletion need four eyes as well as step-up? May deletion remove append-only audit rows, or are they kept, and on what GDPR basis for the names in them? | `c12-exit-deletion`, and through it `c12-exit-export` and `c12-fe-data-exit` | hour 28 | Tenant exit waits, and chunk 12 closes with it open |
| q-private | Who approves tenant-private instruments and obligations (a PRD section 6 bump)? May private text reach a model or the embedder? May a private source start without review? | `c13-private-*`, their screens and `c13-e2e-private` | hour 33 | WAT-06 and INV-07 are cut and named |
| q-sso | How does SSO sit beside "a passkey is the only way in"? Does SSO replace the enrolment code? May a member with a passkey sign in by SSO? What does `enforce_sso` mean? | `c13-sso-*`, `c13-scim`, `c13-fe-sso`, `c13-e2e-identity-admin` | hour 34 | ID-12 is cut from R3 and named |
| q-platform-counters | May the console show per-tenant stream lag, failed jobs and usage through a narrow audited read? Or does each tenant alone see its figures? | `c14-billing-usage`, `c14-health-backend` | hour 38 | Tenant-only figures, and the console shows platform rows only |

### 7.2 Defaults taken, to confirm (nothing waits)

Each default is written in the commit body of the package named:
- One AI switch for every AI feature (`c7-ask-switch`, ruling 13).
- Research requests are gated by `agents.manage` or `proposals.create`, with no new permission (`c11-tenant-agents-contract`).
- Platform agent keys are created under `agent_definitions.manage`, and tenant keys lose the agent write scopes in R1 (`c5-platform-agent-keys`).
- WAT-S4 and WAT-S6 are reworded: a library editor confirms library facts, and a compliance officer decides links on the tenant's own case (`c5-contract-api-screens`).
- Money is held as integer minor units in the agents tables and the plans (`c11-tenant-agents-contract`, `c14-billing-contract`).
- "Send as tickets" moves to chunk 13 (ruling 6).
- The case file exports as text; no PDF library is added (`c12-exports-contract`, `c9-case-file-export`).
- Evidence is limited to PDF, DOCX, XLSX, PPTX, PNG, JPEG, TXT and CSV, up to 25 MB (`c9-evidence`).
- A delegate needs the approve permission themself; delegation only routes work (`c8-ten-out-of-office`, `c10-delegation`).
- An interpretation is a version without an approval step (`c8-reg-history-interpretation`).
- Imported applicability becomes applicability requests for a second person (`c12-import-register`).
- Tagging is gated by `vocab.manage` (`c10-tagging-api`).
- SCIM does no group-to-role sync (`c13-scim`). SAML is descoped if its library breaks the Alpine image or Trivy at MEDIUM (`c13-sso-saml`).
- Agent definitions are read by E5's own reader, and pyyaml stays a development dependency (ruling 19).
- Console language and jurisdiction edits are proposals, built in R2 (`adm-lang-jur-kinds`, ruling 28). Until then, they change only through seeds.
- Evaluation sets are built in chunk 7, for R1. Failed jobs with retry are built in chunk 14, for R3 (ruling 34).
- FP-S5's preview count is proved in f03-T08 (ruling 29).
- Open questions already in `TODO_FOR_alex.md` stay open, including the problem-report "Where" field.

### 7.3 Keys, accounts and services

| Key | Need | Blocks | Needed by |
|---|---|---|---|
| test deploy | A Railway project in EU West, a test host with `WEBAUTHN_RP_ID`, `TRUSTED_PROXY_HOPS=1`, and an EU transactional mail sender | The first test deploy after `r1-readiness` | about hour 28 |
| k-anthropic | `ANTHROPIC_API_KEY` for the test environment (D-07); approval that tenant-typed Ask questions may go to that endpoint on the test deploy; approval of the cost of one 52-case run; and whether CI runs the live classification track | `c5-classification-baseline`; real So-what drafts and Ask answers on the test deploy | the R1 deploy |
| k-embedder | D-09 keys for the embedding and reranker candidates, approval that typed search queries may go to that endpoint, and a CI secret or committed vectors | `c7-embedder-selection-baseline`; until then the test deploy searches by keyword | nothing in the build |
| k-managed-agents | Managed Agents access, plus the D-07 and D-08 rulings | `c11-runner-managed-agents` | nothing in the build |
| clamd | A self-hosted ClamAV service in Railway EU West | Evidence uploads on any deployed environment (chunk 9) | the R2 deploy |
| secret keys | `INTEGRATION_SECRET_KEYS` on the api and worker services | Saving an integration on a deployed environment (chunk 13) | the R3 deploy |
| sandboxes | A Jira Cloud sandbox, and an Entra ID or Okta developer tenant | The manual checks of `c13-tickets-jira`, `c13-sso-oidc` and `c13-scim` | the chunk 13 close |
| EU services | EU-pinned inference (D-07), Sentry EU or no Sentry, and an EU bucket region | Production boot under `c14-eu-data-location` | before a bank tenant |
| plans | The first plans, with limits and prices | The seeded values of `c14-billing-contract` | chunk 14 |
| people | Native-speaker review of sv, da, nb and fi; legal review of the incident clocks and the DORA Article 30 map; a restore test on Railway; a pentest vendor and a certification path | Final copy and the `c14-assurance-*` documents | before a bank tenant |

### 7.4 Capacity

- **Usage allowance.** The plan needs about 356 agent-hours of package work and about 240 of review (15 minutes per package, plus 45 more for each of the 177 security reviews). The orchestrator runs for the whole wall clock. That is about 660 agent-hours in all. A usage-limit stop pauses every lane at once; it happened on 2026-09-19. The wall-clock numbers exclude stops, so add each stop's length one for one.
- **Cloud sessions.** Confirm how many may run at once (the plan assumes 6), and let `f03-T05` run as the cloud E2E pilot.
- **GitHub Actions.** Expect about 87 full CI and CodeQL runs on `candidate`. The repository is public.
- **The laptop.** Docker Desktop must stay up and the machine awake while a run is in progress. Keep within the memory rule of section 2.
- **PRD 0.3 tasks.** `FEATURES_0_3_TASKS.md` exists on the p03 branch with 83 tasks. They are all placed in this plan, and the file lands on main with p03.

## 8. Hardening follow-ups

Findings from the security reviews that did not block their own merge live in `docs/plans/briefs/HARDENING.md`. Each one is built:

| Finding | Where it gets fixed |
|---|---|
| H10 (high): gunicorn's access log writes `?q=` search text, and Sentry breadcrumbs carry it | `h10-log-no-query`, running. It merges before `c3-obligations-read` and before any other route that takes `?q=` |
| H1, H2, H3: the unbounded `offset`, the principal's unbounded permissions, and the `record(tenant_id=None, ...)` guard | `h-a-guards`, after `c3-no-tone` (which owns `apps/shared/schemas.py`), with the `idp` key and a security review |
| H4: `cw.maintenance` rests on review alone | `c3-append-only` (in review) |
| H5: seeded library-list rows get no audit row, and deploys undo approved changes | f03-T01 |
| H6: a machine translation cannot be confirmed in place under the append-only trigger | The default recorded in `TODO_FOR_alex.md`. It is built with the screens that confirm translations |
| H7: the child tables of tenant-private library records have no RLS of their own | `c7-search-index` gives the index the owner and its own RLS. `c7-security-review` checks it |
| H8: approval audit rows carry `steppedUp: false` | `c4-approve-apply` |
| H9: the obligations count's cost grows with the whole library | `h9-footprint-antijoin`, a set-based anti-join, before `r1-readiness`. That is before the deployed library can grow past a few hundred obligations |

A new finding becomes a row there and a package here.

## 9. Considered and rejected

- **Correction 35, in part: "f03-T46 and f03-T47 edit ci.yml, so run them locally".** Their owned paths in `FEATURES_0_3_TASKS.md` are `backend/eval/*`, `search_eval.py`, `tolerance.json` and `tests_scoring.py`, not the workflow. They take the new `eval` key with `c7-eval-gate` and may run in the cloud. `c7-eval-gate`, `c5-classification-baseline` and `c7-embedder-selection-baseline`, which do edit the workflow, hold `ci` and run locally.
- **Correction 4, in part: "f03-T46 and T47 take the `ci` key".** For the same reason they take `eval`, which is the file set they share with `c7-eval-gate`.
- **Correction 15, in part: "add c7-index-changes to `watchwrite`".** Under correction 7, `c7-index-changes` consumes change events through `c5-outbox-cursor`, as Solution_Design routes embeddings (outbox → worker). It no longer edits the watch writers. The other five packages hold `watchwrite`.
- **Correction 17, the `navshot` and `pillshot` keys.** The snapshot baselines become generated files instead, regenerated and reviewed by the main agent at merge. A cloud session cannot produce the win32 baseline anyway, and keys would have moved every screen package that adds a nav entry or a pill onto the laptop. `registry.ts` and `tone-by-kind.ts` stay ledgers of entries.
- **Correction 28, the option of moving pyyaml into the runtime group before E5 merges.** E5's reader reads five top-level scalars from repository files, refuses anything else so a deploy stops rather than guesses, and a test pins it to PyYAML. Moving the dependency would put a local dependency package and an E5 rework at the head of the chunk 5 contract chain, about 1.3 hours on a chain within an hour of R1's critical path. Ruling 19 is changed instead, and the reader is reviewed as input parsing.
- **Correction 2, in part: "place f03-T15 to T49 in R1".** f03-T40 is not placed in R1. It needs a console jurisdiction edit that R1 does not have, and that edit must be a proposal (ruling 28). It is folded into `adm-lang-jur-kinds` in R2. Until then, jurisdictions change only through seeds, which f03-T16's mirror guard keeps exact.
- **Correction 5, the alternative of screens without registry entries.** The dependencies are added instead, so no screen ever calls a stub. To keep the R1 path short, the change page is split and only its So-what panel waits for `c5-cases-so-what-and-links` (ruling 31).