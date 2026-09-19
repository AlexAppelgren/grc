#!/usr/bin/env bash
# Makes a Claude Code cloud session ready to build and test this repository
# (docs/runbooks/WORKTREES.md, "Cloud tasks"). Idempotent: run it first in every session.
#
#   bash scripts/cloud-setup.sh            database, backend and frontend
#   bash scripts/cloud-setup.sh --e2e      the same, plus Playwright's Chromium for E2E
#
# Written from a probe of the cloud environment on 2026-09-19: Ubuntu 24.04, passwordless
# sudo, PostgreSQL 16 and Redis 7 installed but stopped, Ubuntu's pgvector too old (0.6), no
# Docker daemon by default, Python 3.11 as `python3` with 3.12 beside it, Node 22.22.
# It gives the session exactly what docker-compose.yml gives a laptop: the same roles,
# passwords, database and extensions (infra/db/init.sql), on the same ports.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"; cd "$root"
say() { echo "cloud-setup: $*"; }
[ "$(uname -s)" = Linux ] || { echo "cloud-setup: for the Linux cloud session only" >&2; exit 1; }
e2e=0; [ "${1:-}" = --e2e ] && e2e=1

# PostgreSQL 16 with pgvector from the PGDG repository: CI's image (pgvector/pgvector:pg16)
# carries 0.8, and Ubuntu's own package is 0.6.
if ! dpkg -s postgresql-16-pgvector >/dev/null 2>&1 || ! apt-cache policy postgresql-16-pgvector | grep -q pgdg; then
  say "installing PostgreSQL 16 and pgvector from apt.postgresql.org"
  sudo install -d /usr/share/postgresql-common/pgdg
  sudo curl -fsS -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc
  . /etc/os-release
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
    | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-16 postgresql-16-pgvector >/dev/null
fi
sudo pg_ctlcluster 16 main start 2>/dev/null || true
pg_lsclusters | grep -q "16 *main.*online" || { echo "cloud-setup: PostgreSQL did not start" >&2; exit 1; }
redis-cli ping >/dev/null 2>&1 || redis-server --daemonize yes --save '' --appendonly no >/dev/null

# Roles, database and extensions: the script the local db container runs once.
if ! sudo -u postgres psql -tAc "select 1 from pg_database where datname = 'compliance_watch'" | grep -q 1; then
  say "creating roles, the database and extensions (infra/db/init.sql)"
  sudo -u postgres psql -qc "ALTER USER postgres PASSWORD 'postgres-dev-only';"
  sudo -u postgres createdb compliance_watch
  sudo -u postgres psql -q -v ON_ERROR_STOP=1 -f infra/db/init.sql >/dev/null
fi

# Python 3.12 and Poetry 2.0.1, CI's pins. Poetry follows the active `python`, which is 3.11
# here, so the virtualenv is made with 3.12 first and Poetry adopts it.
if ! poetry --version 2>/dev/null | grep -q "2.0.1"; then
  if command -v uv >/dev/null; then uv tool install --force "poetry==2.0.1" >/dev/null
  else pipx install --force "poetry==2.0.1" >/dev/null; fi
  hash -r
fi
if [ ! -x backend/.venv/bin/python ] || ! backend/.venv/bin/python --version | grep -q "3.12"; then
  rm -rf backend/.venv && python3.12 -m venv backend/.venv
fi
say "installing backend dependencies"
(cd backend && bash ./run.sh install --no-interaction --no-root >/dev/null)

node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a===22&&b>=19?0:1)' \
  || { echo "cloud-setup: Node $(node --version) is below 22.19 (CLAUDE.md section 4)" >&2; exit 1; }
say "installing frontend dependencies"
(cd frontend && npm ci --no-audit --no-fund >/dev/null && npm run -s build:tokens)
if [ "$e2e" = 1 ]; then
  say "installing Playwright's Chromium"
  (cd frontend && npx playwright install --with-deps chromium >/dev/null)
fi
say "ready: PostgreSQL 16 with pgvector on 5432, Redis on 6379, backend/.venv (Python 3.12), frontend/node_modules"
