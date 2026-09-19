# Compliance Watch (brand: bleqq)

## 1. What Compliance Watch is

Compliance Watch keeps one obligations inventory current and carries every
regulatory change from first sighting to signed-off evidence. Research agents
find and propose, people decide, and every decision is logged. It is built for
enterprise banks in the Nordics: Swedish, Danish, Norwegian, Finnish and EU
sources, five content languages, bank-grade access control, and an assurance
pack a vendor review can use.

Two zones hold the data: a shared library of sourced public facts that changes
only through approved proposals, and a tenant zone of one bank's judgement and
work under row-level security. Nobody has a password; a passkey is the only
way in. The full scope lives in `PRD.md`; requirement IDs refer to it. Read the
relevant module before building any feature.

## 2. Precedence and read order

`PRD.md` > `docs/DECISIONS.md` and `docs/adr/` > `docs/inputs/INPUT_DELTAS.md` >
other files in `docs/inputs/` > playbook conventions. The prototype in `design/`
decides how things look, read and flow, never what the rules are.

Session start: this file, `docs/CONVENTIONS.md`, the `app.md` of every app the
task touches, then `docs/plans/IMPLEMENTATION_STATUS.md`, `docs/TODO_FOR_alex.md`
and `docs/DECISIONS.md`. UI tasks also read the screen card in `design/screens/`
and `docs/plans/UI_Implementation_Plan.md`. `docs/PLAYBOOK.md` is the reference.

## 3. Release plan

| Release | Outcome | Build plan chunks |
|---|---|---|
| R1 | Passkey sign-in, footprint, inventory with versions and diffs, watch feed fed by agents, search and ask, timeline home, briefing, roadmap, vocabularies without a deploy, audit from day one | 0 to 7 |
| R2 | System of record: applicability, compliance status per entity, gaps, the full case workflow, collaboration, tenant-controlled agents | 8 to 11 |
| R3 | Reports and exports, import, integrations, SSO, retention, tenant exit, the assurance pack, billing | 12 to 14 |

Chunks are in `docs/plans/Build_Plan.md`; their state is in
`docs/plans/IMPLEMENTATION_STATUS.md`.

## 4. Tech stack (exact pins, ADR 0019)

| Layer | Pinned |
|---|---|
| Runtime | Python 3.12 (`py -3.12`), Node 22.23.2 in CI (22.19 minimum), npm 10.9, Poetry 2.0.1 |
| Backend | Django 6.1.1 (newest release, ADR 0025; D-17 superseded), django-ninja 1.7.0, psycopg[binary] 3.3.6, pgvector 0.5.0, celery 5.6.3, redis 8.1.0, webauthn 3.0.0, gunicorn 26.2.0, sentry-sdk 2.69.2, django-cors-headers 4.9.0, dj-database-url 3.1.2, python-json-logger 4.2.0, boto3 1.43.98 |
| Backend dev | ruff 0.16.8, mypy 2.3.1, django-stubs and django-stubs-ext 6.1.1, coverage 7.16.1, pyyaml 6.0.3 |
| Database | PostgreSQL 16 with pgvector (`pgvector/pgvector:pg16`), extensions `vector`, `citext`, `pg_trgm`. Redis 7 |
| Frontend | next 16.3.5, react 19.3.0, react-dom 19.3.0, TypeScript 7.0.2 as the compiler with @typescript/typescript6 6.0.3 under the `typescript` name for tools (ADR 0025), tailwindcss 4.3.3, @tailwindcss/postcss 4.3.3, postcss 8.5.28, @tanstack/react-query 5.103.1, axios 1.20.0, next-themes 0.4.6 |
| Design | @sebgroup/green-tokens 3.1.8, @sebgroup/green-core 3.23.0, Radix primitives (dialog 1.1.23, dropdown-menu 2.1.24, tooltip 1.2.16, select 2.3.7, popover 1.1.23, tabs 1.1.21, checkbox 1.3.11, switch 1.3.7, slot 1.3.3), input-otp 1.5.0, class-variance-authority 0.7.1, clsx 2.1.1, tailwind-merge 3.7.0, @fontsource-variable/hanken-grotesk 5.3.0, @fontsource-variable/noto-sans-mono 5.3.0 |
| Frontend test and lint | vitest 5.0.1, @vitest/coverage-v8 5.0.1, @playwright/test 1.63.0, @testing-library/react 16.3.3, @testing-library/jest-dom 7.0.1, jsdom 30.1.0, eslint 10.11.0, eslint-plugin-react 7.37.5, typescript-eslint 8.70.0, @next/eslint-plugin-next 16.3.5, eslint-plugin-react-hooks 7.1.1, openapi-typescript 7.13.0 |

Frontend pins are exact (no `^`). A pin that fails to install is replaced by
the nearest working version and the change is reported with its reason.

## 5. Non-negotiable invariants

Weakening any of these is a stop: ask the owner (Alex) first.

- Two zones. Tenant tables carry `tenant_id` under enabled and forced
  row-level security; the app role `cw_app` cannot bypass it and the app
  refuses to boot on a role that can.
- Proposals are the only door into the library. Agents never edit it; no API
  key scope reaches it. The re-verification stamp is the single exception.
- Nothing overwritten: versions with effective dates, soft-deleted evidence,
  append-only ledgers with a trigger. Audit and outbox rows in the same
  transaction as every write, through `record()`, the only way to write them.
- Four eyes, enforced by a check constraint, with a passkey step-up on
  approvals, sign-off, footprint changes, exports, key creation, role and
  security changes, re-enrolment.
- No passwords, ever. The emailed code works once, for enrolment, and stops
  working the moment the first passkey exists. No self-service fallback.
- "Applies" and "we comply" are separate facts. Stable keys never change.
- AI output is labelled until a person confirms it; every model call is
  logged; fetched content is untrusted.
- Enums in code are for kinds only. Types, statuses, tags and reasons are rows
  an admin manages; the API returns `key` and `kind`, never a phrase. The case
  state machine's categories and guards are fixed; sub-statuses sit inside.
- Six pill tones (`information`, `notice`, `positive`, `warning`, `negative`,
  `brand`), chosen by slot or kind, never by a person. Pills only through
  `Pill`. No string literals in JSX text.
- Tenant content never reaches logs, Sentry, analytics or an unapproved model
  endpoint. PostgreSQL with pgvector everywhere; there is no SQLite.
- Never lower a gate, skip or quarantine a test, or mock an API in E2E.

### Simplicity first, never at the cost of security or quality

Write the least code that fully solves the stated problem (Alex, 2026-09-19).
No features beyond what was asked. No abstraction for code used once. No
flexibility or configuration nobody asked for. No error handling for cases that
cannot happen. If 200 lines could be 50, rewrite it. The test: would a senior
engineer call this overcomplicated? If yes, simplify.

Security and quality win whenever they pull against simplicity, so never
simplify away: an invariant above or the guard and test that enforce it;
validation at a trust boundary (input from a user, an agent, the network or an
external service is never an impossible case); a test, gate or coverage floor;
an audit row, permission check or step-up; or a setting the playbook requires
(windows, caps, rates and thresholds are settings by rule, not speculation).
Simplify the design, not the safeguards: fewer moving parts is itself a
security property.

## 6. Performance budgets

API endpoint under 250 ms server time (`Server-Timing: app`, a WARNING above
`API_BUDGET_MS`); screen under 500 ms to real data; hybrid search under 800 ms
(1.5 s with the reranker); Ask first token under 2 s, streamed; exports,
imports and agent runs are jobs with a status endpoint. Fan out, never chain.
Paginate (default 20, max 100). Measure against `next start`, never `next dev`.

## 7. Git workflow and the pre-push checklist

One deployed branch, `main`, during the build (D-15), reached only through `bash scripts/ship.sh`,
which runs the real CI and CodeQL on the `candidate` branch first (ADR 0015, 2026-09-19); small commits per whole
slice, each passing the checklist below. Parallel sub-agents work in local worktrees on
short-lived `wt/*` branches that are never pushed; the main agent reviews each and merges
it into `main` (`docs/runbooks/WORKTREES.md`, `scripts/worktree.sh`). Inside a worktree,
load its slot first: `set -a; . ./.env.worktree; set +a`. Commit messages: a plain-English headline
from the user's or the system's point of view; a body with the why, the
requirement IDs, what now happens, what was deliberately not done; no model
or tool names. The owner deploys; never deploy yourself.

**Pre-push checklist: run `bash scripts/prepush.sh --quick`** before every commit to
`main`, and push only with `bash scripts/ship.sh` (`prepush.sh --all` runs every gate locally). It mirrors CI and CodeQL with the same tools,
versions, flags and thresholds, so a green run predicts a green CI run: CodeQL
(`security-extended`, then `.github/scripts/codeql_gate.py` with the accepted
fingerprints), gitleaks, osv-scanner and `npm audit`, licences, the backend and
frontend gates below, OpenAPI drift, E2E and Trivy on both images. It is tiered
by what changed since `origin/main` like CI, downloads its scanners once into
`<main checkout>/.tools/`, and stops at the first red gate with the command
that reproduces it. The items it runs (playbook Appendix D, verbatim):

Every item is enforced by CI and blocks. Run what the diff touched. All
commands assume Postgres with pgvector is running (`docker compose up -d db
redis`, or a local PostgreSQL 16 with the `vector` extension installed).

1. **Migration drift and graph** (any model change):
   ```bash
   cd backend && ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings
   ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings
   ```
   `migrate_from_zero` drops and recreates a scratch database and applies the
   whole graph.
2. **Backend tests + coverage floors** (any backend change):
   ```bash
   cd backend
   ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput
   ./run.sh run coverage report
   ./run.sh run python scripts/coverage_gate.py
   ```
3. **Backend lint + types**: `./run.sh run ruff check . && ./run.sh run mypy`
4. **Compliance lint**, full tree: `python backend/scripts/compliance_check.py --all`
5. **Requirements coverage**: `python backend/scripts/requirements_coverage.py`
6. **OpenAPI + TypeScript drift** (any route, schema or model change):
   `bash generate-types.sh`, commit `openapi.json` and `api.generated.ts`.
7. **Frontend** (any frontend change):
   `cd frontend && npm run lint && npm run typecheck && npm run test:coverage && npm run check:messages && npm run build`
8. **E2E** for the journeys the change touches: `npm run test:e2e -- --grep "<spec or @smoke>"`,
   the full suite before closing a chunk.
9. **Search evaluation** (any change to search, chunking, embeddings or agent classification): `python backend/scripts/search_eval.py`
10. **Secrets**: `gitleaks git . --config .gitleaks.toml` if the binary is local.
11. **Copy drift** (any reworded user-facing string): `cd frontend && npm run check:copy-drift`
12. **Time-anchored fixtures** (any seed or fixture derived from "now"):
    check against the clock rules in Section 8.3.

## 8. Build and run

**With Docker:** `docker compose up -d db redis`. The `db` container runs
`infra/db/init.sql` once: roles `cw_migrator` (owns the schema, `CREATEDB`
locally) and `cw_app` (no ownership, no `BYPASSRLS`), database
`compliance_watch`, extensions `vector`, `citext`, `pg_trgm` (also in
`template1`). Superuser `postgres` / `postgres-dev-only` on 5432, Redis on 6379.
**Without Docker:** install PostgreSQL 16 with the pgvector package and Redis,
run `psql -U postgres -d compliance_watch -f infra/db/init.sql`; same roles,
passwords and extensions, the settings do not change. There is no SQLite path.

**Backend** (from `backend/`, via `./run.sh` or `./run.ps1`): `./run.sh install`,
`./run.sh run python manage.py migrate` (as `MIGRATOR_DATABASE_URL`),
`./run.sh run python manage.py runserver`. Local defaults:
`DATABASE_URL=postgres://cw_app:cw-app-dev-only@localhost:5432/compliance_watch`,
`MIGRATOR_DATABASE_URL=postgres://cw_migrator:cw-migrator-dev-only@localhost:5432/compliance_watch`.
Every variable: `.env.example`, `docs/runbooks/RAILWAY_VARIABLES.md`.

**Frontend** (from `frontend/`): `npm ci`, `npm run build:tokens`, `npm run dev`;
`npm run build && npm start` for anything measured or tested. **Types:**
`bash generate-types.sh` at the root. **E2E:** `npm run test:e2e` or
`npm run test:e2e -- --grep @smoke`; the `webServer` recreates the test
database, migrates from zero, seeds, boots Django with `E2E_MODE` and mock
adapters, and starts a production Next build.

## 9. Project structure

```
PRD.md  CLAUDE.md  README.md  .mcp.json  docker-compose.yml  generate-types.sh
design/    prototype/, system/ (cards), screens/, brand/
docs/      PLAYBOOK, CONVENTIONS, DECISIONS, adr/, plans/, inputs/, runbooks/, reviews/, security/, assurance/, TODO_FOR_alex.md
infra/db/  init.sql (local roles and extensions)
backend/   apps/<app>/, apps/shared/, agents/ (versioned definitions), config/, scripts/, run.sh, run.ps1   (Django + Ninja, Poetry)
frontend/  src/app/ ((tenant) and (console) route groups), src/components/ (+ ui/Pill), src/features/<domain>/
           (api.ts, hooks.ts, *-presentation.ts), src/shared/ (api-client, format, logger, navigation, i18n),
           src/messages/, src/styles/ (tokens.generated.css, brand.css), src/types/api.generated.ts,
           tests/e2e/ (journeys + support/), scripts/
.github/   workflows/ci.yml, workflows/codeql.yml, scripts/codeql_gate.py, dependabot.yml
```

Apps: `identity`, `tenants`, `taxonomy`, `library`, `proposals`, `watch`,
`register`, `cases`, `search`, `home`, `collab`, `agents`, `reports`,
`integrations`, `governance`, `billing`, and `shared` (the mechanics).

| File in `apps/<app>/` | Purpose |
|---|---|
| `app.md` | The app's spec. Read first |
| `models.py` | snake_case columns; `TenantModel`, `LibraryModel`, `Vocabulary`, `AppendOnlyModel`; `Meta.ordering` on anything `.first()`ed; `JSONField` only with a named schema |
| `schemas.py` | All Pydantic request and response models, camelCase, app-prefixed names when app-specific |
| `logic.py` | All business logic; `ValidationError` with user-facing text; every write through `record()` |
| `api.py` | Routes only: auth class, `@requires_permission` or `@requires_scope`, `@requires_step_up` |
| `tests_scenarios.py` | One test per `@integration` scenario, docstring carries the ID |
| `tests_*.py` | Models, rule branches, isolation, concurrency, regression pins |

## 10. The app.md convention

Exactly four sections (playbook Appendix B): context, requirements table with
status `pending` | `in_progress` | `built` | `verified`, condensed acceptance
criteria, Gherkin scenarios headed
`### <PREFIX>-S<n> — <Title> \`@integration\` \`@e2e\` (<REQ-IDs, AC-IDs, J-IDs>)`.
`@integration` maps to `tests_scenarios.py` (`test_<id_lowercased_underscored>`,
`@skip("pending: <ID>")` until built); `@e2e` to
`frontend/tests/e2e/<app>.journey.spec.ts` with the ID in the title and
`test.fixme()` until built. The PRD wins on conflict. Read app.md before
writing code in the app; when a feature lands update the status, un-skip, and
add scenarios for behaviour the PRD did not cover. Cross-app flows live in the
app that triggers them. Never invent another spec format.

## 11. E2E user-flow testing (MANDATORY)

Every UI chunk ends with its journeys green against the real stack. Propagate
this section, in full, to any sub-agent doing UI work.

- One command, `npm run test:e2e`, boots the real backend on a freshly seeded
  throwaway database and a **production** Next build. Never `next dev`.
- Sign in through the UI with a passkey: `support/passkeys.ts` seeds the test
  private keys into Playwright's virtual authenticator (`browserContext.credentials`,
  1.61+, verified 2026-09-19). Never inject tokens or cookies, never mock an
  API response; backend down means tests fail.
- The emailed code appears in exactly two journeys: enrolment of the one
  seeded user without a passkey, and the proof that a code request for an
  enrolled user sends nothing. `E2E_MODE` makes it deterministic; refused deployed.
- Every spec imports `test` from `tests/e2e/support/api-guard` (ESLint
  enforces it): a journey fails on any undeclared `/api/` response of 400 or
  above or any page exception. Declare an expected error where it happens:
  `apiGuard.allow(/\/signoff\/approve/, 409, 'the requester cannot sign off')`.
- Extend `seed_e2e`, never mock: idempotent, deterministic, realistic, from
  the prototype's data. Two tenants, one login per system role, a platform
  editor, one login per negative case. Golden paths J-1 to J-8 are `@smoke`;
  push CI runs `@smoke`, nightly runs all.
- Clocks anchor to the tenant-local date plus a fixed wall time. Settle before
  branching (`await expect(a.or(b).first()).toBeVisible()`). Exact text where
  copy can collide. Teardown restores seeded data on failure too. When a
  journey fails, read the screenshot and trace before touching code.

## 12. Rules and conventions

Full text with the bugs behind each rule: `docs/CONVENTIONS.md`.

- snake_case in the database, camelCase in the API through Ninja's alias
  generator. `JSONField` only with an inline suppression naming its schema.
- No `*args`/`**kwargs` in endpoints or logic. No logic in `api.py`. Schemas in
  `schemas.py`, never `Dict[str, Any]`. No bare `except Exception:`. No `admin.py`.
- Never expose a trace: RFC 9457 problem details with `code`; the client
  branches on `code`, never on `detail`. An empty answer is 200.
- Logging: a person's name and id at most, tenant content never. `logger`
  only, never `console.log`.
- Kinds-only enums; vocabularies are rows; store and compare keys, never labels.
- Pills through `Pill` and a presentation function per record type; no string
  literals in JSX; typography roles only (`text-display`, `text-title`,
  `text-body`, `text-meta`, `.microlabel`; `text-hero` on public pages).
- Screen copy says what the user is doing: no requirement IDs, no restated
  invariants on screen, every string in the message catalogs.
- Permissions, never role names. `tenancy.activate()` after auth; `@tenant_task`
  in the worker. `record()` on every write; `If-Match` on versioned records;
  idempotency on agent writes and webhooks.
- Every threshold is a setting with an env override; tests use fixtures. UTC
  timestamps; legal dates are plain dates with a precision.
- Fetch provider docs, never recall them, and log them in
  `docs/plans/Verification_Log.md`. Use the Green MCP server for tokens.
- Ask rather than guess on an invariant; take the `docs/DECISIONS.md` default
  everywhere else and say so in the commit body. Anything needing a person
  goes to `docs/TODO_FOR_alex.md`.

## 13. Key file reference

| Need | File |
|---|---|
| What to build | `PRD.md`, `backend/apps/<app>/app.md` |
| How we build | `docs/PLAYBOOK.md`, `docs/CONVENTIONS.md` |
| Decisions, defaults, departures from the inputs | `docs/DECISIONS.md`, `docs/adr/`, `docs/inputs/INPUT_DELTAS.md` |
| Architecture, order of work, state | `docs/plans/Solution_Design.md`, `Build_Plan.md`, `IMPLEMENTATION_STATUS.md`, `Implementation_Backlog.md` |
| Outside-world claims; needs a person | `docs/plans/Verification_Log.md`; `docs/TODO_FOR_alex.md` |
| Deploy, variables, domains, first run | `docs/runbooks/` |
| Design contract | `design/README.md`, `design/system/pills-and-labels.md`, `design/prototype/index.html`, `design/brand/README.md` |
| Database roles, boot guards | `infra/db/init.sql`, `docker-compose.yml`, `backend/config/settings.py`, `test_settings.py` |
| Mechanics and gates | `backend/apps/shared/` (`authentication`, `permissions`, `tenancy`, `audit`, `vocabulary`, `adapters/`), `backend/scripts/`, `.github/workflows/ci.yml`, `frontend/scripts/` |
