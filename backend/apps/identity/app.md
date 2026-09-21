# identity — Identity and access

> **App spec.** Source: `PRD.md` Module ID (ID-01–ID-13, AC-ID1–AC-ID3), journey J-1,
> `docs/inputs/INPUT_DELTAS.md` §2, playbook 4.2.
> The PRD is the source of truth; on any conflict the PRD wins. Update this
> file whenever the PRD version bumps or a feature lands.

## 1. Business / user context

A bank's compliance team must be able to say who signed off what, and prove
that nobody could have done it with a stolen password. So nobody has a
password. A person joins by invitation, proves the email once with a code,
enrols a passkey, and from then on the passkey is the only way in. The
emailed code stops working for that account the moment the first passkey is
stored, because otherwise email would be the real authenticator.

Sensitive actions (sign-off, approvals, footprint changes, exports, key
creation, role and security changes, re-enrolment) ask for a fresh passkey
assertion, and the audit event keeps a reference to it. Permissions are
constants in code; roles are rows the tenant composes from them, so nothing in
the product branches on a role name. Agents and integrations use scoped API
keys, and no scope reaches the library. PRD 0.4 (D-62, ADR 0054) adds one
platform-only scope, `proposals:review`: a key bound to an agent definition may
read the proposal queue and approve, correct or reject, which still writes the
library only through an approved proposal. A key can never step up, so the
four-eyes check constraint, not a passkey, is what stands behind an agent's
approval.

Deliberately simplified for R1: no self-service recovery of any kind (an admin
re-issues enrolment), no SSO or SCIM (R3, and they never add a password), and
credential and session policies are fixed defaults until R2 makes them tenant
settings.

When SSO arrives in R3 it proves who a person is and nothing more (D-58, ADR
0051): for an address on a bank's verified domain the identity provider replaces
the emailed code at enrolment and re-enrolment, and with enforcement on it is
asked again at every sign-in, after the passkey. There is no sign-in that starts
at the provider, and SSO never recovers a passkey or replaces step-up. A
stricter credential policy (D-55, ADR 0048) binds new registrations at once and
existing passkeys from a notice date the admin sets, so a bank can tighten
without locking itself out.

PRD 0.5 (D-69, ADR 0056) adds a second kind of credential on the same table. A
`service` key is bound to an agent access entry (`api_key.agent_access`) and acts
as it. A `personal` access token is minted by a member holding the new permission
`tokens.create`, from an authenticated session behind a passkey step-up, and
**acts as that person**, never exceeding their permissions. One table means one
hashing path, one revocation path and one security log. A personal token does not
break "a passkey is the only way in", because the passkey is how the person got
in to mint it, but that only holds while it is fenced: it cannot open a UI
session, it cannot step up and so refuses every step-up action, it must carry an
expiry, and it is revoked on the next request when the person is deactivated,
loses their membership or loses the permission its scope depends on. The scope
`tenant:read`, declared since chunk 1 and gated on no route, becomes the scope
that reaches a tenant's register decisions and nothing else.

## 2. Requirements

Priority: MoSCoW (PRD §6). Status: `pending` | `in_progress` | `built` | `verified`.

| ID | Requirement (condensed; full text in PRD) | Priority | Release | Status |
|----|----|----|----|----|
| ID-01 | Invitation only, roles set at invite | M | R1 | built |
| ID-02 | First sign-in by one-time emailed code straight into passkey enrolment; the enrolment session can do nothing else | M | R1 | built |
| ID-03 | After the first passkey, passkey only; the code stops working for that account; no password anywhere | M | R1 | built |
| ID-04 | Users manage passkeys (add, rename, remove, never the last) and see and revoke sessions | M | R1 | built |
| ID-05 | Recovery: tenant admin re-issues enrolment behind step-up, audited, with notices; the last admin goes through platform support with an out-of-band check | M | R1 | built |
| ID-06 | Step-up by fresh passkey assertion on the sensitive actions of playbook 4.2, recorded on the audit event | M | R1 | built |
| ID-07 | Tenant credential policy: synced passkeys allowed, or attested device-bound authenticators required. It binds new registrations at once and existing passkeys from the admin's notice date; loosening applies at once (D-55) | S | R2 | pending |
| ID-08 | Tenant session policy: idle and absolute limits within platform maximums | S | R2 | pending |
| ID-09 | Permissions are code, roles are rows: seeded system roles plus tenant-defined roles; a tenant always keeps one admin | M | R1 | built |
| ID-10 | Scoped API keys for agents and integrations, shown once, stored hashed, revocable, with last use | M | R1 | built |
| ID-11 | Security log of sign-ins, failures, enrolments, recoveries and key use | M | R1 | built |
| ID-12 | SSO (OIDC, SAML), verified domains and SCIM as a tenant option. SSO proves identity and never opens a session on its own; with enforcement on it is asked after the passkey at every sign-in (D-58) | C | R3 | pending |
| ID-13 | Optional IP allow-list per tenant | C | R3 | pending |
| ACC-03 | Two credential kinds on one table: a service key bound to an agent access entry, and a personal access token minted under `tokens.create` behind a step-up that acts as the person. Both shown once, hashed, expiring, revocable, with a last use and a security log row. A token cannot open a session or step up, and dies with the person | M | R2 | pending |

## 3. Acceptance criteria (from PRD, condensed)

- **AC-ID1** A user who already holds a passkey requests a code: the response is
  indistinguishable from any other code request and no email is sent.
- **AC-ID2** The enrolment session receives 403 on every route except the passkey
  registration ceremony and `GET /me`.
- **AC-ID3** A sensitive action without a fresh assertion answers 403
  `step_up_required`; the audit event of a completed one references the assertion.
- **Mechanics from playbook 4.2 (defaults, all read from settings):** invite token
  single use, stored hashed, 72 h. Code six digits, single use, 10 minutes, stored
  hashed, 5 attempts, rate limited per address and per IP, compared in constant
  time. Session: short-lived access token in memory, rotating refresh token in an
  `HttpOnly`, `Secure`, `SameSite=Strict` cookie scoped to the auth path, replay
  grace window, a `user_session` row behind every refresh. Idle 30 min and
  absolute 12 h by default (D-06). Credential fields stored: credential id, public
  key, sign count, transports, AAGUID, backup-eligible and backup-state flags,
  nickname, created, last used.

## 4. Test scenarios (Gherkin)

Integration scenarios live in `tests_scenarios.py`; E2E scenarios in
`frontend/tests/e2e/identity.journey.spec.ts`. Each test carries its scenario ID.
Stubs stay skipped until the feature lands; never delete a scenario without
updating this file.

### ID-S1 — An invitation carries roles and a single-use token that expires `@integration` (ID-01)
```gherkin
Given a tenant admin with members.manage
When they invite "anna@bank.example" with the roles "Compliance officer" and "Reader"
Then an invitation row exists with those role keys and a hashed token
And the plain token appears only in the emailed link
And opening the link after 72 hours (a setting) answers 410 with code "invitation_expired"
And opening a consumed link answers 410 as well
```

### ID-S2 — Opening the invitation sends a six-digit code within its limits `@integration` (ID-02)
```gherkin
Given a valid invitation link
When the invitee opens it
Then one six-digit code is sent to the invited address through the mailer adapter
And the code is stored hashed with a 10 minute expiry and 5 allowed attempts (settings)
And the invitee verifies with the link's token and the code alone, both in the request body, and holds an enrolment session
And a code issued for any other address does not verify with that token
And a sixth request for the same address within the window answers 429
```

### ID-S3 — A wrong code is refused and locks after five attempts `@integration` (ID-02)
```gherkin
Given a pending code for "anna@bank.example"
When five wrong codes are submitted
Then each answers 400 with code "invalid_code" in constant time
And the sixth submission, even with the right code, answers 400 "code_locked"
And a security log row records the failures
```

### ID-S4 — The enrolment session reaches only passkey registration and GET /me `@integration` `@e2e` (ID-02, AC-ID2)
```gherkin
Given Anna has verified her code and holds an enrolment session
When she calls the passkey registration options and verify endpoints
Then both answer 200
When she calls GET /me
Then it answers 200 with "enrolmentPending" true
When she calls any other route, for example GET /watch/changes
Then it answers 403 with code "enrolment_only"
```

### ID-S5 — The first passkey activates the account and asks for a second one `@integration` `@e2e` (ID-02, ID-03)
```gherkin
Given Anna holds an enrolment session and registers a passkey with user verification
And she is not asked to name it
When the registration verifies
Then a webauthn_credential row stores credential id, public key, sign count, transports, AAGUID, backup flags, nickname, created and last used
And the nickname is derived, not supplied: the authenticator's name from its AAGUID, else the browser and platform ("Chrome on Windows"), else the transport ("Security key", "Phone", "Passkey")
And the confirmation shows that name
And her account becomes active and the enrolment session is replaced by a normal session
And the screen prompts her to add a second passkey, which she may skip
```

### ID-S6 — A code request for an enrolled account looks normal and sends nothing `@integration` `@e2e` (ID-03, AC-ID1)
```gherkin
Given Anna holds a passkey
When anyone requests a code for "anna@bank.example"
Then the response status, body and timing match a request for an unknown address
And the mailer adapter sent nothing
And the security log records "code_refused_enrolled"
```

### ID-S7 — No password exists anywhere `@integration` (ID-03)
```gherkin
Given the running application
Then no user row holds a usable password hash
And no route accepts a password field
And the structural guard fails the build if either becomes false
```

### ID-S8 — Passkey sign-in issues a session `@integration` `@e2e` (ID-03)
```gherkin
Given Anna holds a passkey
When she signs in through the passkey ceremony on the sign-in page
Then the response carries a short-lived access token in the body
And a rotating refresh token in an HttpOnly, Secure, SameSite=Strict cookie scoped to the auth path
And a user_session row exists for the sign-in
And the security log records "signin_passkey"
```

### ID-S9 — Refresh rotates and a replayed refresh is refused after the grace window `@integration` (ID-03)
```gherkin
Given Anna holds a refresh cookie
When she refreshes
Then a new refresh token is issued and the old one is retired
When the old token is presented again inside the grace window (a setting)
Then the refresh succeeds without issuing a third token
When the old token is presented again after the grace window
Then it answers 401 and the whole session is revoked
```

### ID-S10 — A user adds and renames passkeys and can never remove the last one `@integration` `@e2e` (ID-04)
```gherkin
Given Anna enrolled a passkey from Chrome on Windows, named "Chrome on Windows"
When she adds a second passkey from the same browser without naming it
Then it is named "Chrome on Windows (2)", because a derived name is unique per person
And "My passkeys" lists both with created and last used
When she renames "Chrome on Windows (2)" to "Work phone"
Then the nickname changes and nothing else does
When she removes "Chrome on Windows"
Then it is gone
When she tries to remove "Work phone"
Then the request answers 409 with code "last_passkey"
```

### ID-S11 — A user sees and revokes their sessions `@integration` `@e2e` (ID-04)
```gherkin
Given Anna is signed in on two devices
When she opens "My sessions"
Then both sessions are listed with device, created and last seen
When she revokes the other device
Then the next refresh on that device answers 401
```

### ID-S12 — A tenant admin re-issues enrolment behind step-up `@integration` `@e2e` (ID-05)
```gherkin
Given Anna lost every passkey
And an admin with members.manage and a fresh step-up assertion
When the admin re-issues enrolment for Anna
Then every session of Anna is revoked and her passkeys are retired
And a new invitation code path opens for her address
And Anna and the other admins are notified
And the audit event records the admin, Anna and the step-up assertion reference
```

### ID-S13 — The last admin recovers through platform support `@integration` (ID-05)
```gherkin
Given a tenant whose only admin lost every passkey
When platform support re-issues enrolment after an out-of-band check
Then the action is written to the support access log with the check recorded
And a support access grant visible to the tenant covers the action
And the re-issued enrolment prompts for a second passkey
```

### ID-S14 — A sensitive action without a fresh assertion answers step_up_required `@integration` `@e2e` (ID-06, AC-ID3)
```gherkin
Given an approver signed in an hour ago without a step-up
When they approve a case sign-off
Then the response is 403 with code "step_up_required"
And the screen opens the passkey prompt and retries after a successful assertion
```

### ID-S15 — A completed sensitive action references its assertion on the audit event `@integration` (ID-06, AC-ID3)
```gherkin
Given an approver with a step-up assertion younger than the step-up window (a setting)
When they approve a case sign-off
Then the response is 200
And the audit event carries step_up_assertion_id pointing at that assertion
```

### ID-S16 — A tenant can require attested device-bound authenticators `@integration` (ID-07)
```gherkin
Given a tenant whose credential policy is "device-bound from the allow-list"
When a user registers a synced passkey whose AAGUID is not on the list
Then the registration answers 422 with code "credential_policy"
When a user registers an attested authenticator whose AAGUID is on the list
Then it succeeds
```

### ID-S17 — Session limits are tenant policy within platform maximums `@integration` (ID-08)
```gherkin
Given a tenant whose session policy is idle 15 minutes and absolute 8 hours
When a session is idle for 16 minutes
Then the next refresh answers 401
When an admin sets an absolute limit above the platform maximum (a setting)
Then the request answers 422 with code "above_platform_maximum"
```

### ID-S18 — Permissions are code and roles are rows `@integration` `@e2e` (ID-09)
```gherkin
Given the seeded system roles from PRD section 6
When an admin creates the role "Legal reviewer" from cases.read and cases.contribute
Then a role row exists holding those permission constants
And a member holding it can save assessment input and cannot triage
And no endpoint or component compares a role name
```

### ID-S19 — A tenant always keeps one admin `@integration` (ID-09)
```gherkin
Given a tenant with exactly one member holding members.manage
When that member's admin role is removed or the member is deactivated
Then the request answers 409 with code "last_admin"
```

### ID-S20 — An API key is shown once, stored hashed and revocable `@integration` `@e2e` (ID-10)
```gherkin
Given an admin with integrations.manage and a fresh step-up assertion
When they create a key with the scopes "watch.write" and "proposals.write"
Then the plain key appears in that one response and nowhere else
And the row stores a hash, the scopes, created and an empty last used
When the key is used
Then last used updates
When the key is revoked
Then the next call with it answers 401
```

### ID-S21 — No API key scope allows a library edit `@integration` (ID-10, AC-PRO1)
```gherkin
Given a key holding every scope that exists
When it writes to an instrument, provision or obligation route directly
Then every such route answers 403 or does not exist
And the only library-bound write it can make is a proposal
```

### ID-S22 — The security log records sign-ins, failures, enrolments, recoveries and key use `@integration` (ID-11)
```gherkin
Given the flows of ID-S3, ID-S5, ID-S8, ID-S12 and ID-S20 have run
When an admin with security.manage reads the security log
Then each of those events is present with method, actor, outcome, IP and time
And the log table refuses update and delete
```

### ID-S23 — SSO and SCIM never introduce a password `@integration` (ID-12)
```gherkin
Given a tenant that switched on an OIDC provider with a verified domain
When a member enrols through it
Then the identity provider replaces the emailed code and no password is stored anywhere
And SCIM provisioning creates members in "invited" state without a credential
And step-up still asks for a fresh passkey assertion
```

### ID-S24 — A tenant IP allow-list blocks other addresses `@integration` (ID-13)
```gherkin
Given a tenant whose allow-list holds one range
When a member signs in from outside it
Then the request answers 403 with code "ip_not_allowed" and the security log records it
```

### ID-S25 — J-1: invitation to passkey sign-in `@e2e` (ID-01, ID-02, ID-03, AC-ID1, J-1)
```gherkin
Given the seeded user awaiting enrolment and the E2E flag making the code deterministic
When they open the invitation link, enter only the code, enrol a passkey through the virtual authenticator, sign out and sign in with the passkey
Then every step succeeds through the real UI
When they request a code for their address from the sign-in page's "First time here?" path
Then the page shows the same neutral message and the mailer sent nothing
```

### ID-S26 — A denied request answers a structured 403 the UI renders as is `@integration` `@e2e` (ID-09)
```gherkin
Given a reader without cases.triage
When they call the triage endpoint
Then the response is 403 with detail, code "permission_denied" and requiredPermission "cases.triage"
And the Restricted screen shows the server's detail and the missing grant in plain words
```

### ID-S27 — SSO proves who a person is and never opens a session on its own `@integration` (ID-12)
```gherkin
Given a tenant with enforcement on and a member whose account is linked
When the member signs in
Then the passkey is verified first and the response says the identity provider is next
And the challenge is single-use and bound to the user, the tenant, the assertion and this browser
When a response arrives that no challenge asked for, or in a URL rather than a POST
Then it is refused and the security log records "idp_failed"
And there is no route that starts a sign-in at the identity provider
And on a verified domain the provider replaces the emailed code at enrolment and re-enrolment
```

### ID-S28 — A SCIM key carries one scope and its default role holds no admin permission `@integration` (ID-12)
```gherkin
Given an admin with security.manage, members.manage and a fresh step-up assertion
When they create a SCIM key on the SSO route
Then the key carries the single scope "scim" and is shown once
When the same scope is asked for on the general API key route
Then the request answers 422
When the SCIM default role is set to, or later edited to hold, members.manage, roles.manage, security.manage or integrations.manage
Then the request is refused, and a SCIM create with such a role is refused too
```

### ID-S29 — A stricter passkey policy binds new passkeys now and old ones from its notice date `@integration` (ID-07)
```gherkin
Given a tenant whose policy becomes device-bound with a notice date 14 days ahead
When a member registers a synced passkey today
Then the registration answers 422 with code "credential_policy"
When a member signs in with an existing synced passkey before the notice date
Then the sign-in succeeds
When the same member signs in after the notice date
Then the response is 403 with code "credential_policy" and the security log records it
When an admin sets a date or an allow-list that would refuse their own passkeys
Then the request answers 409

### ID-S30 — A bank invitation never reaches platform staff `@integration` (ID-01, ID-02, ID-03)
```gherkin
Given an address that holds a platform role
When a tenant admin invites it into the bank
Then the answer is 422 "platform_account" and no invitation is written
Given a bank invitation whose address is granted a platform role afterwards
When the invited person enters the emailed code and registers their first passkey
Then the answer is 422 "platform_account" with no passkey, no membership and no audit row written
```

### ID-S31 — The review scope reaches the queue and never a library row `@integration` (ID-10, AC-PRO1, AC-ID3)
```gherkin
Given a platform key bound to an agent definition and holding "proposals:review"
When it reads the proposal queue and approves, corrects or rejects a proposal it did not file
Then each call succeeds and the change reaches the library only through apply
When it writes to an instrument, provision, obligation or library vocabulary route
Then every such route answers 403 or does not exist, as ID-S21 already proves for every scope
When a key without "proposals:review" calls the same review routes
Then the request answers 403 naming the missing scope
When a key tries a step-up
Then there is no path for it: a key holds no assertion, and the review routes ask for none
And a tenant key carrying "proposals:review" is refused: the scope is platform-only
```

### ID-S32 — A member marks the library as seen and only their own bookmark moves `@integration` (PRO-03, AUD-01, AC-AUD1)
```gherkin
Given a member of a bank whose library bookmark stands at an earlier date
When the tenant app records their visit
Then the answer is 204, their bookmark stands at now and no colleague's bookmark moved
And one audit event in that bank records the visit with the bookmark before and after
When a platform session records a visit
Then the answer is 404 and nothing is written
### ACC-S3 — A service key acts as the entry and a personal token acts as the person `@integration` `@e2e` (ACC-03)
```gherkin
Given an agent access entry and a member holding tokens.create
When an admin issues a service key for the entry with a step-up
Then the audit rows of its reads name the entry, not the key id
When the member mints a personal access token with a fresh passkey assertion
Then the token is shown once, carries an expiry, and the audit rows of its reads name the member
And the token's effective permissions are the member's permissions intersected with its scopes
When a member without tokens.create tries to mint one
Then the request answers 403
When either credential is used
Then the security log records it with its own method, beside sign-ins and key use
```

### ACC-S9 — A personal token can never step up and dies with the person `@integration` (ACC-03, AC-ACC3)
```gherkin
Given a personal access token held by a compliance officer
When it calls any route carrying @requires_step_up
Then the request answers 403 "step_up_required" and there is no route by which the token could obtain an assertion
When the officer is deactivated, loses their membership, or loses the permission the token's scope depends on
Then the next request on that token is refused, without waiting for a sweep
When a token is minted with no expiry
Then the request is refused
```
