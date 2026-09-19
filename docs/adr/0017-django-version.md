# ADR 0017 — Django 5.2 LTS

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-17; nothing for the owner to confirm)

## Context

Verified on PyPI 2026-09-19: Django 5.2.17 is the newest patch of the 5.2
LTS line; Django 6.1.1 exists. django-stubs 5.2.9 tracks the 5.2 line. A
bank product wants a long support window more than the newest features, and
the type stubs, django-ninja 1.7.0 and the rest of the stack are proven
against 5.2.

## Decision

Pin Django 5.2.17 and django-stubs 5.2.9 (ADR 0019 lists every pin). Move to
the next LTS when it is released and the stack supports it, as a new ADR.
Deliberately not done: Django 6.x.

## Consequences

Easier: security patches without behaviour changes for the support window.
Harder: features that landed in 6.x are unavailable; none is needed by the
PRD. To remember: Dependabot ignores the Django major by name with this
reason.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Pin in `backend/pyproject.toml` | Phase 0 |
