# Security review: the session's bank in the access token (perf-tenant-in-token, 2026-09-28)

## Question

Does the diff of perf-tenant-in-token (ADR 0063) keep two zones and forced row-level
security, the per-request session, membership, permission, support-grant and step-up
decisions, and the identity lookup's reach, while it signs the session's bank into the
access token and resolves a request under it? Does a token whose claim is not its session's
bank get refused, logged and never run in the claimed bank?

## Standard

OWASP ASVS 5.0.0, chapters V7 (session management), V8 (authorization) and V16 (security
logging), read against CLAUDE.md section 5, playbook 4.2 and 14, ADR 0006, ADR 0042 and the
audit's rules for wave B (`docs/plans/r2-waves/PERF_AUDIT.md`).

## Method

1. Read `git diff origin/main...HEAD` line by line: `apps/identity/tokens.py`,
   `apps/identity/session_logic.py`, `apps/identity/models.py` and identity 0010,
   `apps/identity/schemas.py`, the guard change in `apps/shared/tests_tenancy.py`, the new
   `apps/shared/tests_tenant_in_token.py`, the pins, and the security-log catalog lines.
2. Traced every issuer of an access token (`create_session`, `create_support_session`, both
   branches of `refresh`) to confirm the claim is always the stored row's `tenant_id`, never
   a value from the request.
3. Traced the one statement `_read_session` issues under each zone a claim can name, against
   the policies of the tables it touches: `user_session` (mixed, with the identity-lookup
   read), `membership`, `membership_role` and `tenant_role` (tenant, forced), and the tables
   with no row-level security (`app_user`, `tenant`, `language`, `step_up_assertion`,
   `platform_role_assignment`, `platform_role`).
4. Removed, in scratch copies, first the claim comparison and then `_refuse_claim`, and ran
   the new tests red (named in the module's docstring).
5. Confirmed `apps/shared/tests_rls.py` is byte for byte unchanged and green, and that no
   migration touches a policy, the `cw_app` grants or the boot guard.

## What changed, security-relevant

- The access token is `v2` and signs `tenant_id` with the session id, kind and expiry. A `v1`
  token is refused by its format; the refresh cookie is unchanged, so the client's refresh
  on 401 re-issues a `v2` token from the stored row (ADR 0063, "Sessions issued before the
  change"). No old token is accepted, so nothing widens.
- The resolver activates the claimed bank (or asserts no bank) and reads the session, its
  person, its bank, the grants and the step-up in one statement. The identity-lookup flag is
  no longer switched on for a request's own credential.
- A claim that finds no row, or a row of another zone, answers 401; the refusal re-reads the
  row by id through the identity lookup, moves the transaction to the row's own zone, and on
  a mismatch writes `access_token_refused` / `tenant_claim_mismatch` to the security log and
  revokes the session (`session_revoked`, same reason, with its audit row).

## Findings

Severity: critical / high / medium / low / info. Status: fixed / open / accepted.

| # | Sev. | Where | Finding | Status |
|---|---|---|---|---|
| L1 | low | `session_logic.resolve_access_token` | The claimed bank is active for the one read that verifies it. A token only a key holder can make could therefore run that read in a bank not its own. What it reads there is bounded: the session row by its id (invisible in the wrong bank unless it is a console row), and the membership, role and step-up rows keyed on that row's own `tenant_id` and `user_id`, so a mismatched claim reads nothing of the claimed bank. The result is discarded, and the zone is moved to the row's own before anything else runs. | **Accepted**, pinned by `TenantInToken.assert_refused_and_logged` (the zone after every refusal). |
| L2 | low | `session_logic._refuse_claim` | The refusal's security-log row records no address or user agent: the resolver is called with the token alone (`Resolver = Callable[[str], ...]`), and threading the request through every auth class and the test stubs is wider than this package. The row names the person, the bank and the reason; a party able to forge the token can set any address anyway. | **Accepted**, ADR 0063 "Consequences". |
| I1 | info | `session_logic._refuse_claim` | The refusal writes (a security-log row, a revocation, an audit row) in a request that answers 401. Writes on an unauthenticated path are a flooding risk in general; here only a correctly signed token reaches them, so only a SECRET_KEY holder can trigger one. An authentication refusal is a response inside the view, so `ATOMIC_REQUESTS` commits it. | **Accepted, noted.** |
| I2 | info | `session_logic._session_reads` | The annotated queryset is built once per process (`functools.cache`) and each call filters a clone. A queryset holds no rows and no zone until it runs, and the base is never evaluated, so no row or tenant is shared across requests. | **Accepted, noted.** |
| I3 | info | `apps/shared/tests_scenarios.py` NFR-S10 | Before the change a console session never asserted its own zone and inherited whatever the connection's transaction had; in production each request's transaction starts in no bank, so this only showed in a test that left a bank active. The resolver now asserts no bank for a console session (the same rule `resolve_api_key` follows for a platform key, D-78), and the test counts audit rows from the editor's own zone. | **Fixed** (a narrowing). |

No critical, high or medium finding.

## Invariants checked

- **Two zones, forced RLS, `cw_app`:** no migration changes a policy, a grant or FORCE; the
  RLS guard (`tests_rls.py`) is unchanged and green; the boot guard is untouched.
- **Identity lookup reaches only what it needs:** the clause stays on the same five tables;
  its callers in the session module are narrowed from the module to `choose_tenant`,
  `_load_by_refresh` and `_refuse_claim` (`tests_tenancy.py`), and a test proves the request
  path issues no statement naming the flag.
- **Every decision on every request:** a revoked or expired session, a deactivated person, a
  removed or moved membership, an ended support grant, another bank's id and a revoked key
  are all still refused (`tests_tenant_in_token.py`, `tests_request_once.StillRefused`,
  `tests_support_session.py`). The step-up still reaches `@requires_step_up` from the same read.
- **Security log and audit:** the refusal writes through `log_event()` and `record()`, the
  only doors to those ledgers, in the session's own zone.
- **Nothing logs a token or tenant content:** the diff adds no logger call.

## Gates run

Backend: the whole suite in three foreground runs (`apps.shared` with `apps.identity`, then
the other fifteen apps in two halves; 4,164 tests, 0 failures), migration drift,
`migrate_from_zero`, ruff, mypy, `compliance_check.py --all`, `requirements_coverage.py`,
`api_docs_gate.py`, `contract_drift.py`. Frontend: lint, typecheck, the security-log
presentation test, `check:messages`, `check:copy-drift`. E2E: `@smoke` (15), the identity and
cold-start journeys (15) and the tenants journeys (11), all green.
