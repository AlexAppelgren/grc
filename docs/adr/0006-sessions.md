# ADR 0006 — Sessions: in-memory access token, rotating refresh cookie, a row per session

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-06; the owner confirms the default limits)

## Context

Bank customers expect instant revocation of a person's access and limits on
how long a session lives (PRD ID-04, ID-08). The last repo proved a design
of a short-lived access token held in memory plus a rotating refresh token in
a cookie, with one row per session so an admin can revoke at once. NIST SP
800-63-4 guidance on AAL2 re-authentication (12 h absolute, 30 min idle) is
known from secondary sources only (`Verification_Log.md`); the defaults use
those numbers and are settings.

## Decision

Access token in memory (never in storage), rotating refresh token in an
`HttpOnly`, `Secure`, `SameSite=Strict` cookie scoped to the auth path, a
replay grace window (a setting), a `user_session` row behind every refresh.
Defaults: idle 30 minutes, absolute 12 hours, both tenant policy within
platform maximums. Deliberately not done: long-lived bearer tokens in local
storage, and server-side session cookies for the API (the console and the
tenant app share one client).

## Consequences

Easier: revoke a person or a device instantly; a leaked access token dies in
minutes. Harder: the client needs one-flight refresh on 401 and a cold-load
refresh before the first request. To remember: the grace window exists for
concurrent tabs, and a replay after it revokes the whole session (ID-S9).

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | `SessionAuth`, refresh, `user_session`, the api-client refresh flow | Chunk 1 |
| 2 | Tenant session policy screen with platform maximums | Chunk 11 |
