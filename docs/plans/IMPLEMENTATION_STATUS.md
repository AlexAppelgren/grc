# Implementation status

The living ledger of `docs/plans/Build_Plan.md`. Updated at the end of every
chunk, and inside chunk 0 at every Phase 0 item. Status is the truth of
`git log`, not intentions: a row moves only when the commit that earns it is
on `main`.

## Definitions

| Word | Means |
|---|---|
| **implemented** | The code for every requirement in the chunk is on `main`: models with migrations that apply from zero, logic, routes, screens with empty, loading, error and denied states, types regenerated. Nothing skipped, nothing "coming soon" |
| **tested** | Every `@integration` scenario of the chunk is un-skipped and green under `config.test_settings` on Postgres, every `@e2e` scenario is un-fixme'd and green against the real stack, coverage floors hold, and the full pre-push checklist (Appendix D) passes |
| **verified** | Exercised by a person against a running server (the Railway test environment or a local production build): each requirement's `app.md` status cell reads `verified`, and what was cut is named in the commit body and here |

A chunk is **done** when all three hold. `in progress` means at least one
commit for the chunk is on `main`. `pending` means none.

## Chunks

| # | Chunk | Release | Implemented | Tested | Verified | Status | Notes |
|---|---|---|---|---|---|---|---|
| 0 | Phase 0 bootstrap | R1 | 2026-09-19 | 2026-09-19 | | in progress | Checklist below. Verified waits for the owner to boot it (locally or on Railway) |
| 1 | Identity and tenant admin basics | R1 | 2026-09-19 | 2026-09-19 | | in progress | Invitation, code (token-bound on the link path, no email field), passkey enrolment with derived names, passkey sign-in, sessions, step-up, roles from permissions, API keys, security log, members admin, organisation profile. Security review in `docs/security/CHUNK1_AUTH_REVIEW_2026-09-19.md`; F29 (token in request paths) is fixed by e604de7: the invitation token travels in the link's fragment and a request body, never a path. Cut: ID-07, ID-08 (R2), ID-12, ID-13 (R3) |
| 2 | Vocabularies, taxonomy and footprint | R1 | 2026-09-19 | 2026-09-19 | | in progress | Library and tenant vocabularies as rows with rename, reorder, retire, restore, merge and the near-duplicate check; library list writes become proposals (VOC-07); footprint change requests with dry-run preview, four eyes and step-up. FP-03 in progress: the rule exists, the surfaces that apply it arrive from chunk 3. VOC-03 (R2) has a backend and no screen. Cut: the tenant view of its own pending library proposals (moves to chunk 4) |
| 3 | Library and inventory | R1 | 2026-09-24 | 2026-09-24 | | in progress | Closed by `r1-close-and-readiness` over the merged wave-4 batch: `prepush.sh --all` and the full E2E suite green on the close commit. Built: instruments with identity, dates and lineage (INV-01), the provision tree with verbatim versions (INV-02), obligations with facets and diffs (INV-03, INV-04), original-language text with labelled machine translations (INV-05), source link, last-verified date and "this looks wrong" (INV-06), a standard as an instrument per edition with one conformance duty and no standard text (INV-08; INV-S11, INV-S12), the machine-confirmed rendering (INV-S14), the footprint rule over instruments and obligations with the opt-in standards dimension and the regime fold (FP-01, FP-03, FP-S4), and markets with the watched view on the inventory (FP-04, FP-S10, FP-S13). Cut: INV-07, a bank's private library records (R3, chunk 13; INV-S9, INV-S13 and PRO-S12 skipped); the reports' use of the footprint (FP-03, chunk 12). The first standard (ISO/IEC 27001) is a test and E2E seed until the legal question on standard titles is answered (`TODO_FOR_alex.md`). Verified waits for the owner |
| 4 | Proposals and the platform console | R1 | 2026-09-24 | 2026-09-24 | | in progress | Closed by `r1-close-and-readiness`. Built: the console shell and sign-in, the proposal queue and one proposal with four eyes and step-up, the independent agent as the second principal (PRO-S13, PRO-S14, ID-S31, AUD-S9, AGT-S15), the proposal rules for a standard (PRO-S10, PRO-S11), rejection reasons, the tenant's own requests, library updates since the last visit (PRO-S7), the audit read for a bank and for the library (AUD-01), a problem report kept inside the bank with its own list and close (AUD-03, AUD-S5), and the console's tenants, vocabularies, sources, change facts, evaluation set and agent keys (ADM-02's R1 part, ID-S20). D-79's refusal is lifted: an agent may approve a new instrument or obligation (`vocab-agent-confirm`), while `library-confirmer` v2 stays a draft until its evaluation rows exist. Cut: PRO-04 batch proposals (PRO-S8, chunk 11); ADM-02's agent definitions (chunk 11), support access (chunk 8), languages and jurisdictions (R2), plans and system health (ADM-S5, ADM-S7, chunk 14). Open, not cut: H33, whether two agents' keys must come from two people (medium, security-review-c4 M5), waits for the owner's answer. Verified waits for the owner |
| 5 | Watch and the agent API | R1 | 2026-09-24 | 2026-09-24 | | in progress | Closed by `r1-close-and-readiness`. Built: sources and the coverage log with the library re-check that proposes a correction (WAT-01, WAT-S12), one change per reform with its timeline and merges (WAT-02), types, flags, scope and a required regime from vocabularies with suggestions confirmed by an agent of another definition (WAT-03, WAT-S4, D-74), obligation links (WAT-04, WAT-S6), the "So what?" with Rewrite and Confirm per bank (WAT-05, WAT-S7), standards watched from public metadata (WAT-07, WAT-S10, WAT-S11), the agent API from open to close with vocabularies read at run start (AGT-01, AGT-02, AGT-S1, AGT-S3), injection screening and the server-side run budgets (AGT-07, H40, H41), the sector scope and its evaluation gate (AGT-08, AGT-S12), one case per bank per change (CAS-01), agent keys (ID-10), a change's jurisdiction and the feed's watched view (FP-04, FP-S15) and J-4 end to end (AGT-S10). Cut: WAT-06 tenant source requests (WAT-S8, R3, chunk 13); CAS-02 to CAS-08 and J-2 (chunk 9); AGT-03 to AGT-06 and the Sources page's Add, Edit and Check now (chunk 11); console health (chunk 14); no console problem-report surface (removed, D-50). The live classification baseline waits for the D-07 key. Verified waits for the owner |
| 6 | Home, briefing, roadmap | R1 | 2026-09-24 | 2026-09-24 | | in progress | Closed by `r1-close-and-readiness`. Built: Today with what is coming, the lead item, what needs a decision and source health (HOM-01); the weekly briefing and its snapshots (HOM-02); the roadmap's regulatory branch with a date's precision (HOM-03's R1 part); upcoming changes and the revocable calendar feed with its own screen (HOM-04, HOM-S5), writing RFC 5545 as fetched into `Verification_Log.md`. Cut: Today's compliance standing (chunk 8); the roadmap's own deadlines (next reviews and gap targets chunk 8, assessments and actions chunk 9, certificates with TEN-02 chunk 8, HOM-S15), so HOM-03 stays `in_progress`; HOM-05 My work (chunk 8); `Home.decideNow` (Today reads `GET /me` counts); recurrences and briefing feedback. Three confirmations wait for the owner in `TODO_FOR_alex.md`. Verified waits for the owner |
| 7 | Search and ask | R1 | 2026-09-24 | 2026-09-24 | | in progress | Closed by `r1-close-and-readiness`. Built: the hybrid index and its rebuild, search by reference and by idea with one ranked answer, similar records and the per-caller limits (SRC-01, SRC-02); Ask streaming cited statements grounded in the reader's own ranking, flagging pending changes, answering "no answer" without a model call and for any question a standard alone supports, refusing for the bank's AI switch, with the reader's verdict and the budgets (SRC-03, SRC-S4 to SRC-S6, SRC-S9, SRC-S12, J-7); the AI log (AUD-02, AUD-S4); the evaluation set and its release gate (SRC-05, SRC-S8). **The retrieval track of the release gate is not recorded**: it is wired, the baseline reads "Unrecorded" (never zero), and a retrieval regression does not fail CI until `c7-embedder-selection-baseline` runs with the D-09 key; it stays in `TODO_FOR_alex.md`. Cut: SRC-04 saved searches (SRC-S7, chunk 13); SRC-S13, the register's units in search (chunk 8); `POST /eval/runs` (chunk 14); the register filters (chunk 8). Ask on a real model waits for the D-07 key. Verified waits for the owner |
| 8 | Register | R2 | 2026-09-27 | 2026-09-27 | | in progress | Closed by `r2-close-and-readiness` (the R2 close below). Built: applicability per obligation, entity and standard unit by one confirmed person (REG-01, D-75), compliance status per entity kept apart from applicability (REG-02), gaps with risk acceptance (REG-03), history (REG-04), internal links and items, controls among them (REG-05, D-99), the Statement of Applicability per standard and entity (REG-08), recurring duties (REG-07), legal entities with licences and certificates, departments with heads, teams and team membership (TEN-02, TEN-03), member removal with bulk reassignment (TEN-05), support access (TEN-06), My work and participants (HOM-05, COL-04), our own deadlines on the roadmap (HOM-03), vocabulary lists, rules and tagging (VOC-04 to VOC-06). Putting a team in a department, found at the close, was built after it by `ten02-team-department` (2026-09-28), so TEN-02 reads `built`. Left: REG-06 and REG-S9, attestations and waivers, are chunk 13 (R3). PRD 0.3 adds HOM-05, COL-04, REG-08 and the amended TEN-02, TEN-03 and REG-01. HOM-05, COL-04, TEN-02 and TEN-03 sit above the cuttable Should items in the Build plan's list (D-26). D-75 (PRD 0.6) amends REG-01: one compliance person sets applicability after a confirmation dialog, with an audit event and no second approver or step-up; risk acceptance keeps its four eyes. The chunk 8 tasks that file, approve or decide applicability requests are re-planned before the chunk starts (`CHUNK8_TASKS.md`, "Amended by D-75") |
| 9 | Case workflow | R2 | 2026-09-27 | 2026-09-27 | | in progress | Closed by `r2-close-and-readiness`. Built: triage with the one-person close (CAS-02, D-92), assessment with stale writes refused (CAS-03, CAS-08), actions with owner, due date and the sign-off lock (CAS-04), evidence uploaded multipart and scanned by clamd before download (CAS-05, D-101), sign-off with four eyes and a passkey, send-back (CAS-06), the case file (CAS-07), participants on cases (COL-04), J-2 and J-3. Left: CAS-04's ticket export and INT-S3 are chunk 13 (R3); clamd on Railway is Alex's to provision (D-101) |
| 10 | Collaboration | R2 | 2026-09-27 | 2026-09-27 | | in progress | Closed by `r2-close-and-readiness`. Built: comments and mentions on any record a person can read and on My work (COL-01, HOM-05), notifications with preferences, reminders, escalation, the digest and the delegation hop (COL-02), out of office with a delegate (TEN-04, D-95), Create or Suggest where a value is used and the admin's Suggested tab (VOC-03), tags on one record and in bulk (VOC-08). Left: following a record (COL-03, COL-S4) is R3; the `proposal_waiting` and `saved_search_hit` notifications have no producer yet (chunk 13's saved searches); webhook delivery (INT-01) is chunk 13; comment retention is AUD-04's purge, chunk 12 |
| 11 | Tenant-controlled agents, and agent access | R2 | 2026-09-27 | 2026-09-27 | | in progress | Closed by `r2-close-and-readiness`. Built: bleqq's agent definitions and versions as platform configuration (AGT-03, D-102), the agents a bank adds, schedules, pauses, stops and caps (AGT-04), research requests with a bank's capped text as D-98's guarded exception (AGT-05), the runner adapter with its mock and the app as scheduler of record (AGT-06), re-tag batches decided row by row (PRO-04, D-107), the session policy (ID-08), agent access end to end with entries, keys, personal tokens, tenant reach, what applies, the MCP server and the access log (ACC-01 to ACC-09, J-11), and the bank's own records: scope items, the bank's own agent research, its own queue and controls (OWN-01 to OWN-05, INV-07, J-12). Left: the device-bound passkey policy (ID-07, ID-S16, ID-S29) is out of R2 by D-100; the real agent runner and the worker leg that applies its events (H80) wait for the D-07 EU model path; ACC-10 and ACC-S10 are chunk 13 (R3) |
| 12 | Reports, exports, import, exit | R3 | | | | pending | |
| 13 | Integrations and enterprise access | R3 | | | | pending | PRD 0.5 adds ACC-10, the map of which application touches which register entry. PRD 0.7 moves INV-07 to chunk 11 with OWN; private sources (WAT-06) stay here |
| 14 | Hardening and assurance | R3 | | | | pending | |

## Chunk 0: Phase 0 checklist

From playbook 2.2 to 2.5 and the kick-off prompt. The orchestrator ticks an
item when its commit is on `main`. Order matters: later items depend on
earlier ones.

### 2.1 Repo shape and stack
- [x] `docker-compose.yml` and `infra/db/init.sql` (Postgres 16 with pgvector, Redis, roles `cw_migrator` and `cw_app`)
- [x] Exact version pins in `backend/pyproject.toml` and `frontend/package.json` (ADR 0019); deviations recorded there. 2026-09-19: every package moved to its newest release, Django 6.1.1 and TypeScript 7.0.2 included (ADR 0025)
- [x] `agents/` directory with the first versioned definition skeleton (moved to `backend/agents/` in chunk 5, so the API image carries it)

### 2.2 Backend skeleton
- [x] `config/settings.py` with the boot guards of playbook 11.1 (deployed detection, DEBUG, SECRET_KEY, E2E flag, mock adapters, database role, local storage)
- [x] `config/test_settings.py` with a numbered comment per override
- [x] `apps/shared/authentication.py` (`SessionAuth`, `ApiKeyAuth`, `EnrolmentAuth`)
- [x] `apps/shared/permissions.py` (constants, `@requires_permission`, `@requires_scope`, `@requires_step_up`)
- [x] `apps/shared/tenancy.py` (`activate()`, `@tenant_task`, `TenantModel`, `LibraryModel`, `library_write()`)
- [x] `apps/shared/audit.py` (`record()`, `AppendOnlyModel`)
- [x] `apps/shared/vocabulary.py` (abstract `Vocabulary`, generic endpoints)
- [x] `apps/shared/adapters/` (`llm`, `embedder`, `agent_runner`, `mailer`, each with a mock)
- [x] `apps/shared/middleware.py` (request ID, `Server-Timing`), `storage.py`, `health_check.py`, `factories.py`
- [x] `apps/shared/e2e_seed.py` and the `seed_e2e` command (refuses to run deployed)
- [x] Structural guard tests of playbook Section 5, each proven to fail once
- [x] `scripts/compliance_check.py`, `coverage_gate.py`, `requirements_coverage.py`, `contract_drift.py`, `search_eval.py`
- [x] `/health/` checking DB, cache, worker and pgvector, 503 naming the failing component
- [x] `docker-entrypoint.sh`: migrate as `cw_migrator`, idempotent reference seeds with a comment each, gunicorn as `cw_app`
- [x] Sixteen empty domain apps with `apps.py`, `models.py`, `schemas.py`, `logic.py`, `api.py`, `migrations/__init__.py`
- [x] `migrate_from_zero` and `export_openapi` management commands
- [x] `backend/run.sh` and `run.ps1`, `.env.example`, `generate-types.sh`

### 2.3 Frontend skeleton
- [x] `shared/utils/api-client.ts` (one axios instance, bearer, request ID, one-flight refresh, cold-load refresh, `If-Match`)
- [x] `shared/utils/format.ts` and `shared/utils/logger.ts`
- [x] `shared/i18n/` and `messages/<namespace>/{en,sv}.json`
- [x] `shared/navigation/registry.ts` and `require-permission.tsx` with the Restricted screen
- [x] `scripts/build-tokens.mjs` writing `styles/tokens.generated.css` from Green; `styles/brand.css` overriding the brand pair with the placeholders
- [x] `src/styles/theme.css` (`@theme inline`, Tailwind 4 is CSS-first so there is no `tailwind.config.ts`) with semantic colours and the named type scale; numbered sizes generate nothing and ESLint refuses them
- [x] `components/ui/Pill.tsx` and the other primitives from the pill card; `/dev/pills` gallery with the screenshot spec in both themes
- [x] The shell with the phonetic logo (`design/brand/`), light and dark via `next-themes`
- [x] `eslint.config.js` with teeth (no legacy font sizes, no `console.log`, no raw pills, no JSX string literals, E2E imports `test` from `support/api-guard`)
- [x] `vitest.config.ts` with per-directory thresholds; contrast test for every text-on-surface pair including the six tones
- [x] `playwright.config.ts` whose `webServer` boots the real backend and a production Next build; `tests/e2e/support/` (`api-guard`, `passkeys`, `start-backend`)
- [x] `scripts/messages-check.mjs`, `scripts/copy-drift-check.mjs`
- [x] D-04 spike written up in `frontend/docs/D-04-spike.md` and its outcome copied into ADR 0004
- [x] `frontend/tests/e2e/<app>.journey.spec.ts` stubs with `test.fixme()` for every `@e2e` scenario

### 2.4 CI from the first commit
- [x] `.github/workflows/ci.yml` with every gate of playbook Section 9, tiered, a timeout on every job, `pgvector/pgvector:pg16` service, explicit `permissions:`, concurrency, nightly full run
- [x] `.github/workflows/codeql.yml` with `.github/scripts/codeql_gate.py`
- [x] `.gitleaks.toml` extending the default ruleset, dev-only literals and E2E test keys allowlisted exactly
- [x] `.github/dependabot.yml` grouped weekly per ecosystem targeting `main`
- [x] Dependency licence gate and container image scan (MEDIUM and above, Alpine images, ADR 0025)
- [x] Every gate proven to fail once before it is trusted

### 2.5 The document chain
- [x] `CLAUDE.md` per Appendix A, `docs/CONVENTIONS.md`, `.cursor/rules/compliance-watch-rules.mdc`, `README.md`
- [x] `docs/adr/0001` to `0024` and the index
- [x] `docs/plans/IMPLEMENTATION_STATUS.md` (this file), `Implementation_Backlog.md`
- [x] `docs/runbooks/FIRST_RUN_SETUP.md`, `RAILWAY_VARIABLES.md`, `DNS_DOMAINS.md`
- [x] `backend/apps/<app>/app.md` for all 17 apps and `tests_scenarios.py` stubs for the 16 domain apps
- [x] `Verification_Log.md`, `TODO_FOR_alex.md` and `Solution_Design.md` extended
- [x] `docs/inputs/schema.sql` and `data-model.md` present (version 0.3, landed 2026-09-19 09:38 with an updated `INPUT_DELTAS.md`)

### Exit criterion
- [x] The pre-push checklist (Appendix D) passes on the empty app, end to end, including the full `npm run test:e2e` against a freshly seeded backend (2026-09-19: 4 live specs green, 111 stubs skipped, 29 s)

## R1 performance pass (`r1-perf`, NFR-02)

2026-09-23, on `claude/r1w4-r1-perf`, integrated into `main` with wave 4 and confirmed at the R1 close (2026-09-24). Every R1 API operation
and screen has a recorded baseline inside its budget.

- **API:** `backend/perf/routes.py` measures 139 of the 140 operations as the principal that
  calls each in R1 (only `e2eMailOutbox`, E2E-only, is left out); `backend/perf/baseline.json`
  is recorded on a fresh `seed_e2e` slot. Highest p95: `createConsoleTenant` 199 ms (371
  queries, one per seeded role and list), `listObligations` 67 ms, everything else under
  60 ms; search 56 ms against 1.5 s, Ask's first event 51 ms against 2 s. The harness's
  query count read 0 once the connection's query log filled; fixed.
- **Footprint at scale:** on a slot scaled to 3021 obligations and 6431 chunks the
  per-row footprint function put the lists and search over budget. Taxonomy 0008 reads the
  bank's footprint once per query (p95 before and after, 10 samples): `GET /obligations`
  378 to 233 ms, its watched-market view 615 to 241 ms, `GET /instruments` 262 to 119 ms,
  search 903 to 501 ms. The two obligations views are inside budget with little margin; the
  rest of their cost is building each row's scope (its terms and its instrument's reach),
  the next place to look if the library grows past a few thousand obligations.
- **Screens (NFR-S7):** green twice from a fresh seed against `next start`; medians in the
  Measured column of `UI_Implementation_Plan.md`, the slowest the inventory at about 250 ms.
- **Not yet:** real-model and real-embedder timings wait for the D-07 and D-09 keys; the
  load profile and the deployed measurement are chunk 14's.

## R2 performance pass (`r2-perf`, NFR-02)

2026-09-27, on `claude/r2w7-r2-perf-f0h7ud`, built on the nine wave-4 to wave-6 packages it
names. Every R2 API operation has a recorded baseline, the heavy reads are measured at scale,
and what runs over budget is fixed or named in HARDENING.

- **API:** `backend/perf/routes.py` gains three blocks, `r2-perf: chunk 8`, `chunk 9-10` and
  `chunk 11`: 141 R2 operations and 7 second ways of calling one (My work as a department
  head, the inventory filtered by the overlay, what applies, the register reads and MCP with
  a personal token beside an entry's key, search as an entry's key), each as the principal
  that calls it, with a step-up where the route asks for one and the real key or token where
  an agent calls. Heavy calls run at their caps: applicability and a paste at
  `REGISTER_BULK_MAX`, the tagging preview at `BULK_TAGGING_MAX_RECORDS`, the Statement of
  Applicability at Annex A's 93 units, the inbox at 5,000 rows, the evidence upload through
  the mock scanner, the case file export, what applies inside `WHAT_APPLIES_SUMMARY_DEADLINE_MS`
  (about 125 ms median against 2 s). `publishAgentVersion` is the one operation left out:
  it publishes only the next version from a folder the build ships, and no seeded
  definition is one version behind such a folder. `baseline.json` holds all 287 rows,
  recorded on a fresh `seed_e2e` slot (E2E_MODE on). The harness learnt a raw multipart
  body, path converters and a row's variant for this (`perf/harness.py`, tested).
- **Over budget on the seeded slot:** a 100-line paste of units (477 ms p95, H109),
  approving the 12-row batch (378 ms, H111, as its decision row already said), marking 5,000
  notifications read (338 ms, H110) and R1's tenant creation (280 ms, now 521 queries, H112).
  100 applicability answers sit at the edge (244 ms p95). Everything else is inside its
  budget; the slowest R2 reads are what applies, the MCP tool calls and the obligations
  list, all under 170 ms p95.
- **At scale:** a slot of 3,000 obligations, 8,144 chunks, three legal entities, 415 register
  entries, 204 gaps and a 30-person department (391 rows on its My work). Hybrid search took
  5.9 s, 5.1 s of it just-in-time compilation that library 0012's child policies set off;
  JIT is now off on every connection (D-116, H105) and the search answers in 370 ms
  median, 412 ms p95 against 1.5 s. A department's My work read the title of every row;
  it now reads the page's (H106): 130 ms median, 240 to 270 ms p95. Still over: the reader's
  obligations list (270 ms median, 330 ms p95, the footprint judged twice per row through
  library 0012's child policy, H107 and H9) and the roadmap, which has no end without `to`
  (711 items, 634 ms, a product question for Alex, H108). The register reader's filtered
  list (128 ms p95) and a member's own My work (67 ms p95) are well inside.
- **Screens:** every destination reaches its real data inside 500 ms on the merged tree
  (NFR-S7, three green runs against `next start`); the R2 screens' medians are in the UI
  plan, the slowest the inventory at about 340 ms and Today at about 330 ms. The inventory
  had doubled to about 520 ms by reading the closed Filters sheet's terms, scope and duty
  types on landing; it reads them when the sheet opens now (H113). Out of office, which
  joined the registry without a screen budget, has its row.
- **Merged guards:** the merge of the nine packages left six guards red that each package
  had green on its own branch (the agents contract's served list, a participant route both
  gated and ungated, a fixture import in the factories, the chunk 8 to 10 tests writing
  library children from a bank's zone, a publish audit row carrying a typed note, and
  frontend fixtures and catalogs); each is fixed as its package had it. Journeys the chunk 8,
  9 and 11 packages wrote before main's D-104 inventory now walk it: the register's standard
  journeys reach an outside duty through "Show all items", INV-S4's overlay step sets "As of"
  in the Filters sheet, AGT-S6 asks on `/ask`, and the sign-off journeys open a case by its
  stable key as the triage journeys do; AGT-S7, whose runs stay running under the mock
  runner, runs after AGT-S5 and AGT-S6 instead of beside them.
- **Not yet:** real-model and real-embedder timings wait for the D-07 and D-09 keys; the
  load profile and the deployed measurement are chunk 14's.

## R1 close (`r1-close-and-readiness`, 2026-09-24)

R1 (chunks 0 to 7) is implemented and tested on `claude/r1w5-r1-close-and-readiness-6gi2py`,
which starts from `main` at f3b9085 (every wave-2, wave-3 and wave-4 package, shipped green
through CI) and adds only status, ledger and floor changes. Verified is left to Alex: no
requirement reads `verified` until he exercises it on the test deployment.

- **Gates, in one cloud session, not in parallel with any other suite:** `prepush.sh --all`
  green through every gate that runs here: gitleaks over every origin branch, CI tiers,
  osv-scanner, `npm audit`, licences, CodeQL for Python and JavaScript with the accepted
  fingerprints, migration drift and the graph from zero, the backend suite under coverage
  (2081 tests, 1959 run, 122 R2 and R3 stubs skipped; aggregate 97.5%) and every floor,
  ruff, mypy, compliance lint, requirements coverage, contract drift, the API documentation
  gate, search evaluation, OpenAPI and TypeScript drift, the frontend's lint, typecheck,
  coverage, messages, copy drift and build, the full E2E suite (113 passed; the 64 skipped
  are exactly the 64 `test.fixme` journeys, every one R2 or R3) and `@coldstart`. The two
  container builds and their Trivy scans need Docker, which the session does not have; CI
  runs them on `candidate`.
- **No R1 route answers 501:** no production module produces `not_built` any more (a grep
  over `backend/apps` and `backend/config` finds it only in tests that pin its absence), and
  `backend/perf/routes.py` exercised 139 of 140 operations against a seeded stack.
- **No R1 scenario skipped, no R1 journey fixme:** the 122 skipped integration scenarios and
  the 64 fixme journeys all name a chunk from 8 to 14. Requirements coverage is green.
- **API documentation:** `backend/scripts/api_docs_pending.txt` has no entry line.
- **Status cells:** every R1 requirement reads `built`, except HOM-03 (our own deadlines,
  chunks 8 and 9), ADM-01 and ADM-02 (their R2 and R3 parts), which read `in_progress` with
  the cut named in their `app.md`.
- **Hardening:** every medium or higher row reads fixed with its proof, or is a cut Alex
  accepted: H33 (security-review-c4 M5), accepted on 2026-09-24 (D-89).
- **Owner-blocked:** the D-07 model key, the D-09 embedding key and the retrieval baseline
  (the retrieval track of the release gate is **not recorded**), the test deployment, and
  legal on standard titles; listed first in `docs/TODO_FOR_alex.md`.

## R2 close (`r2-close-and-readiness`, 2026-09-27)

R2 (chunks 8 to 11) is implemented and tested on `claude/r2w8-r2-close-and-readiness`, which
starts from `main` at 85fe808 (every wave-1 to wave-7 R2 package, shipped green through CI)
and adds status, ledger and floor changes, and the removal of stale "answers 501" sentences
from the published descriptions. Verified is left to Alex: no requirement reads `verified`
until he exercises it on the test deployment.

- **Gates, in one cloud session, not in parallel with any other suite:** `prepush.sh --all`
  green through gitleaks over every origin branch, CI tiers, osv-scanner, `npm audit`,
  licences, CodeQL for Python and JavaScript with the accepted fingerprints, migration drift
  and the graph from zero, the backend suite under coverage (4104 tests, 4068 run, 36 R3 and
  named-cut stubs skipped; aggregate 97.9% over 28864 statements) and every floor, ruff,
  mypy, compliance lint, requirements coverage, contract drift, the API documentation gate
  and search evaluation. It then stops, as the plan expects, at "OpenAPI/TS: artefacts match
  the contract": the only drift is the regenerated descriptions of this package's edits,
  which the integrator commits (a cloud session never does). With the regenerated artefacts
  left uncommitted in the tree, that gate is green and the run continues: the frontend's lint,
  typecheck, coverage, messages, copy drift and build green; the full E2E suite red in a run
  whose seed was taken at 23:58 in Stockholm and whose journeys ran after midnight (13
  date-anchored journeys a day apart, H114). Re-run after midnight: 187 passed and NFR-S7's
  Today at 504 ms against 500 (H115); the next full run green, 188 passed and the 15 skipped
  exactly the `test.fixme` journeys, none flaky; `@coldstart` green. The two container builds and their
  Trivy scans need Docker, which the session does not have; CI runs them on `candidate`.
- **No R2 route answers 501:** the only `not_built` left in production code is `POST
  /exports` for the kinds chunk 12 builds (R3); the case file export is built. Descriptions
  that still said a built route answered 501 are corrected.
- **No R2 scenario skipped, no R2 journey fixme, except named cuts:** the 36 skipped
  integration scenarios are R3's, plus REG-S9 (chunk 13), ACC-S10 (chunk 13), COL-S4 (R3) and
  ID-S16 and ID-S29 (out of R2 by D-100). The `test.fixme` journeys are R3's (ADM-S5, WAT-S8, SRC-S7, REP-S1, REP-S2, REP-S4, REP-S5, INT-S1, INT-S3, INT-S4, NFR-S17, NFR-S19), REG-S9 (chunk 13) and COL-S4.
  Requirements coverage is green.
- **API documentation:** `backend/scripts/api_docs_pending.txt` has no entry line.
- **Contract drift:** the 22 pending lines are all chunk 12 to 14 (R3); the internal-link
  operations moved to `INPUT_DELTAS.md` as a deliberate shape.
- **Status cells:** every R2 requirement reads `built`, except TEN-02 (no route puts a team
  in a department, found at the close; built since by `ten02-team-department`), ID-07 (out of R2 by D-100), and ADM-01 and ADM-02,
  whose R3 parts are named in their `app.md`.
- **Coverage floors:** 51 R2 modules join `coverage_gate.py` at the file's margins; no
  earlier floor moved. **Test weights:** `test_module_seconds.json` re-measured over the whole
  suite on four workers, per module (each TestCase class timed in its worker, set-up
  included), 3404 worker-seconds over 261 modules; dealt to the ten CI shards they come out even at about 340 seconds each.
- **Hardening:** H1, H2, H3, H4, H8, H12, H38 and H100 checked against code and test and
  marked fixed; H114 (an E2E run across the tenant's midnight) and H115 (Today near its
  screen budget under load) added. Open at medium or higher: H80 (high when a real runner is switched on;
  latent, since only the mock runs), H107 and H108 (performance, H108 waits on Alex).
- **Owner-blocked:** clamd on Railway (D-101), the D-07 model key and EU path, the D-09
  embedding key and retrieval baseline, the test deployment and legal on standard titles;
  listed first in `docs/TODO_FOR_alex.md` ("R2 is closed").

## The library baseline (`claude/library-baseline`, 2026-10-01, D-118, ADR 0065)

The shared library's starting inventory, researched on 2026-09-30 and 2026-10-01 and filed
through the proposal door, so a bank's first scope setting meets real law instead of an
empty library (PRO-01, PRO-02, INV-01, INV-03, INV-05, WAT-01).

- **Built:** 24 tranches in `backend/apps/library/baseline/` (544 instruments, 1,894 duties;
  EU, Sweden, Denmark, Norway and Finland, market abuse and financial sanctions included),
  every fact a row in the Verification log; `check_baseline.py` and
  `apps/proposals/tests_baseline.py`, which files and approves the whole baseline; the
  platform agent `library-baseline` (v1, no model), filed by the beat every
  `LIBRARY_BASELINE_FILING_MINUTES` and by `manage.py file_library_baseline`, which also
  registers the fifteen pages in `sources.json`; the instrument level
  `government_regulation` and the issuers it needed; sanctions under `aml` in watch-sweeper
  v2 and library-confirmer v3; the console queue's New instrument and New obligation filters,
  the review screen's facts for a new record, and approving a page at once with one passkey,
  each proposal through its own approval (PRO-S16, PRO-S17).
- **Owner-blocked:** approving the queue (the agent that filed it cannot), publishing the two
  new agent versions, and Digitaliseringsministeriet's successor; listed in
  `docs/TODO_FOR_alex.md` ("The library baseline").

## Public registers (`main`, 2026-10-05, PRD 0.9, D-121, ADR 0066)

A bank's organisation and regulatory scope from GLEIF and Finansinspektionen's register, on
Alex's word ("go ahead, write the brief and build all steps"), built ahead of the rest of R3
(`docs/plans/briefs/PUBLIC_REGISTERS.md`; TEN-07, TEN-08, FP-05, AC-TEN2, AC-FP4, J-13).

- **Built (backend):** the registers adapter (live GLEIF and FI, mock for tests and E2E; the live
  one run against the real registers for SEB: 17 subsidiaries, 42 licences, 11 branches); the
  lookup job, its apply and the stored register facts (tenants 0006, TEN-S13); the nightly
  re-read (TEN-S14); the licence-to-term mapping (`register_terms.json`); company lines on the
  regulatory scope request with `entity_scope_exclusion` and their history (taxonomy 0013,
  FP-S21); the scope suggestions (FP-S20); the register's span honouring a company's
  exclusions (REG-S18); a total time limit on a lookup's and a re-read's register reads.
- **In progress:** the Organisation and Regulatory scope screens and J-13.
- **Left, deliberately:** the entity switcher and a membership's entity scope (D-96), markets
  from cross-border services, the Danish, Norwegian and Finnish licence registers, a Today
  row for a suggestion. Three questions with defaults are in `docs/TODO_FOR_alex.md`
  ("public-registers").
