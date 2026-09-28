# ADR 0063 — The access token signs the session's bank, and a request resolves in it

**Date:** 2026-09-28 · **Status:** accepted (owner approval of the query and request audit's wave B, 2026-09-28; perf-tenant-in-token; amends ADR 0006 and the resolver of playbook 14)

## Context

The query and request audit of 2026-09-28 (`docs/plans/r2-waves/PERF_AUDIT.md`, finding 1)
measured a fixed cost of eight queries on every request, six of them the auth layer's.
Wave A took it to four before the route: switch the identity-lookup flag on, read the session
with its person and bank, switch the flag off with the bank activated, read the membership's
grants with the latest step-up. The flag exists because the access token named only a session,
so its bank was unknown until the session row was read, and `user_session` sits under forced
row-level security. Alex approved taking the cost further by putting the tenant id in the
signed token.

## Decision

- **The token signs the bank.** An access token is
  `v2.<session id>.<kind>.<tenant id>.<expiry>.<HMAC-SHA-256 over all of it>` with
  SECRET_KEY, the tenant part empty for a session in no bank (a console session, a bank-less
  enrolment session). The claim is copied from the stored session each time a token is issued
  (sign-in, support entry, refresh), never from anything the client sends.
- **A request resolves in the claimed zone.** The resolver checks the signature, activates the
  claimed bank (`tenancy.activate`) or, for an empty claim, no bank (`tenancy.clear_tenant`),
  in one statement, then reads in one statement under it the session, its person with their
  locale, its bank with its default language, the membership's grants and the latest step-up
  (platform grants only for a session in no bank). Two queries where there were four; the
  request's fixed cost goes from six (wave A) to four with the transaction's open and close.
- **The claim must be the row's.** Row-level security shows the session only in its own zone,
  and a console session's row to a bank as well (`user_session` is a mixed table). The resolver
  refuses, with 401, a claim the zone did not show and a row whose bank is not the claim. It
  then looks the row up by id through the identity lookup, leaves the claimed bank for the
  row's own zone (or no bank when there is no row), and when the row stands in another zone
  than the claim it writes `access_token_refused` with `tenant_claim_mismatch` to the security
  log in the session's own zone and ends the session (`session_revoked`, same reason).
- **The per-request path never opens the identity lookup.** The identity-lookup clause stays on
  the same five tables and the RLS guard is unchanged: sign-in still picks a bank through it,
  the refresh cookie still finds its session through it, and the refusal above looks up one
  `user_session` row by its id. The guard of its callers (`apps/shared/tests_tenancy.py`)
  narrows the session module from the whole module to those three functions, so a request's
  credential can no longer reach it, and names the resolver as the one place a console
  session's empty claim asserts no bank, beside `resolve_api_key` for a platform key.
- **Unchanged:** forced row-level security on every tenant table, the `cw_app` role without
  `BYPASSRLS` and the boot guard, the per-request checks of revocation, expiry, a deactivated
  person, the membership, the permission, the support grant and the step-up.

## Threat model

| Case | What happens |
|---|---|
| A forged claim, without the key | The HMAC fails: 401 before any query. |
| A forged claim, with the key (another bank on a real session) | The claimed bank shows no row, or shows a console row the comparison refuses: 401, logged, the session ended. The request is left in the session's own zone, and nothing of the claimed bank is read beyond the one statement that found nothing. A key holder can already forge any session's token, so the claim adds no power; the log is the tripwire. Only a key holder can trigger the refusal's writes, so they cannot be flooded. |
| A stale claim: a token from before this change (v1) | Refused (401) by its format, not logged; the session is not touched. |
| A stale claim: the bank struck out of a bank session's token | As a forged claim: the empty claim shows no bank row; 401, logged, ended. |
| A moved membership (removed in bank A, added in bank B) | The session stays bound to A: A has no active membership, so 401. A token claiming B is a forged claim. A new session in B needs a new sign-in. |
| A removed membership, a deactivated person | 401 on the next request, as before: the grants read finds no membership, or the person's status refuses. |
| A revoked or expired session | 401 on the next request, as before: the row is read on every request. A mismatched claim on a revoked session is still logged. |
| A platform (console) session | Its empty claim resolves it with no bank active, platform grants only. A bank's claim on it is refused, logged in the platform zone and ends it. |
| Support access | Its claim is the granted bank; the grant is still read under the bank's own policies on every request, and past the window or revoked it answers 401 `support_access_ended`. Another bank's claim is refused, logged and ends it. |
| An agent key or personal access token | Never an access token: `cw_` credentials go through `ApiKeyAuth` and `resolve_api_key`, unchanged, which still opens the identity lookup on `api_key` and checks revocation on every request. A key presented as a session bearer, or a session token as a key, is 401. |

## Sessions issued before the change

Access tokens of the old format are **refused and re-issued**, never accepted: a v1 token
answers 401, the client's one-flight refresh on a 401 (ADR 0006) presents the refresh cookie,
whose format is unchanged, and the refresh issues a v2 token whose claim is read from the
stored session. Nobody signs in again unless their session had already ended; no old token is
ever accepted, so nothing is widened, and an access token lives ten minutes at most, so none
outlives the deploy by longer than that anyway.

## Consequences

Easier: two queries fewer on every session request, and every query of a request runs scoped
from the first; the identity lookup is off a request's hot path. Harder: the token grew by a
tenant id (32 characters), and the refusal path now writes (a security-log row, a revocation
and its audit row) in a request that answers 401, which the request's transaction commits
because an authentication refusal is a response, not an exception. The refusal records no
address: the resolver is not handed the request, and a key holder can set one at will anyway.
To remember: a session must never change bank. If a tenant switcher ever arrives, it mints a
new session in the other bank rather than moving the row.
