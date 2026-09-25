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
| 8 | Register | R2 | | | | pending | PRD 0.3 adds HOM-05, COL-04, REG-08 and the amended TEN-02, TEN-03 and REG-01. HOM-05, COL-04, TEN-02 and TEN-03 sit above the cuttable Should items in the Build plan's list (D-26). D-75 (PRD 0.6) amends REG-01: one compliance person sets applicability after a confirmation dialog, with an audit event and no second approver or step-up; risk acceptance keeps its four eyes. The chunk 8 tasks that file, approve or decide applicability requests are re-planned before the chunk starts (`CHUNK8_TASKS.md`, "Amended by D-75") |
| 9 | Case workflow | R2 | | | | pending | |
| 10 | Collaboration | R2 | | | | pending | |
| 11 | Tenant-controlled agents, and agent access | R2 | | | | pending | PRD 0.5 adds ACC-01 to ACC-09, the agents a bank runs itself (`docs/plans/briefs/AGENT_ACCESS.md`). ACC sits below the AGT work in the chunk's list and is cut first under the descope rule, moving whole to chunk 13. PRD 0.7 adds OWN-01 to OWN-05 and moves INV-07 here from chunk 13 (D-89, D-91, ADR 0059, `docs/plans/briefs/SCOPE_ITEMS.md`) |
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
