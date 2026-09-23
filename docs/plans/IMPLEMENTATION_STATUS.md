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
| 1 | Identity and tenant admin basics | R1 | 2026-09-19 | 2026-09-19 | | in progress | Invitation, code (token-bound on the link path, no email field), passkey enrolment with derived names, passkey sign-in, sessions, step-up, roles from permissions, API keys, security log, members admin, organisation profile. Security review in `docs/security/CHUNK1_AUTH_REVIEW_2026-09-19.md`; F29 (token in request paths) open, next task. Cut: ID-07, ID-08 (R2), ID-12, ID-13 (R3) |
| 2 | Vocabularies, taxonomy and footprint | R1 | 2026-09-19 | 2026-09-19 | | in progress | Library and tenant vocabularies as rows with rename, reorder, retire, restore, merge and the near-duplicate check; library list writes become proposals (VOC-07); footprint change requests with dry-run preview, four eyes and step-up. FP-03 in progress: the rule exists, the surfaces that apply it arrive from chunk 3. VOC-03 (R2) has a backend and no screen. Cut: the tenant view of its own pending library proposals (moves to chunk 4) |
| 3 | Library and inventory | R1 | 2026-09-22 | 2026-09-22 | | in progress | The data layer, the FFFS 2017:2 provision tree seed, the instrument and provision reads and the inventory and instrument screens are on `main`: instruments and provisions with identity, dates and lineage (INV-01), a three-level provision tree with verbatim versions and transitional notes (INV-02), obligations with facets and diffs (INV-03, INV-04, unchanged from earlier chunk work), original-language text with labelled machine translations on both obligations and provisions (INV-05), a source link, a last-verified date and "this looks wrong" on both instruments and obligations, provisions reporting through their instrument (INV-06). The one footprint rule (`reading.instrument_scopes()`, `reading.obligation_scopes()` inheriting through it) now covers instruments as well as obligations, and the inventory's Instruments tab carries its own "Show outside our scope" switch (FP-03). Cut: `GET /instruments/{id}/problem-reports` and `GET /obligations/{id}/problem-reports` as list endpoints (a reader files a report but nobody reads the list back yet; moves to chunk 4 with the tenant's own proposal queue), `GET /authorities` as a standalone route (re-annotated to chunk 5; an instrument's authority is read embedded today), FP-S4's report surfaces (no register exists yet; chunk 12), the vocabulary screen's real usage count for `relation_type` (stays hardcoded 0) and its merge re-pointing (`repoint.py` has no `relation_type` function, so merging two relation types would not move `instrument_relation` rows off the retired key; both moves to whichever chunk next touches `relation_type`, not INV-01 or INV-02 work). INV-S14 no longer waits on a ruling — D-74 answered `q-editor-confirm` — it waits on the agent-approver code itself (chunk 4-T25/T26, in progress). INV-07 (tenant-private library records) and INV-08 (standards) stay pending, R3 and PRD 0.3 respectively |
| 4 | Proposals and the platform console | R1 | | | | in progress | Built: the console shell and its own sign-in, the proposal queue and one proposal's screen with four eyes and step-up, the rejection-reason list, the tenant's own request list, the audit read for a bank and for the library, the console's tenants, vocabularies, sources, change-facts and agent-key screens, and the tenant's own "what changed in the library while we were away" (PRO-S7, `GET /library-updates`). Not yet: PRO-04 batch proposals (PRO-S8), the independent agent's confirmation (PRO-S13/PRO-S14) and machine-confirmed provenance (INV-S14) — `q-editor-confirm` is answered (D-74); this now waits only on the agent-approver code itself, in progress — ADM-02 system health (ADM-S5), and the platform agent-key routes, which still answer 501 (ID-S20) |
| 5 | Watch and the agent API | R1 | | | | in progress | Built: sources and their checks, change registration and curation through the agent key, the watch feed and one change's page with its timeline, documents and obligation links, the AI-drafted "So what?" per tenant, the fan-out that opens a case in every bank marked inside or outside its scope, and the re-check when the scope moves. Not yet: WAT-06 tenant source requests (WAT-S8), a standard's new edition as one change (WAT-S10), the coverage tab (`GET /sources/coverage` still answers 501), and WAT-S4/WAT-S6's editor-confirmation half, which waits on the confirmation code landing (`q-editor-confirm` itself is answered, D-74) |
| 6 | Home, briefing, roadmap | R1 | | | | in progress | Built: Today with what is coming, the lead item, what needs a decision and source health; the weekly briefing and its snapshots; the roadmap with the quarters ahead and a date's urgency pill; the calendar feed's backend, with its address as a revocable credential. Not yet: the calendar feed's own screen (`/me/calendar-feeds`), which HOM-S5's journey still waits on. HOM-05 (my work) and TEN-02's certificate dates are PRD 0.3 and sit in chunk 8 |
| 7 | Search and ask | R1 | | | | in progress | Built: the hybrid index and its rebuild inside an approval, search by reference and by idea with one ranked answer, similar records, the per-caller rate limits and the search screen. Not yet: Ask — `apps/search/ask.py` still answers one `not_built` event and there is no Ask panel, so SRC-S4, SRC-S5 and J-7 (SRC-S10) wait on it. First test deploy target after this chunk |
| 8 | Register | R2 | | | | pending | PRD 0.3 adds HOM-05, COL-04, REG-08 and the amended TEN-02, TEN-03 and REG-01. HOM-05, COL-04, TEN-02 and TEN-03 sit above the cuttable Should items in the Build plan's list (D-26). D-75 (applicability set by one compliance person after a confirmation dialog, with no second approver) is parked in `b5b70c5` on `origin/claude/r1-integration` for Alex; until it lands REG-01 keeps its four eyes |
| 9 | Case workflow | R2 | | | | pending | |
| 10 | Collaboration | R2 | | | | pending | |
| 11 | Tenant-controlled agents | R2 | | | | pending | PRD 0.5's agent access (ACC, the agents a bank runs itself) is parked in `cee7cf2` on `origin/claude/r1-integration` for Alex; it is not part of this chunk until it lands |
| 12 | Reports, exports, import, exit | R3 | | | | pending | |
| 13 | Integrations and enterprise access | R3 | | | | pending | |
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
