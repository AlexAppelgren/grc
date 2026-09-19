# ADR 0021 — No Django admin

**Date:** 2026-09-19 · **Status:** accepted by default (playbook 4.3; the owner confirms)

## Context

Django's admin is a second write surface: it bypasses `record()`, ignores
`@requires_permission` and `@requires_step_up`, knows nothing about the
tenant activation that row-level security depends on, and would let a staff
user with a password edit library rows outside a proposal. Every one of
those breaks an invariant in `CLAUDE.md` §5. The Phase 0 brief forbids
`admin.py` anywhere.

## Decision

Zero `admin.py` files, `django.contrib.admin` not installed, no admin URL.
The API with its permissions, step-up and audit is the only write surface;
the platform console (ADM-02) and the tenant admin screens (ADM-01) are
built on it like every other screen. Reference data is seeded by the
entrypoint. Deliberately not done: a read-only admin, because it would still
run without tenant activation and would grow.

## Consequences

Easier: one write path, one audit trail, one permission model. Harder: every
admin need is a screen with empty, loading, error and denied states. To
remember: the compliance lint and CI fail on any `admin.py`; a one-off data
fix is an environment-guarded management command, never an admin edit.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Settings without `contrib.admin`, the lint rule | Phase 0 |
