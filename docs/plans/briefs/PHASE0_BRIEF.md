# Phase 0 brief for sub-agents (shared by every agent)

Repo: `C:\Users\Alex\projects\grc` (git, branch `main`). Windows 11, Git Bash and
PowerShell available. Python 3.12 is at `py -3.12`. Node 22.18, npm 10.9, Poetry 2.0.1,
Docker Desktop (Postgres 16 + pgvector and Redis via `docker compose up -d db redis`;
`docker-compose.yml` and `infra/db/init.sql` already exist at the repo root and create the
roles `cw_migrator` / `cw_app`, database `compliance_watch`, extensions vector, citext,
pg_trgm; superuser `postgres` / `postgres-dev-only`, port 5432). Redis on 6379.

## Read first (mandatory, in this order)
1. `CLAUDE.md` (root)
2. `docs/PLAYBOOK.md` — the sections named in your task, plus Sections 1, 4.3, 5, 13
3. `PRD.md`
4. `docs/DECISIONS.md`, `docs/inputs/INPUT_DELTAS.md`
5. `design/system/pills-and-labels.md`, `design/brand/README.md`, `design/README.md`

`docs/inputs/schema.sql` and `docs/inputs/data-model.md` are MISSING from the repo. Phase 0
does not need them (no domain models are built in Phase 0). Do not invent domain tables.
Only the identity/tenancy/audit/vocabulary *base* mechanics and empty app packages exist
after Phase 0.

## Product invariants (never weaken; stop and report instead)
- Two zones. Tenant tables under forced row-level security; the app DB role cannot bypass it.
- Proposals are the only door into the library. Agents never edit it.
- Nothing overwritten: versions with effective dates. Audit + outbox rows in the same
  transaction as every write, through `record()`.
- Four eyes with passkey step-up on approvals. No passwords, ever. Emailed code is
  enrolment-only, never a fallback.
- Enums in code are for kinds only. Types/statuses/tags/reasons are rows. API returns
  `key` and `kind`, never a phrase.
- Six pill tones (`information`, `notice`, `positive`, `warning`, `negative`, `brand`),
  chosen by slot or kind, never by a person. Pills only through `Pill`. No string
  literals in JSX text.
- Tenant content never reaches logs, Sentry or an unapproved model endpoint.
- PostgreSQL with pgvector everywhere. No SQLite anywhere.
- Never lower a gate, skip/quarantine a test, or mock an API in E2E. If a gate is wrong,
  fix the gate and say why.
- Requirement IDs (e.g. `ID-03`) appear in specs, test docstrings, commit bodies and code
  comments. Never on screen.

## Pinned versions (exact; record where you put them)
Backend (Poetry, `backend/pyproject.toml`, `python = "~3.12"`):
django 5.2.17 (D-17: 5.2 LTS, NOT 6.x), django-ninja 1.7.0, psycopg[binary] 3.3.6,
pgvector 0.5.0, celery 5.6.3, redis 8.1.0, webauthn 3.0.0, gunicorn 26.2.0,
sentry-sdk 2.69.2, django-cors-headers 4.9.0, dj-database-url 3.1.2,
python-json-logger 4.2.0, boto3 1.43.97, whitenoise 6.12.0 (only if needed).
Dev: ruff 0.16.8, mypy 2.3.1, django-stubs 5.2.9 (5.2 line to match Django 5.2; if it
does not resolve with mypy 2.3.1, pick the newest django-stubs 5.2.x + the mypy it pins
and RECORD the pair), coverage 7.16.1.
Frontend (`frontend/package.json`, exact versions, no `^`):
next 16.3.5, react 19.3.0, react-dom 19.3.0, typescript = newest **5.x** (check
`npm view typescript versions --json`; do not use 7.x), tailwindcss 4.3.3,
@tailwindcss/postcss 4.3.3, postcss 8.5.28, @tanstack/react-query 5.103.1, axios 1.20.0,
next-themes 0.4.6, vitest 5.0.1, @vitest/coverage-v8 5.0.1, @playwright/test 1.63.0,
eslint 10.10.0, typescript-eslint 8.70.0, @next/eslint-plugin-next 16.3.5,
eslint-plugin-react-hooks 7.1.1, openapi-typescript 7.13.0, @sebgroup/green-tokens 3.1.8,
@sebgroup/green-core 3.23.0, @radix-ui/react-dialog 1.1.23,
@radix-ui/react-dropdown-menu 2.1.24, @radix-ui/react-tooltip 1.2.16,
@radix-ui/react-select 2.3.7, @radix-ui/react-popover 1.1.23, @radix-ui/react-tabs 1.1.21,
@radix-ui/react-checkbox 1.3.11, @radix-ui/react-switch 1.3.7,
class-variance-authority 0.7.1, clsx 2.1.1, tailwind-merge 3.7.0,
@testing-library/react 16.3.3, @testing-library/jest-dom 7.0.1, jsdom 30.1.0,
@fontsource-variable/hanken-grotesk 5.3.0, @fontsource-variable/noto-sans-mono 5.3.0.
If a pinned version fails to install or is incompatible, pick the nearest working
version and REPORT the change with the reason.

## Canonical commands (CI, docs and Dockerfiles all use exactly these)
Backend, from `backend/`, via the Poetry wrapper `./run.sh` (bash) or `./run.ps1`:
```
./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings
./run.sh run python manage.py migrate_from_zero --settings=config.test_settings
./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput
./run.sh run coverage report
./run.sh run python scripts/coverage_gate.py
./run.sh run ruff check . && ./run.sh run mypy
./run.sh run python scripts/compliance_check.py --all
./run.sh run python scripts/requirements_coverage.py
./run.sh run python scripts/contract_drift.py
./run.sh run python scripts/search_eval.py
./run.sh run python manage.py export_openapi --out ../openapi.json
```
Frontend, from `frontend/`:
```
npm ci
npm run build:tokens     # scripts/build-tokens.mjs -> src/styles/tokens.generated.css
npm run lint
npm run typecheck
npm run test:coverage
npm run check:messages   # scripts/messages-check.mjs
npm run check:copy-drift # scripts/copy-drift-check.mjs
npm run build
npm run test:e2e         # playwright (webServer boots backend + next start)
npm run test:e2e -- --grep @smoke
```
Root: `bash generate-types.sh` (export openapi.json from backend, normalise, run
openapi-typescript to `frontend/src/types/api.generated.ts`).

## Environment variables (backend `config/settings.py`; `.env.example` lists all)
`ENVIRONMENT` (local|test|ci|<anything else = deployed/production, fail closed),
`RAILWAY_ENVIRONMENT_NAME` (presence alone = deployed), `DEBUG`, `SECRET_KEY`,
`DATABASE_URL` (cw_app), `MIGRATOR_DATABASE_URL` (cw_migrator), `REDIS_URL`,
`ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `PRODUCT_NAME` (default "Compliance Watch"),
`WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGINS`, `STORAGE_BACKEND` (local|s3), `STORAGE_*`,
`MAIL_PROVIDER` (mock|smtp), `MAIL_*`, `LLM_PROVIDER` (mock|anthropic|bedrock),
`ANTHROPIC_API_KEY`, `EMBEDDER_PROVIDER` (mock|...), `AGENT_RUNNER` (mock|managed_agents),
`E2E_MODE` (the E2E flag: deterministic codes; refused when deployed), `SENTRY_DSN`,
`API_BUDGET_MS` (250), `NEXT_PUBLIC_API_URL`.
Local defaults: `DATABASE_URL=postgres://cw_app:cw-app-dev-only@localhost:5432/compliance_watch`,
`MIGRATOR_DATABASE_URL=postgres://cw_migrator:cw-migrator-dev-only@localhost:5432/compliance_watch`.
Dev-only secrets are literal strings ending in `-dev-only` or starting `django-insecure-`.

## Django apps (empty packages after Phase 0, each with `app.md`, `apps.py`, `models.py`,
`schemas.py`, `logic.py`, `api.py`, `tests_scenarios.py`, `migrations/__init__.py`)
`identity`, `tenants`, `taxonomy`, `library`, `proposals`, `watch`, `register`, `cases`,
`search`, `home`, `collab`, `agents`, `reports`, `integrations`, `governance`, `billing`,
plus `shared` (the mechanics). Python package path: `apps.<name>`; label = name.

## app.md scenario heading format (parsed by `scripts/requirements_coverage.py`)
Exactly (Appendix B): `### <APP>-S<n> — <Title> \`@integration\` \`@e2e\` (AC-…)` where
`<APP>` is the upper-case app prefix used by the PRD (ID, TEN, VOC, FP, INV, PRO, WAT,
REG, CAS, SRC, HOM, COL, AGT, REP, INT, AUD, ADM, I18N, NFR) — one app.md may host
several prefixes (e.g. `governance/app.md` hosts AUD; `tenants/app.md` hosts TEN and ADM-01;
`identity/app.md` hosts ID; `taxonomy/app.md` hosts VOC, FP, I18N-01; `home/app.md` HOM;
`reports/app.md` REP; `integrations/app.md` INT; `billing/app.md` NFR-05; `shared` hosts
NFR-01..04, I18N-02 is `frontend`-owned but listed under `shared`).
Scenario tests: `tests_scenarios.py` has one test method per `@integration` scenario, named
`test_<SCENARIO_ID_lowercased_with_underscores>` with the scenario ID as the first line of
the docstring, decorated `@skip("pending: <SCENARIO-ID>")` until built.
`@e2e` scenarios map to `frontend/tests/e2e/<app>.journey.spec.ts` with the ID in the
test title and `test.fixme(...)` until built.

## Ownership (write only inside your area; report anything you need from another area)
- Backend agent: `backend/**` except `backend/apps/*/app.md` and `backend/apps/*/tests_scenarios.py`;
  plus root `generate-types.sh`, `.env.example`.
- Frontend agent: `frontend/**`, plus `design/screens/*.html` cards it cuts.
- Docs agent: `CLAUDE.md`, `README.md`, `.cursor/rules/*.mdc`, `docs/**` (extend, never
  regenerate the shipped files), `backend/apps/*/app.md`, `backend/apps/*/tests_scenarios.py`
  (skipped stubs only; each file must import unittest.skip and django.test.TestCase and
  contain nothing else executable).
- CI agent: `.github/**`, `.gitleaks.toml`, `.gitattributes`, `.editorconfig`, `.dockerignore`
  (root), `.github/dependabot.yml`, `.github/scripts/codeql_gate.py`, `scripts/` at root
  for licence + container scan helpers if needed.
- The orchestrator owns `docker-compose.yml`, `infra/**`, commits and pushes. Do NOT commit.

## Conventions every agent follows
- Comments explain *why*, name the playbook section or incident, carry the number.
- Every threshold is a setting with an env override. Tests use fixtures, never hardcodes.
- snake_case in the database, camelCase in the API (Ninja alias generator).
- No `admin.py` anywhere. No `**kwargs` in endpoints or logic. No bare `except Exception:`.
- No `console.log`; `logger` only. No PII or tenant content in logs.
- Playwright ≥ 1.61: `browserContext.credentials` is the virtual WebAuthn authenticator
  (verified 2026-09-19 in Playwright docs). Never inject tokens or cookies in E2E.
- Deliver whole, working, tested pieces. Run your own gates before reporting. Report
  exactly what is done, what is not, and every deviation from this brief.
