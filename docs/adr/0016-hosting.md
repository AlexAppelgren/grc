# ADR 0016 — Railway EU West, container-only, nothing Railway-specific in code

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-16; nothing for the owner to confirm now)

## Context

Data must stay in the EU (GDPR, DORA, the assurance pack of playbook 18).
Railway offers an EU West region, Postgres templates with pgvector and
private S3-compatible buckets, known from the Compliance Watch chat and to be
verified in the Railway console when the project is created
(`Verification_Log.md`). A bank may require the tenant zone inside its own
environment later (ADR 0024).

## Decision

Deploy every service (api, worker, beat, web, db, redis, bucket) in Railway
EU West, container-only and twelve-factor: configuration through
environment variables, the entrypoint migrating as the migrator role and
seeding reference data, `RAILWAY_ENVIRONMENT_NAME` read only to detect a
deployed environment. Deliberately not done: Railway SDKs, Railway-specific
build hooks, or any host-specific path in application code.

## Consequences

Easier: the same image runs on any container host, which is what
portability needs. Harder: Railway's console names and menus are verified
by the owner, not the agent (`docs/runbooks/RAILWAY_DEPLOY.md`). To remember:
the owner deploys; the agent keeps the Dockerfiles, the entrypoint and the
runbooks true.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Dockerfiles, entrypoint, `/health/`, runbooks | Phase 0 |
| 2 | Owner creates the project and services | Before the first test deploy |
