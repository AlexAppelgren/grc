# ADR 0002 — WebAuthn RP ID is the exact app host per environment

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-02; the owner confirms the production host before any real user enrols)

## Context

A passkey is bound to one relying-party ID. Any origin under the RP ID can
ask for the credential, so a broad RP ID (`bleqq.com`) would let every other
bleqq.com site request these credentials. Verified 2026-09-19
(`docs/plans/Verification_Log.md`): a passkey belongs to one RP ID; Related
Origin Requests let a second origin use the same credentials via
`/.well-known/webauthn` in Chrome and Edge 128, Safari 18 and Firefox 152.
Passkeys created on a `*.up.railway.app` host stop working the day the host
changes, which is why a stable test host matters before anyone enrols.

## Decision

`WEBAUTHN_RP_ID` is the exact app host of each environment, read from
settings, with `WEBAUTHN_ORIGINS` the matching `https://` origins. Proposed
production host `compliance.bleqq.com`; test host per
`docs/runbooks/DNS_DOMAINS.md`. Deliberately not done: a registrable-domain
RP ID, and any environment-derived default in code.

## Consequences

Easier: no other site under the brand domain can touch these credentials.
Harder: a rebrand or host move means re-enrolment, or keeping the old host
alive and serving `/.well-known/webauthn` for Related Origin Requests. To
remember: test deploys use throwaway passkeys; the owner confirms the
production host before the first real enrolment (`docs/TODO_FOR_alex.md`).

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Settings, boot check that the RP ID is set when deployed | Chunk 1 |
| 2 | Test host attached and RP ID set | Owner, before the first test deploy |
