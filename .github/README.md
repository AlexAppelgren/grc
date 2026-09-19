# CI for Compliance Watch

What runs, when, for how long, and what it needs. The gates themselves are
listed in the comment block at the top of `workflows/ci.yml` and defined in
`docs/PLAYBOOK.md` Section 9. Every gate blocks; nothing is advisory.

## Workflows

### `workflows/ci.yml`

Triggers: `push` to `main`, `pull_request`, `schedule` at 02:30 UTC
(04:30 Stockholm, away from local midnight) and `workflow_dispatch`.
Concurrency cancels in-flight runs on the same ref; scheduled runs are never
cancelled. The nightly run and manual runs execute everything in full.

| Job | Runs when | Timeout | What it does |
|---|---|---|---|
| `changes` | always | 5 min | `dorny/paths-filter` with `base: github.ref_name` on push and extglob patterns decides which areas changed. Schedule, manual runs and any change under `.github/` mean everything runs |
| `backend` | backend area changed, or full | 30 min | pgvector + Redis services, `infra/db/init.sql` applied, then in order: migration drift, `migrate_from_zero`, tests under coverage, `coverage report`, `coverage_gate.py`, ruff, mypy, `compliance_check.py --all`, `requirements_coverage.py`, `contract_drift.py`, `search_eval.py` |
| `openapi-types-drift` | backend or frontend changed, or full | 15 min | `bash generate-types.sh`, then `git diff --exit-code` on `openapi.json` and `frontend/src/types/api.generated.ts` (both must be tracked) |
| `frontend` | frontend area changed, or full | 20 min | `build:tokens`, `lint`, `typecheck`, `test:coverage`, `check:messages`, `check:copy-drift`, `build` |
| `e2e` | backend or frontend changed, or full | 60 min | Same services and init; Chromium; `npm run test:e2e -- --grep @smoke` on push and PR, the full suite on schedule and manual runs. Uploads `frontend/test-results` and `frontend/playwright-report` on failure, kept 14 days. The pill gallery screenshot compare lives in this suite |
| `secrets` | always | 10 min | `gitleaks/gitleaks-action` over the full history with `.gitleaks.toml` (`GITLEAKS_CONFIG`), gitleaks pinned to 8.30.1 |
| `cve` | lockfiles changed, or full (so every night) | 15 min | Refuses to run on a missing or empty lockfile; `osv-scanner` on the committed `backend/poetry.lock` and `frontend/package-lock.json`; `npm audit --audit-level=high`; both under `bash -eo pipefail` |
| `licences` | lockfiles changed, or full | 20 min | `scripts/check_licences.py`: no AGPL/GPL/SSPL in either tree, Apache attribution for `@sebgroup/*` in `frontend/THIRD_PARTY_NOTICES.md`. Exceptions with reason and date in `scripts/licence_exceptions.json`; stale exceptions fail |
| `container-scan` | Dockerfiles or lockfiles changed, or full | 30 min | Builds `backend/Dockerfile` and `frontend/Dockerfile` (matrix), Trivy on the images: HIGH and CRITICAL, unfixed included, exit code 1 |

"Lockfiles" means `backend/poetry.lock`, `backend/pyproject.toml`,
`frontend/package-lock.json`, `frontend/package.json`,
`frontend/THIRD_PARTY_NOTICES.md` and `scripts/**`.

Timeouts are first estimates. Retune each to roughly twice the slowest
observed run once there are observations (playbook 9).

### `workflows/codeql.yml`

Triggers: same as `ci.yml`. One job, `analyze`, matrix over `python` and
`javascript-typescript`, 45 min each, `security-extended` queries, SARIF
uploaded to code scanning and kept as an artefact for 14 days. Then
`scripts/codeql_gate.py` fails the job on any finding of medium severity or
above (security-severity 4.0+, or level `error`/`warning` for rules with no
security severity) unless it is accepted per fingerprint in
`codeql-accepted.json` with a reason and a date, and fails on any acceptance
that no longer matches a finding. Thresholds: `CODEQL_GATE_MIN_SECURITY_SEVERITY`
(default 4.0) and `CODEQL_GATE_FAIL_LEVELS` (default `error,warning`).

To accept a finding: copy `ruleId` and `partialFingerprints.primaryLocationLineHash`
from the SARIF artefact into `codeql-accepted.json` with `language`, `path`,
`reason`, `acceptedOn` and `acceptedBy`. When an adjacent edit rehashes a
fingerprint, re-triage at the new location before re-keying.

### `dependabot.yml`

Weekly, Monday 06:00 Stockholm, grouped per ecosystem, targeting `main`:
pip in `/backend`, npm in `/frontend`, github-actions in `/`. Majors a peer
dependency cannot take are ignored by name with the reason in the file
(Django 6 per D-17, TypeScript majors, React majors until Next takes them,
`@next/eslint-plugin-next`, `@tailwindcss/postcss`).

## Composite actions (`actions/`)

| Action | Purpose |
|---|---|
| `setup-backend` | Poetry 2.0.1 via pipx, Python 3.12 with the Poetry cache keyed on `backend/poetry.lock`, `bash ./run.sh install --no-interaction --no-root` |
| `setup-frontend` | Node 22 with the npm cache keyed on `frontend/package-lock.json`, `npm ci` |
| `init-db` | Applies `infra/db/init.sql` as `postgres` inside the pgvector service container (the compose volume mount only runs locally) and proves `cw_app` cannot bypass RLS |

## Services

Both `backend` and `e2e` run against `pgvector/pgvector:pg16` (superuser
`postgres` / `postgres-dev-only`, database `compliance_watch`) and
`redis:7-alpine`, the same images as `docker-compose.yml`. The job `env`
carries `DATABASE_URL` (as `cw_app`), `MIGRATOR_DATABASE_URL` (as
`cw_migrator`), `REDIS_URL` and `ENVIRONMENT=ci`; `e2e` adds `E2E_MODE=true`,
`CI=true` and `NEXT_PUBLIC_API_URL`.

## Secrets and variables

None beyond the automatic `GITHUB_TOKEN` in Phase 0. Permissions are
`contents: read` and `pull-requests: read` at the top of both workflows
(the latter so a Dependabot token can run the paths filter). `codeql.yml`
raises `security-events: write` and `actions: read` on its one job to upload
SARIF. `gitleaks-action` needs a licence key only for organisation accounts;
this repository is under a personal account. If it moves to an organisation,
add `GITLEAKS_LICENSE` as a repository secret and pass it in the `secrets` job.

## Pinned actions

Every `uses:` is pinned to a full commit SHA with the version tag beside it.
Dependabot's github-actions group keeps them moving.

| Action | Version | SHA |
|---|---|---|
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `dorny/paths-filter` | v4.0.3 | `ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d` |
| `actions/setup-python` | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/setup-node` | v7.0.0 | `820762786026740c76f36085b0efc47a31fe5020` |
| `actions/cache` | v6.1.0 | `55cc8345863c7cc4c66a329aec7e433d2d1c52a9` |
| `actions/upload-artifact` | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |
| `gitleaks/gitleaks-action` | v3.0.0 | `e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e` |
| `google/osv-scanner-action` | v2.6.0 | `a345acffa64b0eaede81a3d9aae6141214d9c8fc` |
| `aquasecurity/trivy-action` | v0.36.0 | `ed142fd0673e97e23eac54620cfb913e5ce36c25` |
| `docker/setup-buildx-action` | v4.4.1 | `f87e5991a6d7451dcb8d9637bfbc97413f497069` |
| `docker/build-push-action` | v7.4.0 | `c3c9e263c25d99ce0380d002d59b67737d91b0dc` |
| `github/codeql-action` | v4.38.1 | `1c5b675653bb5c22dbe9b12b556ec555138e09fd` |

## Running the gates locally

Appendix D of the playbook lists the same commands. The licence gate:

```bash
cd backend && bash ./run.sh run python ../scripts/check_licences.py backend
cd .. && python scripts/check_licences.py frontend
```

The CodeQL gate needs a SARIF file; download the artefact from a run and
point `--sarif-dir` at it. Workflow syntax: `actionlint .github/workflows/*.yml`.
