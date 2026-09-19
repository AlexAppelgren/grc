#!/usr/bin/env bash
# Entrypoint for the API image (playbook 2.2, 12).
#
#   1. Migrate as the migrator role (MIGRATOR_DATABASE_URL owns the tables).
#   2. Run every idempotent reference seed as the app role, in dependency order. Each
#      line below says what silently breaks without it. The last repo shipped four
#      reference seeds that ran nowhere, and every failure was quiet.
#   3. Start gunicorn as the app role (DATABASE_URL: cw_app, no ownership, no BYPASSRLS;
#      the boot guard refuses anything else).
#
# The worker and beat services override the command (`celery -A config worker`,
# `celery -A config beat`) and skip steps 1 and 2 by passing their own command: anything
# other than `serve` is exec'd as given.
set -euo pipefail

if [[ "${1:-serve}" != "serve" ]]; then
    exec "$@"
fi

: "${DATABASE_URL:?DATABASE_URL (cw_app) is required}"
: "${MIGRATOR_DATABASE_URL:?MIGRATOR_DATABASE_URL (cw_migrator) is required}"

echo "entrypoint: migrating as the migrator role"
DATABASE_URL="$MIGRATOR_DATABASE_URL" python manage.py migrate --noinput

echo "entrypoint: reference seeds"
# seed_reference runs every registered seed (apps/shared/management/commands/seed_reference.py).
# Without it: no permissions (every route 403s), no system roles (no invitation can assign
# one), no languages (no label can be stored), no jurisdictions (no instrument can be
# filed), no library vocabularies (agents get unknown_key on everything), no authorities
# (no source can be registered), no agent definitions (no agent can be switched on).
python manage.py seed_reference

echo "entrypoint: starting gunicorn as the app role"
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT_S:-60}" \
    --access-logfile - \
    --error-logfile -
