# Variables

Every variable the backend and the web app read, and where each lives.
`backend/config/settings.py` reads them; `.env.example` lists them all with
a comment and no real value. Secrets live only in Railway variables and
GitHub encrypted secrets. Dev-only secrets are literal strings ending in
`-dev-only` or starting `django-insecure-`, allowlisted by exact literal in
`.gitleaks.toml`.

## Environment detection

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `ENVIRONMENT` | api, worker, beat | `local` | `ci` | `test` | `local`, `test` and `ci` are the only names that are not "deployed". Anything else (including `prod`, `Production`, `demo`, `dev`, or unset) fails closed with every guard on. `test` is the one deployed name where mock adapters are allowed and the UI shows a banner |
| `RAILWAY_ENVIRONMENT_NAME` | all | unset | unset | set by Railway | Presence alone means deployed, whatever `ENVIRONMENT` says |
| `DEBUG` | api | `true` | `false` | `false` | Refused when deployed |
| `SECRET_KEY` | api, worker, beat | `django-insecure-dev-only` | a generated value | Railway secret | A missing or default value is refused outside DEBUG |

## Database and cache

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `DATABASE_URL` | api, worker, beat | `postgres://cw_app:cw-app-dev-only@localhost:5432/compliance_watch` | the `cw_app` string against the service container | the `cw_app` connection string | The app refuses to boot if this role is a superuser, owns the tables or has `BYPASSRLS` (ADR 0022) |
| `MIGRATOR_DATABASE_URL` | api (entrypoint), CI | `postgres://cw_migrator:cw-migrator-dev-only@localhost:5432/compliance_watch` | the `cw_migrator` string | the `cw_migrator` connection string | Used only by `migrate`, `migrate_from_zero` and the test runner's database creation |
| `REDIS_URL` | api, worker, beat | `redis://localhost:6379/0` | the service container | Railway Redis URL | Celery broker and cache |

## Hosts and identity

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `ALLOWED_HOSTS` | api | `localhost,127.0.0.1` | `localhost` | the api host | Explicit, never `*` |
| `CORS_ALLOWED_ORIGINS` | api | `http://localhost:3000` | `http://localhost:3000` | `https://<web host>` | Scoped to `/api/` |
| `PRODUCT_NAME` | api, web | `Compliance Watch` | same | `bleqq compliance` | The display name; a rebrand is a variable |
| `WEBAUTHN_RP_ID` | api | `localhost` | `localhost` | the exact test host (`DNS_DOMAINS.md`) | A passkey belongs to one RP ID (D-02, ADR 0002). Required when deployed |
| `WEBAUTHN_ORIGINS` | api | `http://localhost:3000` | `http://localhost:3000` | `https://<test host>` | Comma-separated allowed origins for the ceremonies |

## Storage, mail, models, agents

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `STORAGE_BACKEND` | api, worker | `local` | `local` | `s3` | `local` is refused when deployed |
| `STORAGE_*` (`STORAGE_ENDPOINT`, `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_REGION`) | api, worker | unset | unset | the private bucket's values | Only read when `STORAGE_BACKEND=s3` |
| `MAIL_PROVIDER` | api, worker | `mock` | `mock` | `smtp` | A mock mailer is refused when deployed except in `test` |
| `MAIL_*` (`MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`) | api, worker | unset | unset | the EU transactional sender | SPF and DKIM on the sending domain |
| `LLM_PROVIDER` | api, worker | `mock` | `mock` | `anthropic` | `mock`, `anthropic`, `bedrock` (D-07, ADR 0007) |
| `ANTHROPIC_API_KEY` | api, worker | unset | unset | Railway secret | Only read when `LLM_PROVIDER=anthropic` |
| `EMBEDDER_PROVIDER` | api, worker | `mock` | `mock` | per D-09 | Plus the provider's key variable once D-09 is decided; until then the test deploy searches by keyword only |
| `RERANKER_PROVIDER` | api, worker | `mock` | `mock` | `none` until D-09 names one | `mock` is refused when deployed except in `test`; `none` leaves the fused order as the answer |
| `RERANKER_TOP_K` | api, worker | `50` | `50` | `50` | How many fused hits the reranker is given (SRC-01) |
| `AGENT_RUNNER` | worker | `mock` | `mock` | `mock` until chunk 11 | `mock` or `managed_agents` (D-08, ADR 0008) |

## Testing, observability, budgets

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `E2E_MODE` | api (E2E only) | set by Playwright's `webServer` | set by the E2E job | never | Makes the enrolment code deterministic and enables `seed_e2e`. Refused on two independent legs when deployed |
| `SENTRY_DSN` | all | unset | unset | optional, EU region DSN | `send_default_pii=False`, bodies never sent, scrubbers on events and transactions |
| `API_BUDGET_MS` | api | `250` | `250` | `250` | A WARNING with the request ID above it |

## Web app

| Variable | Services | Local | CI | Railway test | Notes |
|---|---|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | web | `http://localhost:8000` | `http://localhost:8000` | the api's public URL | Baked at build time by Next; a change needs a rebuild |

## Rules

- Every threshold in `settings.py` (code lifetimes, attempts, session
  limits, rate limits, budgets) has an env override named after the setting;
  the defaults are the numbers in the playbook and the PRD. They are not
  listed here individually; `.env.example` is the complete list.
- A new variable is added in four places in one commit: `settings.py`,
  `.env.example`, this file, and the Railway service it belongs to (by the
  owner).
