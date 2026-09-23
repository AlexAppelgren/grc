#!/usr/bin/env bash
# Boots the backend for E2E (playbook 8.3): drops and recreates the throwaway E2E
# database, migrates it from zero (which proves the migration graph applies), seeds
# seed_e2e, starts a real Celery worker, then serves Django with the E2E flag and mock
# adapters. Playwright's webServer waits for /health/ on the port below, and /health/
# only answers 200 when the database, pgvector, the cache and the worker all answer, so
# a journey never starts against a half-booted stack.
#
# The server runs under config.settings as cw_app (DATABASE_URL), never as the migrator:
# row-level security must be real in E2E or J-8 proves nothing. Migration and seeding run
# as cw_migrator, exactly as docker-entrypoint.sh does on a deploy.
#
# Two extra modes, both for the cold-start journey (docs/runbooks/FIRST_RUN_SETUP.md):
#
#   E2E_COLD_START=1        boot exactly as a deploy boots — migrate, then seed_reference,
#                           and nothing else. No seed_e2e, no fixture, no extra row.
#   start-backend.sh manage run one management command against this same database as
#     <command> [args...]   cw_app and exit, the way a person runs one on the api shell.
#
# Both keep E2E_MODE and the mock adapters, so the emailed code stays deterministic and
# no mail or model call leaves the machine. The Playwright config gives the cold-start
# run its own database name and its own ports, so it can never touch the seeded run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
BACKEND="$ROOT/backend"
PORT="${E2E_BACKEND_PORT:-8000}"
E2E_DB="${E2E_DATABASE_NAME:-compliance_watch_e2e}"

if [ ! -f "$BACKEND/run.sh" ]; then
  echo "start-backend: $BACKEND/run.sh is missing. The backend is not in this checkout, so E2E cannot run." >&2
  echo "start-backend: build the backend (playbook 2.2) or, for the gallery/spike specs only, set E2E_SKIP_BACKEND=1." >&2
  exit 1
fi

cd "$BACKEND"

# Run the venv's own interpreter, not `poetry run`. Poetry's shim chain (shim, poetry,
# poetry again, python re-exec) breaks the parent link, so when Playwright tears the
# webServer down with `taskkill /T` on Windows the server and the worker survive as
# orphans holding the stdout pipe, and the run never exits (observed 2026-09-19: four
# specs green, then an eight-minute hang). Direct children die with their parent.
VENV_PATH="$(bash ./run.sh env info --path)"
if command -v cygpath >/dev/null 2>&1; then VENV_PATH="$(cygpath -u "$VENV_PATH")"; fi
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) PY="$VENV_PATH/Scripts/python.exe"; CELERY="$VENV_PATH/Scripts/celery.exe" ;;
  *) PY="$VENV_PATH/bin/python"; CELERY="$VENV_PATH/bin/celery" ;;
esac
if [ ! -x "$PY" ]; then
  echo "start-backend: no interpreter at $PY. Run 'bash backend/run.sh install' first." >&2
  exit 1
fi

# Same defaults as .env.example. CI and a laptop with docker compose both match them.
APP_URL="${DATABASE_URL:-postgres://cw_app:cw-app-dev-only@localhost:5432/compliance_watch}"
MIGRATOR_URL="${MIGRATOR_DATABASE_URL:-postgres://cw_migrator:cw-migrator-dev-only@localhost:5432/compliance_watch}"
# Swap the database name at the end of each URL for the E2E database.
APP_E2E_URL="${APP_URL%/*}/$E2E_DB"
MIGRATOR_E2E_URL="${MIGRATOR_URL%/*}/$E2E_DB"

export ENVIRONMENT=test
export E2E_MODE=1
export DEBUG=0
export LLM_PROVIDER=mock
export EMBEDDER_PROVIDER=mock
export AGENT_RUNNER=mock
export MAIL_PROVIDER=mock
export STORAGE_BACKEND=local
# No persistent connections under runserver: it starts a thread per request, and each
# thread's connection outlives it, so with a max age every request leaks one until
# Postgres runs out of slots (CI, 2026-09-23: "too many clients already" after 84
# journeys). Django's own guidance for the development server; gunicorn keeps its default.
export DATABASE_CONN_MAX_AGE_S=0
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/1}"
export CORS_ALLOWED_ORIGINS="${CORS_ALLOWED_ORIGINS:-http://localhost:3000}"
export WEBAUTHN_RP_ID="${WEBAUTHN_RP_ID:-localhost}"
export WEBAUTHN_ORIGINS="${WEBAUTHN_ORIGINS:-http://localhost:3000}"
export MIGRATOR_DATABASE_URL="$MIGRATOR_E2E_URL"

# `manage`: one command against the database this script boots, as cw_app, then exit.
# Nothing is recreated and nothing is seeded, so it is only ever run while the stack is
# up. bootstrap_platform is not exempt from the database role guard (config/settings.py),
# which is the point: a person runs it on the api service, as the app role, under
# row-level security, and so does the journey.
if [ "${1:-}" = "manage" ]; then
  shift
  export DATABASE_URL="$APP_E2E_URL"
  exec "$PY" manage.py "$@"
fi

echo "start-backend: recreating $E2E_DB and migrating from zero (as cw_migrator)"
DATABASE_URL="$MIGRATOR_URL" "$PY" manage.py migrate_from_zero --name "$E2E_DB" --keep

if [ "${E2E_COLD_START:-0}" = "1" ]; then
  # What a deploy does and no more (backend/docker-entrypoint.sh): the reference seeds as
  # cw_app, then serve. Everything the cold-start journey needs, a first deploy has too.
  echo "start-backend: cold start, seeding reference data only (as cw_app)"
  DATABASE_URL="$APP_E2E_URL" "$PY" manage.py seed_reference
else
  echo "start-backend: seeding seed_e2e (as cw_migrator)"
  DATABASE_URL="$MIGRATOR_E2E_URL" "$PY" manage.py seed_e2e
fi

export DATABASE_URL="$APP_E2E_URL"

# A real worker, so /health/ tells the truth. --pool=solo runs on Windows and Linux alike.
# Its output goes to a file, not the inherited pipe: a background child holding
# Playwright's stdout pipe open is the other way a run can hang after the last test.
WORKER_LOG="${E2E_WORKER_LOG:-$ROOT/frontend/test-results/e2e-worker.log}"
mkdir -p "$(dirname "$WORKER_LOG")"
echo "start-backend: starting a Celery worker (log: $WORKER_LOG)"
"$CELERY" -A config worker --pool=solo --loglevel=warning --without-gossip --without-mingle   >"$WORKER_LOG" 2>&1 </dev/null &
WORKER_PID=$!
cleanup() {
  kill "$WORKER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "start-backend: serving on 127.0.0.1:$PORT (as cw_app)"
"$PY" manage.py runserver "127.0.0.1:$PORT" --noreload
