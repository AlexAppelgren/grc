# ADR 0003 — py_webauthn with our own thin endpoints

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-03; nothing for the owner to confirm now)

## Context

The sign-in rules are few, specific and product invariants: invitation only,
a code that works once and switches off after the first passkey, no
fallback, admin-driven recovery, tenant credential policy, step-up on listed
actions (PRD ID-01 to ID-06, INPUT_DELTAS §2). A generic auth framework
ships password flows, social login and recovery paths we would spend more
effort disabling than using. `webauthn` (py_webauthn) 3.0.0 is the newest
release on PyPI (verified 2026-09-19).

## Decision

Use `webauthn` 3.0.0 for the registration and assertion ceremonies, and
write the endpoints ourselves under `/auth` (request code, verify code,
passkey registration options and verify, sign-in options and verify, step-up
options and verify, refresh, sign-out) and `/me` (passkeys, sessions), with
`SessionAuth`, `EnrolmentAuth` and `ApiKeyAuth` in `apps/shared`. Deliberately
not done: django-allauth or any framework with a password model; SSO is
decided at R3 (D-15 timing, ID-12) and never adds a password.

## Consequences

Easier: every rule is a few lines we own and test per scenario. Harder: we
own the ceremony plumbing, challenge storage and session rotation, so the
identity scenarios (ID-S1 to ID-S26) carry the proof. To remember: fetch the
py_webauthn documentation before implementing each ceremony and record it in
the verification log; never recall it.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Auth classes, permissions, `EnrolmentAuth` | Phase 0 (shared) |
| 2 | Invitation, code, ceremonies, sessions, step-up | Chunk 1 |
| 3 | Credential and session policy as tenant settings | Chunk 11 |
