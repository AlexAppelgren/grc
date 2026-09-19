# Compliance Watch (bleqq)

A compliance inventory and regulatory watch platform for enterprise banks in
the Nordics. Research agents find and propose, people decide, every decision
is logged.

## Quick start

Requirements: Docker Desktop (or a local PostgreSQL 16 with pgvector and
Redis), Python 3.12, Poetry 2.0.1, Node 22.18.

```bash
docker compose up -d db redis                 # Postgres 16 + pgvector with the cw_migrator / cw_app roles, Redis

cd backend
./run.sh install                              # or ./run.ps1 on PowerShell
cp ../.env.example .env                       # local defaults work as they are
./run.sh run python manage.py migrate         # runs as cw_migrator
./run.sh run python manage.py runserver       # http://localhost:8000/api/v1, /health/

cd ../frontend
npm ci
npm run build:tokens                          # Green tokens -> src/styles/tokens.generated.css
npm run dev                                   # http://localhost:3000

bash generate-types.sh                        # openapi.json -> frontend/src/types/api.generated.ts
```

Tests: `cd backend && ./run.sh run python manage.py test apps --settings=config.test_settings`,
`cd frontend && npm run test:coverage`, `npm run test:e2e` (real stack, passkey
sign-in through the UI). The full pre-push checklist is in `CLAUDE.md` §7.

Without Docker: install PostgreSQL 16 with the pgvector package and Redis, run
`infra/db/init.sql` as the superuser against a database named
`compliance_watch`, keep the same roles and passwords. There is no SQLite.

## Where things are

| Read | For |
|---|---|
| `CLAUDE.md` | Agent context: invariants, stack, commands, conventions |
| `PRD.md` | The requirements, with IDs |
| `docs/PLAYBOOK.md` | How we build and what never bends |
| `docs/CONVENTIONS.md` | Architecture and conventions reference |
| `docs/DECISIONS.md`, `docs/adr/` | Open decisions, their defaults, the ADRs |
| `docs/plans/` | Solution design, build plan, backlog, status ledger, verification log |
| `docs/runbooks/` | Railway deploy, variables, DNS and RP ID, first run |
| `docs/TODO_FOR_alex.md` | What needs a person |
| `design/` | The prototype (flow, wording, pills), system cards, brand |
| `backend/apps/<app>/app.md` | Each app's spec and scenarios |
