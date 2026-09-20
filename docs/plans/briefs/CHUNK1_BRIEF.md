# Chunk 1 brief: identity and tenant admin basics (shared by every agent)

Repo `C:\Users\Alex\projects\grc`, branch `main`, HEAD da0a5e7 (Phase 0 + newest packages).
Read first, in this order: `CLAUDE.md`, `docs/CONVENTIONS.md`, `docs/PLAYBOOK.md` Sections 3,
4.2, 4.3, 4.4, 5, 8, `PRD.md` sections ID, TEN, ADM, 4, 5, 6, `docs/inputs/INPUT_DELTAS.md`
(all, especially section 2), `docs/inputs/schema.sql` section 1 (lines 62-140) and the
identity tables around lines 985-1115 (`invitation`, `user_session`, `login_event`,
`support_access`, `team`), `docs/inputs/data-model.md` sections 1, 4, 8.1 item 4 and 9,
`backend/apps/identity/app.md`, `backend/apps/tenants/app.md`, `backend/apps/shared/app.md`,
`design/README.md` (screens the prototype lacks), `design/system/pills-and-labels.md`,
`docs/adr/0002`, `0003`, `0006`, `0022`, `0025`. Phase 0 code is the floor: read
`backend/apps/shared/{authentication,permissions,tenancy,audit,vocabulary,models}.py`,
`backend/config/settings.py`, `frontend/src/shared/utils/api-client.ts`,
`frontend/src/shared/navigation/registry.ts`, `frontend/tests/e2e/support/*`.

Scope (Build_Plan chunk 1): ID-01 to ID-06, ID-09 to ID-11, TEN-01, ADM-01 (people only),
ADM-03, journeys J-1 and J-8. Scenarios: identity ID-S1 to S15, S18 to S22, S25, S26;
tenants TEN-S1, TEN-S7, ADM-S1, ADM-S2, ADM-S3. Out of scope, stubs stay skipped: ID-S16,
S17, S23, S24 (R2/R3), TEN-S2 to S6.

## Order of work: tests first (Alex, 2026-09-19: "build tests first, then write code")
For each scenario: un-skip its stub in `tests_scenarios.py` (or `test.fixme` in the journey
spec), write the test so it fails for the right reason, then implement until green. Never
delete or weaken a scenario. Commit nothing; the orchestrator commits.

## Invariants (never weaken; stop and report instead)
No passwords anywhere. The emailed code is a one-time enrolment bootstrap, never a fallback:
a code request for an address whose account holds a passkey answers exactly like any other
request, in the same time, and sends nothing. Enrolment session reaches only the passkey
registration ceremony and `GET /me`. Step-up is a fresh passkey assertion inside
`STEP_UP_WINDOW_S` (default 300) on: re-issue enrolment, role and permission changes,
security policy changes, API key creation (and later: sign-off, approvals, footprint,
exports). Four eyes where it applies. Permissions are constants in
`apps/shared/permissions.py` (PRD section 6, already there); roles are rows composed of
permissions; nothing compares a role name. A tenant always keeps one member holding
`members.manage`. Every write goes through `record()`. Tenant tables under forced RLS
(`migration_helpers.rls_operations`). Every threshold is a setting with an env override.
Tokens, codes and keys are stored hashed (SHA-256 for random tokens; the 6-digit code with
a per-row salt), compared in constant time (`secrets.compare_digest`). Randomness from
`secrets`. Personal data in logs: name and id only. Security log rows are append-only.

## Data model (Django models; snake_case; from schema v0.3 as corrected by INPUT_DELTAS)
`apps/library`: `Language` (code PK-like unique `key`, name, `text_search_config`, active;
seed en, sv, da, nb, fi in `seed_reference` with a comment per seed). Nothing else in
library this chunk.
`apps/shared`: `Tenant` exists (id, name, slug, timezone, created). Add `settings`-free
explicit columns instead of a settings blob: `default_language` FK Language, and a
`content_languages` M2M (ordered via through model `sort_order`). Keep `status` as a kind
(`active|deactivated`).
`apps/identity`:
- `User` (table `app_user`): id uuid, email citext unique, name, locale FK Language,
  status kind (`invited|active|deactivated`), created_at, last_seen_at, deactivated_at.
  Not Django's auth User; no password field anywhere (the no-passwords guard stays).
- `PlatformRole(Vocabulary)` rows `platform_admin`, `library_editor` with `permissions`
  (ArrayField of permission constants). `PlatformRoleAssignment` (user, role).
- `TenantRole(Vocabulary, TenantModel)`: system rows per tenant seeded from PRD section 6
  (`admin`, `compliance_officer`, `owner`, `approver`, `contributor`, `reader`, `auditor`)
  with `permissions` ArrayField; `is_system` true; tenants add their own (ID-S18).
- `Membership(TenantModel)`: user, roles M2M TenantRole, title, notification_prefs
  (JSONField with a named schema comment `MembershipNotificationPrefs`), last_visit_at,
  invited_by, deactivated_at, out_of_office_until, delegate (nullable; R2 uses them).
  Unique (tenant, user).
- `Invitation(TenantModel)`: email citext, roles M2M TenantRole, title, token_hash unique,
  invited_by, created_at, expires_at (INVITATION_TTL_H=72), accepted_at, accepted_user,
  revoked_at, `kind` (`invite|reenrolment`).
- `OtpCode`: user (nullable) + email citext, code_hash, salt, attempts, max_attempts
  snapshot, expires_at (OTP_TTL_MIN=10), consumed_at, created_at, ip.
- `AuthChallenge`: id, kind (`registration|authentication|step_up`), challenge bytes
  (base64url text), user nullable, session nullable, expires_at (CHALLENGE_TTL_S=120),
  consumed_at.
- `WebAuthnCredential`: user, credential_id (base64url, unique), public_key (base64url
  COSE), sign_count, transports (ArrayField text), aaguid, backup_eligible, backed_up,
  device_type kind (`single_device|multi_device`), nickname, created_at, last_used_at,
  retired_at.
- `UserSession`: user, tenant nullable, kind (`enrolment|full`), refresh_token_hash
  unique, previous_refresh_hash nullable + rotated_at (replay grace
  REFRESH_REPLAY_GRACE_S=30), created_at, last_seen_at, expires_at (absolute
  SESSION_ABSOLUTE_H=12), idle limit SESSION_IDLE_MIN=30 enforced on refresh, revoked_at,
  revoked_reason, ip, user_agent.
- `StepUpAssertion`: session, credential, created_at, challenge. `record()` gains a
  `step_up_assertion_id` on `AuditEvent` (INPUT_DELTAS section 6): add the column and let
  `@requires_step_up` put the fresh assertion on `request.step_up_assertion` so logic
  passes it to `record()`.
- `ApiKey`: tenant nullable (null = platform key for agents), agent nullable (FK added in
  chunk 5; leave a uuid nullable `agent_id` column now), name, key_prefix (8 chars shown),
  key_hash, scopes ArrayField from the scope constants in `permissions.py` (`agent-runs:write`,
  `sources:write`, `changes:write`, `proposals:write`, `search:read`, `library:read`,
  `upcoming:read`, `tenant:read`; none allows a library edit), created_by, created_at,
  expires_at, revoked_at, last_used_at.
- `LoginEvent(AppendOnlyModel)` (table `login_event`): occurred_at, tenant nullable, user
  nullable, api_key nullable, email, method kind (`email_code|passkey|api_key`; later
  `oidc|saml`), event kind (`code_sent|code_refused_enrolled|code_failed|code_locked|
  enrolled|signin|signin_failed|step_up|step_up_failed|refresh_replay|session_revoked|
  reenrolment_issued|key_used|key_revoked`), success, failure_reason, ip, user_agent.
  Mixed-table RLS policy (tenant null rows to platform staff, tenant rows to their tenant).
`apps/tenants`: `SupportAccess(TenantModel)` (platform_user, reason, ticket_ref,
access_level kind, approved_by, started_at, ended_at) used by ID-S13. `SecurityPolicy`
is R2: do not create it.

## API contract (Ninja, `/api/v1`, camelCase, RFC 9457 errors; both agents build to this)
Auth, ungated by design (`bootstrap` / `public-token`), rate limited (settings; off in
tests except the test that proves it):
- `POST /auth/invitations/open` `{token}` -> 202 `{}` (the token in the body since
  security review F29, the link is `/invite#<token>`); valid token: sends a code to the
  invited address and answers 202; expired or consumed: 410 `invitation_expired`.
- `POST /auth/code/request` `{email}` -> 202 `{}` always (neutral); sends a code only for
  an address with an open invitation or re-enrolment and no live passkey; otherwise logs
  `code_refused_enrolled` (if enrolled) and sends nothing. Constant response time
  (the logic does the same hashing work on every path).
- `POST /auth/code/verify` `{email, code}` -> 200 `{accessToken, sessionKind: "enrolment",
  expiresIn}` + refresh cookie (HttpOnly, Secure outside DEBUG, SameSite=Strict,
  Path=/api/v1/auth); 400 `invalid_code`; 400 `code_locked` after OTP_MAX_ATTEMPTS=5.
- `POST /auth/passkeys/register/options` (EnrolmentAuth or SessionAuth) -> 200 the
  py_webauthn `options_to_json` object; user verification required, resident key
  required, exclude existing credentials.
- `POST /auth/passkeys/register/verify` `{credential, nickname}` -> 201
  `{passkey: {...}, accessToken?, sessionKind: "full"}`: from an enrolment session the
  first passkey activates the user (status active), revokes the enrolment session, and
  issues a full session (accessToken + refresh cookie); from a full session it adds a
  passkey. Logs `enrolled`.
- `POST /auth/passkeys/authenticate/options` `{}` -> 200 options (discoverable: empty
  allowCredentials) ; `POST /auth/passkeys/authenticate/verify` `{credential}` -> 200
  `{accessToken, sessionKind: "full", expiresIn}` + refresh cookie; updates sign_count,
  last_used; 401 `signin_failed` (logged). The user handle in the credential is the user
  id (bytes of the uuid).
- `POST /auth/step-up/options` (SessionAuth) -> 200 options bound to the session's user
  (allowCredentials = that user's credentials); `POST /auth/step-up/verify` `{credential}`
  -> 200 `{assertionId, expiresAt}`; stores StepUpAssertion for the session.
  `@requires_step_up` accepts a request when the session has an assertion younger than
  STEP_UP_WINDOW_S; otherwise 403 `step_up_required`.
- `POST /auth/refresh` (cookie) -> 200 `{accessToken, expiresIn}` rotating the refresh
  token; replay inside grace: same answer without a third token; replay after grace: 401
  and the session is revoked (`refresh_replay` logged); idle/absolute limits -> 401.
- `POST /auth/sign-out` -> 204, revokes session, clears cookie.
Access token: opaque `sid.<random>` signed with HMAC(SECRET_KEY) or simply a random token
hashed in a small `AccessToken` table with ACCESS_TOKEN_TTL_S=600; choose the HMAC form
(no table). `SessionAuth` resolves it to `request.auth = Principal(kind="user",
subject_id, tenant_id, permissions, scopes=[], session_id)` and calls
`tenancy.activate(tenant_id)`. `EnrolmentAuth` accepts only enrolment sessions;
`ApiKeyAuth` reads `Authorization: Bearer cw_<prefix>_<secret>`, hashes, checks
revoked/expired, updates last_used (throttled to once a minute), logs `key_used`, sets
scopes, activates the key's tenant if any.
Me (SessionAuth; `GET /me` also EnrolmentAuth):
- `GET /me` -> `{user{id,email,name,locale}, tenant{id,name,slug,timezone}|null,
  roles[{key,kind,label}], permissions[], platformRoles[{key,kind,label}],
  enrolmentPending, passkeyCount, stepUpValidUntil|null}`.
- `PATCH /me` `{name?, locale?}` (If-Match not needed: not a versioned record).
- `GET /me/passkeys`, `PATCH /me/passkeys/{id}` `{nickname}`, `DELETE /me/passkeys/{id}`
  (409 `last_passkey` when it is the last live one).
- `GET /me/sessions` `[{id, current, createdAt, lastSeenAt, ip, userAgent}]`,
  `DELETE /me/sessions/{id}`.
Tenant admin (SessionAuth + `@requires_permission`):
- `GET /tenant` (any member) `{id,name,slug,timezone,defaultLanguage{key,kind,label},
  contentLanguages[...], onboarding{stepsDone, steps[{key, done}]}}`; `PATCH /tenant`
  (`security.manage` for now; `tenants.manage` on the console later) name, timezone,
  defaultLanguage key, contentLanguages keys. Onboarding steps computed: profile set,
  first member invited, footprint set (false until chunk 2), first passkey enrolled by an
  admin.
- `GET /tenant/members` (`members.manage`; a member without it gets 403) ->
  `[{userId, email, name, status, roles[{key,kind,label}], title, lastSeenAt, passkeyCount,
  activeSessions}]`; `POST /tenant/members` `{email, roleKeys[], title?}` -> 201 creates
  the invitation (kind invite) and emails the link; `PATCH /tenant/members/{userId}`
  `{roleKeys?, title?}` (step-up when roleKeys changes; 409 `last_admin`);
  `DELETE /tenant/members/{userId}` deactivates (409 `last_admin`; revokes sessions).
- `GET /tenant/invitations`, `POST /tenant/invitations/{id}/resend`,
  `DELETE /tenant/invitations/{id}` (revoke).
- `POST /tenant/members/{userId}/reissue-enrolment` (`members.manage` + step-up) ->
  202: revokes every session, retires every passkey, opens a re-enrolment invitation for
  the address, emails the user and every other admin, audit event with the assertion.
- `GET /tenant/members/{userId}/sessions`, `DELETE /tenant/members/{userId}/sessions`
  (revoke all; `members.manage`).
- `GET /tenant/roles` (any member: pickers need labels), `POST /tenant/roles`
  `{key, labels{en,sv}, usageNote, permissions[]}` (`roles.manage` + step-up),
  `PATCH /tenant/roles/{key}` (labels, usage note, permissions for non-system rows; labels
  only for system rows; step-up when permissions change), `POST /tenant/roles/{key}/retire`.
- `GET /reference/permissions` (any session) -> `[{key, group, description}]` from the
  constants, for the role editor.
- `GET /tenant/api-keys` (`integrations.manage`), `POST /tenant/api-keys`
  `{name, scopes[], expiresAt?}` (+ step-up) -> 201 `{id, name, keyPrefix, scopes,
  createdAt, plainKey}` (the only place plainKey appears), `DELETE /tenant/api-keys/{id}`.
- `GET /tenant/security-log` (`security.manage`) paginated LoginEvent rows.
Console (platform staff; `@requires_permission` on platform permissions):
- `POST /console/tenants/{tenantId}/members/{userId}/reissue-enrolment`
  (`support_access.grant` + step-up) `{reason, ticketRef, outOfBandCheck}` -> 202; writes a
  SupportAccess row and the audit event (ID-S13).
- `manage.py bootstrap_platform --admin-email` creates the platform admin user with the
  `platform_admin` role and an invitation (kind invite, tenant null: platform invitations
  need `tenant` nullable on Invitation; make it nullable with the mixed RLS policy).
Structured 403: `{title,status,detail,code:"permission_denied",requiredPermission}`;
enrolment session on any other route: 403 `enrolment_only`.
Pagination on lists: `limit` default 20, max 100, `offset`; response `{items, total}`.

## E2E seed (`apps/shared/e2e_seed.py`, extend; the seed-integrity guard extends with it)
Tenant A "Example Bank AB" (slug example-bank) with one login per system role, e-mails
`<role>@example-bank.test`, names from the prototype's USERS list where they exist (read
`design/prototype/index.html`, search `USERS`), each with ONE fixed passkey whose COSE
public key is in the seed and whose private key lives in
`frontend/tests/e2e/support/passkeys.ts` (generate deterministic P-256 key pairs once with
a small script, commit both halves, allowlist the private keys in `.gitleaks.toml` by
exact literal with the reason "E2E virtual authenticator test keys, playbook 8.3").
Plus `anna@example-bank.test` invited (roles compliance_officer, reader) with no passkey:
the one user still awaiting enrolment; the E2E flag (`E2E_MODE`) makes her invitation
token `e2e-invite-anna` (hashed in the row) and every code `123456`. Tenant B
"Second Bank A/S" with `admin@second-bank.test` (admin, passkey). Platform:
`editor@bleqq.test` (library_editor) and `platform@bleqq.test` (platform_admin), passkeys.
Seed is idempotent and deterministic (fixed uuids).

## Frontend (screens per design/README: design a card first, commit the card, then build)
Cards in `design/screens/`: `auth-invitation.html`, `auth-code.html`, `auth-enrol.html`
(with the second-passkey prompt), `auth-sign-in.html`, `auth-step-up.html`,
`auth-recovery.html` ("ask your admin"), `me-passkeys.html`, `me-sessions.html`,
`admin-members.html` (members, invitations, re-enrolment, sessions), `admin-roles.html`,
`admin-api-keys.html`, `admin-security-log.html`, `admin-organisation.html` (TEN-01).
Cut from the prototype's language (its CSS variables and components); phone first; two
buttons share one row, primary right.
Routes: `/sign-in`, `/invite` (token in the fragment, F29), `/enrol` (code, then passkey, then second-passkey
prompt), `/me/passkeys`, `/me/sessions`, `/admin/organisation`, `/admin/members`,
`/admin/roles`, `/admin/api-keys`, `/admin/security-log`, `/restricted`. Navigation
registry entries with `anyOfPermissions`. `api-client.ts`: on 403 `step_up_required` run
the step-up ceremony (a modal) and retry once; on 401 refresh once. WebAuthn in the
browser through `navigator.credentials` with base64url helpers (no library; keep it in
`src/shared/webauthn.ts` with unit tests). Empty, loading, error and denied states on
every screen. Every string in the `messages/<namespace>/{en,sv}.json` catalogs. Labels for roles come from
the rows (`{key,kind,label}`), never from code.
E2E journeys (`identity.journey.spec.ts`, `tenants.journey.spec.ts`): un-fixme ID-S25
(J-1, @smoke: invite link -> code -> enrol passkey via the virtual authenticator -> skip
second passkey -> sign out -> passkey sign-in -> code request shows the neutral message
and the mailer sent nothing, checked through a test-only endpoint
`GET /api/v1/e2e/mail-outbox` that exists only under E2E_MODE and is ungated by design
`bootstrap` with that reason), ID-S4, S5, S6, S8, S10, S11, S12, S14 (use the re-issue
enrolment action as the sensitive action until sign-off exists), S18, S20, S26; TEN-S7
(J-8, @smoke: tenant B's admin opens tenant A's member URL and gets the 404 screen, sees
only its own members), TEN-S1, ADM-S1, S2, S3. `support/passkeys.ts` uses
`browserContext.credentials` (Playwright 1.63 typings) to seed the fixed keys.

## Gates before you report (all must be green in your area)
Backend: the whole Appendix D list from `CLAUDE.md`, with `generate-types.sh` run last
(commit nothing). Frontend: lint, typecheck, test:coverage, check:messages,
check:copy-drift, build, and `npm run test:e2e` against the real backend (the backend
agent's work must be on disk; coordinate through the orchestrator if it is not yet).
Report: files, scenarios un-skipped, gate numbers, every deviation from this brief and why,
and anything you need from the other agent.
