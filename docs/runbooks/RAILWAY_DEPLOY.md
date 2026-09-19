# Railway test deploy

For Alex. The agent keeps this file true as services land. Verify names and
menus in the Railway console: this was written without access to it.

## Project shape (region: EU West)

| Service | Source | Start command | Notes |
|---|---|---|---|
| `db` | Postgres with pgvector template | | Enable point-in-time recovery. Run the role script below once |
| `redis` | Redis | | Celery broker and cache |
| `bucket` | Private S3-compatible bucket | | Evidence and exports. Required on every deployed environment, the test one included: the app refuses to boot on the local file backend when deployed (`STORAGE_BACKEND=s3`) |
| `api` | `backend/Dockerfile` | default entrypoint | Migrates as `cw_migrator` (the entrypoint runs `manage.py migrate` with `DATABASE_URL=$MIGRATOR_DATABASE_URL`), seeds reference data, starts gunicorn as `cw_app` |
| `worker` | same image | `celery -A config worker` | |
| `beat` | same image | `celery -A config beat` | Exactly one instance |
| `web` | `frontend/Dockerfile` | `next start` | Custom domain attached here |

## Database roles (once, as the template's superuser)

```sql
CREATE ROLE cw_migrator LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;
CREATE ROLE cw_app      LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;
GRANT ALL ON DATABASE railway TO cw_migrator;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

The first migration grants `cw_app` its table privileges and sets default
privileges for later tables. The app refuses to boot if `DATABASE_URL` points
at a role that can bypass row-level security.

## Variables

| Variable | Service | Value |
|---|---|---|
| `ENVIRONMENT` | all | `test`, the one deployed name where mock adapters and demo data are allowed. The UI shows a banner while any mock is active |
| `DATABASE_URL` | api, worker, beat | the `cw_app` connection string |
| `MIGRATOR_DATABASE_URL` | api | the `cw_migrator` connection string |
| `REDIS_URL`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` | api, worker, beat | |
| `PRODUCT_NAME` | api, web | `bleqq compliance` |
| `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGINS` | api | the exact test host, and its `https://` origin |
| `STORAGE_*` | api, worker | bucket endpoint, name, keys |
| `MAIL_*` | api, worker | the transactional sender |
| `LLM_PROVIDER`, `ANTHROPIC_API_KEY` | api, worker | `anthropic` |
| `EMBEDDER_PROVIDER`, its key | api, worker | per D-09 |
| `AGENT_RUNNER` | worker | `mock` until chunk 11 |
| `SENTRY_DSN` | all | optional, EU region |
| `NEXT_PUBLIC_API_URL` | web | the api's public URL |

## First run

1. Deploy `db`, `redis`, `bucket`. Run the role script.
2. Deploy `api`. Check `/health/` answers 200 with every component named.
3. Deploy `worker`, `beat`, `web`. Attach the test host to `web`.
4. `python manage.py bootstrap_platform --admin-email you@…` (lands with chunk 1; after Phase 0 only `seed_reference`, `seed_e2e`, `migrate_from_zero` and `export_openapi` exist) creates the first
   platform admin invitation. Open the emailed link, enter the code, enrol a
   passkey.
5. In the console, create the first tenant and invite its admin.
6. Optional: `python manage.py seed_demo` (lands with chunk 3) loads the prototype's sample data
   into a demo tenant. It refuses to run when `ENVIRONMENT` is a production
   name.
