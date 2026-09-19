# Security review: chunk 1, identity and access (2026-09-19)

## Question

Does the passkey-only identity layer of chunk 1 (invitation, emailed code,
passkey enrolment and sign-in, sessions, step-up, members, roles, API keys,
security log) hold the product invariants of PRD ID-01 to ID-11 and playbook
4.2, 4.3 and 11, and does it meet the OWASP ASVS requirements for
authentication, session management, authorization, cryptography, logging and
data protection, plus the WebAuthn server-side verification steps?

## Standard

OWASP ASVS **5.0.0**, the latest stable release (30 May 2025), read from
owasp.org/ASVS and the `5.0/en` chapter files at tag `v5.0.0` on GitHub on
2026-09-19 (`docs/plans/Verification_Log.md`). The brief named the 4.0 chapter
numbers; the 5.0 chapters checked against are:

| 5.0 chapter | 4.0 name in the brief |
|---|---|
| V6 Authentication | V2 |
| V7 Session Management | V3 |
| V8 Authorization | V4 |
| V11 Cryptography | V6 |
| V16 Security Logging and Error Handling | V7 |
| V14 Data Protection | V8 |
| V4 API and Web Service, V13 Configuration, V3 Web Frontend Security | (cookies, CORS, CSP, headers) |

WebAuthn Level 3 server-side steps checked: challenge single use and bound to
the ceremony, origin and RP ID, user verification flag, sign counter
regression, credential id uniqueness (§7.1 step 22), user handle to account
binding on discoverable credentials (§7.2 step 6), exclude list on
registration, attestation handling.

## Method

1. Read `CLAUDE.md`, `docs/CONVENTIONS.md`, playbook 4.2, 4.3, 11, 14, PRD
   section ID and AC-ID1 to AC-ID3, ADR 0002, 0003, 0006.
2. Read every file under `backend/apps/identity/` and `backend/apps/tenants/`,
   `apps/shared/{authentication,permissions,tenancy,audit,middleware,errors,api,
   migration_helpers,sentry_scrub}.py`, `config/{settings,api,test_settings}.py`,
   the identity migration, the E2E seed's guard, and (read only) the frontend
   `shared/webauthn.ts`, `shared/utils/api-client.ts`, `features/identity/**`.
3. Checked py_webauthn 3.0.0's installed source for the sign-count and user
   handle behaviour rather than the README.
4. Traced the E2E-only surfaces (`/api/v1/e2e/mail-outbox`, the fixed code, the
   fixed invitation token) from the route to the settings guard and the
   production-guard test.
5. For each medium-or-above backend finding: wrote a regression test whose
   docstring names the finding, then the fix, and re-ran ruff, mypy,
   `scripts/compliance_check.py --all` and the whole backend suite until green
   (352 tests, 144 skipped as pending R2/R3 scenarios, 0 failures).

No request or response shape changed; no migration was edited or added.

## Findings

Severity: critical / high / medium / low / info. Status: fixed / open /
accepted (with the reason).

| # | Sev. | Where | Finding | Status |
|---|---|---|---|---|
| F1 | high | `apps/identity/security_log.py:20` | `client_ip()` took the **leftmost** `X-Forwarded-For` value whenever the header existed. The header is caller-supplied text, so any client could pick its own "address": the per-IP limits on code request, code verify, sign-in and refresh (`AUTH_RATE_PER_IP_PER_MINUTE`, `ENROLMENT_CODE_RATE_PER_IP_PER_HOUR`) were resettable per request, and the security log (ID-11), session rows and OTP rows recorded forged addresses. (ASVS V6.1, V16.) | **Fixed.** New setting `TRUSTED_PROXY_HOPS` (default 0: the header is ignored and the socket address is the client). With N hops, the Nth value from the right is the client, never the leftmost. `.env.example`, `RAILWAY_DEPLOY.md` (`=1` on Railway) and the Verification_Log updated. Tests: `tests_policies.ClientAddress`. |
| F2 | medium | `apps/identity/code_logic.py:126-145` | The attempt counter was read, incremented in memory and saved: N parallel requests each saw `attempts == 0`, so the five-attempt lock on the six-digit code could be exceeded by racing; the single-use consumption was a plain save as well, so two right answers in flight yielded two enrolment sessions. (ASVS V6.3.) | **Fixed.** One conditional `UPDATE ... WHERE attempts < max_attempts` claims the attempt (Postgres row lock serialises the racers), and one conditional `UPDATE ... WHERE consumed_at IS NULL` consumes. Tests: `tests_policies.CodeAttemptsUnderConcurrency`. |
| F3 | medium | `apps/identity/passkey_logic.py:117-131` | `_consume_challenge` did `.first()` then `save(consumed_at)`: the same assertion presented twice at once passed twice, so a challenge was not strictly single use. (WebAuthn §7.2 step 11 and §13.4.3.) | **Fixed.** The claim is one conditional `UPDATE`; the read is isolated in `_open_challenge` so the race is testable. Tests: `tests_policies.ChallengeSingleUse`. |
| F4 | medium | `apps/identity/passkey_logic.py:284-296` | Discoverable sign-in found the credential by id and verified the signature, but never checked `response.userHandle`. WebAuthn §7.2 step 6 requires that, when no user was identified before the ceremony, the user handle is present and names the account that owns the credential. No exploit was found (the signature binds the credential), but the spec step is mandatory and the frontend already sends the handle. | **Fixed.** Sign-in requires a handle equal to the credential owner's id bytes; step-up (account known, allow list set) checks it when present. Failures log `user_handle_mismatch`. Tests: `tests_policies.UserHandleBinding`. |
| F5 | medium | `apps/identity/passkey_logic.py:248`, `invitation_logic.py:205` | `POST /auth/passkeys/authenticate/options` was unauthenticated, unlimited, and wrote an `auth_challenge` row plus an audit and outbox row per call; `POST /auth/invitations/{token}/open` limited per address only after a token matched, so unknown tokens were unbounded. Write amplification and table fill from one address. (ASVS V6.3.2 style throttling, playbook 11.2.) | **Fixed.** Both take the `auth:ip` limit (`AUTH_RATE_PER_IP_PER_MINUTE`) before any work. Tests: `tests_policies.UnauthenticatedCeremonySteps`. |
| F6 | medium | `apps/shared/middleware.py:83`, `apps/shared/sentry_scrub.py:59` | The over-budget warning logged `request.path`, and the Sentry scrubber left `request.url`: for `/auth/invitations/{token}/open` that is the single-use, 72-hour invitation token, which can be opened repeatedly until accepted. `max_request_body_size='never'` does not cover the URL. (ASVS V16.2, V7 tokens in URLs.) | **Fixed.** The warning logs the matched route pattern (`api/v1/auth/invitations/<token>/open`), or the first two path segments on a 404; `scrub_url` redacts the segment after `/auth/invitations/` in `request.url`. Tests: `tests_middleware.ServerTiming.test_over_budget_never_logs_a_path_parameter`, `SentryScrubbers.test_the_invitation_token_never_leaves_in_the_request_url`. |
| F7 | medium | `apps/identity/session_logic.py:174-190`, `members_logic.py:188`, `invitation_logic.py:229` | A full session in a tenant resolved even with no active membership there (permissions empty, but the "any member" routes `GET /tenant`, `GET /tenant/roles`, `GET /reference/permissions` answered). Reachable: deactivation revoked sessions but left the address's open invitation, and a re-invite after deactivation handed back the dead membership, so the person enrolled into a session with no membership. (ASVS V8.1.) | **Fixed.** `build_principal` returns nothing when a full tenant session has no active membership row (folded into the query it already ran, so the members-list query pin holds); deactivation closes the address's open invitations in that tenant (audited in `after.invitationsClosed`); accepting an invitation as a deactivated member reactivates the membership with the invitation's roles. Tests: `tests_policies.FullSessionsStandOnMemberships`. |
| F8 | medium | `apps/identity/passkey_logic.py:222` | On the first passkey, enrolment accepted `find_open_for_email()`, the newest open invitation for the address in any tenant, not the invitation the enrolment session came from. If a second tenant invited the address between code and passkey, the membership was created in the wrong tenant (and under real RLS the insert fails with the first tenant activated). Enrolment session confinement, ID-02. | **Fixed.** `find_open_for_tenant(email, session.tenant_id)` binds acceptance to the session's tenant. Test: `tests_policies.EnrolmentBoundToItsInvitation`. |
| F9 | medium | `apps/identity/api.py:126-158`, `234-238` | Adding a passkey (and removing a non-last one) from a full session needs only the access token: a token stolen within its 10-minute life can plant an attacker passkey and keep access after the session ends. ASVS V6 expects re-authentication for changes to authentication factors. The playbook 4.2 step-up list does not include it, and the enrolment flow deliberately prompts for a second passkey right after the first. | **Fixed, narrowed** (2026-09-19): `POST /auth/passkeys/register/verify` from a full session and `DELETE /me/passkeys/{id}` are allowed only while the session is younger than `STEP_UP_FRESHNESS_MINUTES` (its `created_at`; a refresh does not move it) or with a fresh assertion (`enforce_recent_sign_in_or_step_up`); the enrolment session is unchanged. So the second-passkey prompt right after enrolling or signing in needs no extra ceremony, and a token stolen later in a session cannot plant a passkey. A sign-in and an enrolment no longer mint a `StepUpAssertion` (the first fix did, which let every `@requires_step_up` action through for the window after sign-in): that contradicted ID-S14, and high-impact actions (re-issue, role and permission changes, API keys, footprint approval, later sign-off, exports, approvals) should carry an explicit act of intent. `GET /me` `stepUpValidUntil` reflects real assertions only. Tests: `tests_scenarios.test_id_s10`, `tests_policies.StepUpOnPasskeyChanges`. |
| F10 | low | `apps/identity/session_logic.py:244` | A refresh value older than `previous_refresh_hash` (two rotations back) is refused but does not revoke the session; replay detection covers only the immediately previous token. | **Accepted.** Such a value is indistinguishable from a random one without keeping the whole hash family; the absolute limit bounds exposure and the immediate-previous case (the realistic theft) revokes. |
| F11 | low | `config/settings.py:227` | `SECURE_PROXY_SSL_HEADER` is set unconditionally, so a direct client could claim HTTPS. | **Accepted.** Railway's edge terminates TLS and owns the header; nothing security-relevant keys on `is_secure()` besides the redirect, and locally the redirect is off. Revisit if the app is ever exposed without a proxy. |
| F12 | medium | `apps/identity/code_logic.py:56-76` | `request_code` is neutral in its answer and does a decoy hash, but on the sending path it also writes two rows and calls the mailer synchronously (an SMTP round trip when deployed). Response time therefore distinguishes "open invitation and no passkey" from every other address. | **Fixed** (2026-09-19): every identity mail is composed in the request and delivered by the Celery task `apps.identity.tasks.deliver_mail`, enqueued with `transaction.on_commit` (eager and inline in tests), so the request never waits on a relay; the mock mailer's outbox moved to the cache (locmem in tests, Redis in E2E) so `GET /api/v1/e2e/mail-outbox` reads what the worker sent. Tests: `tests_policies.MailLeavesThroughTheWorker`. |
| F13 | low | `apps/identity/code_logic.py:139` | `code_locked` is answered only for an address holding a live code, so after five wrong guesses a caller learns that an address has a code in flight. | **Accepted.** It needs an invitee's address and an open code; the lock is the defence and the guess space (10^6, 5 tries) is unchanged. |
| F14 | low | `config/settings.py:259` | CORS allows a `x-tenant-id` request header that nothing reads. | **Accepted / note.** Harmless today; drop it or design it when a tenant switcher arrives. |
| F15 | low | `apps/identity/passkey_logic.py:206` | A credential id already registered to another account raised `IntegrityError` (500) and broke the request transaction. (WebAuthn §7.1 step 22 asks for a clean refusal.) | **Fixed.** Insert under a savepoint; duplicate answers 400 `registration_failed`. Test: `tests_policies.CredentialIdUniqueness`. |
| F16 | low | `apps/identity/invitation_logic.py:279-280` | Re-enrolment issued from tenant A retires the person's passkeys globally (no tenant on `webauthn_credential`) while, under RLS, it revokes only the sessions visible in A. A person in two tenants loses B access until re-enrolled, and keeps B sessions until they expire. | **Accepted for R1.** No tenant switcher, so no multi-tenant persons; revisit with TEN-06 support access and a tenant switcher. |
| F17 | info | `apps/shared/permissions.py:419-435` | Step-up freshness is **per window** (`STEP_UP_FRESHNESS_MINUTES` = 5), bound to the session (`step_up_assertion.session_id`, challenge bound to user and session), not consumed per action. | **Accepted, safe.** Any number of sensitive actions inside five minutes ride one assertion; the assertion id is stored on every such audit row (AC-ID3). The window rides on an in-memory 10-minute access token and a rotating, path-scoped cookie, so the exposure is a hijacked token for at most the window. Per-action consumption would double the passkey prompts in the sign-off flow for no gain the audit trail does not already give. |
| F18 | info | `apps/shared/routes.py:20`, `logic.py:16`, `config/settings.py:458`, `tokens.py:55`, `e2e_seed.py:79` | E2E-only surfaces when deployed: `/api/v1/e2e/mail-outbox` answers 404 unless `E2E_MODE and MAIL_PROVIDER == "mock"`; `E2E_MODE` refuses boot on every deployed environment (rule 4, proven for `prod` and the deployed `test` by `tests_production_guard.py`); `tokens.new_code` refuses the fixed code again when deployed (`tests_policies`); the fixed invitation token exists only when `seed_e2e` runs, which `refuse_when_deployed()` blocks. | **Closed.** Unreachable when deployed on three independent legs. |
| F19 | info | `apps/shared/tenancy.py:80`, `migration_helpers.py:46`, `tests_rls.py:33` | The identity-lookup clause is on four tables (invitation, membership, user_session, api_key), pinned by the RLS guard; the flag is transaction-local, switched on only inside `identity_lookup()` blocks that each run one `.first()`/`values_list` and reset in `finally`. Every lookup keys on a secret (token hash, session pk from the cookie, key prefix) or the already-authenticated user (memberships), none on caller-chosen ids. | **Closed.** Narrow enough; no path was found that returns rows of another tenant to a caller. The one wider read is `choose_tenant` (all memberships of the signed-in user, tenant ids only). |
| F20 | info | `apps/shared/permissions.py:211-230` | `ALL_SCOPES` holds no library write; `@requires_scope` refuses unknown constants at import; agent routes land in later chunks. | **Closed** (AC-PRO1, ID-S21). |
| F21 | info | `members_logic.membership_of`, `tenant_invitation`, `revoke_api_key`, `revoke_own_session`, `_own_passkey` | Every `/tenant/...{id}` lookup filters by the session's tenant and every `/me/...{id}` by the caller's user id; a foreign record is 404 and a missing permission 403, consistently, so ids do not enumerate across tenants. | **Closed** (AC-NFR1 for chunk 1 routes). |
| F22 | info | `session_logic.set_refresh_cookie`, `config/settings.py:224-261` | Refresh cookie: `HttpOnly`, `Secure` (off only under DEBUG, which is refused when deployed), `SameSite=Strict`, `Path=/api/v1/auth`, max-age = absolute limit; CORS allowlist with credentials scoped to `/api/`; CSP `default-src 'none'; frame-ancestors 'none'`; HSTS one year with preload; `X-Frame-Options: DENY`; referrer policy same-origin. | **Closed.** |
| F23 | info | `apps/identity/schemas.py` | PATCH bodies are explicit fields; logic takes named arguments; role permissions are validated against `TENANT_PERMISSIONS` (a tenant role can never carry a platform permission), scopes against `ALL_SCOPES`, locales and languages against active rows. | **Closed** (no mass assignment). |
| F24 | info | `apps/identity/*`, `security_log.py` | No `logger` call in identity or tenants; the security log row holds email, IP and user agent by design (ID-11, playbook 4.7 "IP beyond the security log"); audit rows hold names and ids. Sentry: `send_default_pii=False`, body never, both scrubbers (F6 closed the URL gap). | **Closed.** |
| F25 | low | `apps/identity/invitation_logic.py:178,195` | `invitation.resent` / `invitation.revoked` audit rows use the email's local part as `subject_title`. | **Accepted.** The invitee has no name yet; the address is on the invitation row already; the local part alone is the least that still identifies the row in the log. |
| F26 | low | `apps/identity/passkey_logic.py:271-281` | Sign-counter regression (a cloned authenticator) is refused by py_webauthn (verified in the installed source) and logged `signin_failed`, but the credential is not marked and the person is not told. | **Accepted for R1**; recommend a `suspect` mark plus a notice in R2 with ID-07 credential policy. |
| F27 | info | `apps/identity/passkey_logic.py:164` | Attestation `none` is requested; py_webauthn verifies a statement when present; AAGUID, backup flags and device type are stored. Attested device-bound policy is ID-07 (R2). | **Closed for R1.** |
| F28 | low (frontend) | `frontend/src/shared/utils/api-client.ts`, `shared/webauthn.ts`, `features/identity/*` | Verified: the access token lives only in module memory; bootstrap paths never carry a bearer; one-flight refresh with a cold-load attempt; a 401 is retried once; step-up retried once; `assertionToJson` forwards `userHandle` (so F4 is compatible); errors branch on kind. Two notes for the frontend owner: (a) the invitation token is the web route `/invite/{token}`, so it lands in browser history and would leak in `Referer` to any third-party asset on that page: set `Referrer-Policy: no-referrer` on that page and `history.replaceState` to a token-free URL once `openInvitation` has answered; (b) `refreshSession` treats any failure, including a network error, as a signed-out state (a UX, not a security, matter). | **Reported, not edited** (another agent owns the frontend). |

## What changed

Backend, tests first, no contract or migration change:

- `backend/apps/identity/security_log.py`: `client_ip` trusts `X-Forwarded-For` only for `TRUSTED_PROXY_HOPS` hops, from the right.
- `backend/config/settings.py`: `TRUSTED_PROXY_HOPS` (env, default 0). `.env.example` and `docs/runbooks/RAILWAY_DEPLOY.md` list it.
- `backend/apps/identity/code_logic.py`: `_open_code`, `_claim_attempt`; attempts and consumption are conditional `UPDATE`s.
- `backend/apps/identity/passkey_logic.py`: `_open_challenge` and an atomic claim in `_consume_challenge`; `_user_handle_matches` (required at sign-in, checked when present at step-up); `authentication_options(request)` rate limited; the credential insert under a savepoint with a 400 on duplicates; enrolment accepts `find_open_for_tenant(email, session.tenant_id)`.
- `backend/apps/identity/api.py`: passes `request` to `authentication_options`.
- `backend/apps/identity/invitation_logic.py`: `find_open_for_tenant`; `open_invitation` rate limited per IP before the lookup; `accept_invitation` reactivates a deactivated membership with the invitation's roles.
- `backend/apps/identity/session_logic.py`: `build_principal` returns nothing for a full tenant session without an active membership.
- `backend/apps/identity/members_logic.py`: deactivation closes the address's open invitations in the tenant.
- `backend/apps/shared/middleware.py`: `loggable_route`; the over-budget warning logs `route`, never `path`.
- `backend/apps/shared/sentry_scrub.py`: `scrub_url` on `request.url`.
- Tests: `backend/apps/identity/tests_policies.py` (seven new classes, each docstring naming its finding), `backend/apps/shared/tests_middleware.py` (three tests).
- Docs: this file; `docs/plans/Verification_Log.md` (ASVS 5.0.0, py_webauthn sign count, Railway proxy, the last marked not verified); `docs/TODO_FOR_alex.md` (F1 proxy hops, F9, F12).

Gates after the changes: ruff clean, mypy clean (201 files), `compliance_check.py --all` 0 findings, backend suite 352 tests OK.

## Not changed on purpose

- `apps/shared/e2e_seed.py`, `e2e_logins.py`, `seed_reference.py`, `apps/taxonomy`, `apps/proposals`, `apps/library` and every frontend file: owned by other agents during this review.
- Existing migrations: no schema change was needed; every fix is logic.
- The playbook 4.2 step-up list (F9) and the mail delivery path (F12): product decisions, recorded for the owner.

## Re-run

Until findings converge, re-run this review after F9 and F12 are decided, after
chunk 11 (tenant credential and session policy) and before the independent
penetration test (playbook 18).

## Addendum, 2026-09-19: F29, the invitation token travels in request paths

**Severity:** medium. **Status:** open, fix scheduled as the first task after chunks 1 and 2
are committed. Nothing is deployed yet.

Found while building the code-only invitation step. The token sits in the path of
`POST /auth/invitations/{token}/open` and of the page URL `/invite/{token}`, so every server
that logs request lines writes it down: Django's request logger on any 4xx (seen in test
output as `Gone: /api/v1/auth/invitations/<token>/open`), `runserver`, gunicorn's access
log on every request including successful ones, the hosting edge, and the web server for the
page itself. F6 kept it out of our own middleware and Sentry but not out of these. A token
alone cannot enrol anyone, since the emailed code is also needed, but a secret in logs breaks
the logging rule regardless.

**Fix (planned):** move the token out of every path instead of redacting logs. The emailed
link becomes `/invite#<token>`: a URL fragment is never sent to any server, proxy or
`Referer` header. The page reads it and posts it in the request body to `/open`, as the new
`POST /auth/invitations/verify` already does. A test asserts no request line carries a token.

