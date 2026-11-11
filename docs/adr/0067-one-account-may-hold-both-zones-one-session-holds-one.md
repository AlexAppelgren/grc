# ADR 0067 — One account may hold both zones; one session holds one, and a passkey switches between them

**Date:** 2026-11-08 · **Status:** accepted (Alex, 2026-11-08, in chat: "I would also like the option where I can both be an admin and part of a tenant as a user, and then if they are used with both there is a toggle to switch between the two contexts"; D-122; supersedes hardening H13's rule that platform staff are separate accounts; leaves ADR 0042 and ADR 0064 unchanged)

## Context

Hardening H13 (2026-09-20) made platform staff separate accounts. `bootstrap_platform`
refused an address any bank knew, a bank invitation and its acceptance refused an address
holding a platform role (422 `platform_account`), and so did a new bank's first
administrator. It had two reasons. Before ADR 0064 a session's grants were read in a way
that could let a platform grant ride into a bank session, and the audit row of a platform
grant has no tenant, so a bank never saw that one of its members had been given the console.

The owner wants one passkey for both: to work in a bank as a member and to run the platform,
with a toggle between the two.

## Decision

- **The mutual exclusion goes.** `bootstrap_platform` (its normal path and `--reenrol`), a
  bank invitation, its acceptance and `create_tenant`'s first administrator accept an address
  the other zone knows. The code `platform_account` no longer exists.
- **A session is still in exactly one zone.** `session_logic.build_principal` is unchanged: a
  session with no bank reads only the platform assignments and keeps what
  `PLATFORM_PERMISSIONS` names; a bank session reads only that bank's membership grants and
  keeps what `TENANT_PERMISSIONS` names. The token signs its zone (ADR 0064). Tests pin both
  directions for a dual account.
- **Sign-in keeps its default.** `choose_tenant`: the oldest active membership, else the console.
- **A switch is a new session behind a passkey.** `POST /me/context` with `tenantId` (a bank the
  person is an active member of) or null (the console, when they hold an active platform role).
  It needs a full session and a passkey step-up on it fresher than the step-up window. The old
  session is revoked with the reason `context_switched` in its own zone, the zone is changed,
  and `create_session` writes the new one. The refresh cookie is replaced the way sign-in sets
  it. The security log gets a `signin` row in the new zone with the reason `context_switched`.
  The audit trail gets `session.revoked` in the old zone and `session.created` and
  `session.context_switched` (carrying the step-up) in the new one. The answer is the same
  `SessionTokens` sign-in returns. The step-up belongs to the old session and never moves, so
  every switch costs one fresh assertion and an assertion can serve one switch at most. A bank
  or console the person does not hold, and the context they are already in, answer 404
  `not_found`. `GET /me` lists `contexts`: every context held, with the current one marked.
- **Entering the console from a bank leaves the bank's zone.** `switch_context` is the one new
  caller of `tenancy.clear_tenant()` (the guard in `apps/shared/tests_tenancy.py` names it),
  reached only by a full session with a fresh step-up whose person holds an active platform
  role. The person's banks are read through the identity lookup by `held_banks`, which replaces
  `choose_tenant` in that guard's list; `choose_tenant` now calls it.
- **The bank sees it.** A member who holds any platform role carries `platformStaff` true on
  Admin › Members, and the members screen marks them. `bootstrap_platform` writes the
  `platform_role.assigned` row in each bank the person is an active member of as well as the
  one without a tenant. `--reenrol` revokes the person's sessions in each of their banks too,
  since their passkeys are retired account-wide, and writes the re-enrolment row in each bank.
- **Unchanged:** support access (D-49, ADR 0042) is the only way platform staff read a bank
  they are not a member of; four eyes compares account ids, so a dual account cannot approve in
  one zone what it asked for in the other (support access to its own bank, a library proposal
  it filed); every write goes through `record()`; RFC 9457 errors carry `code`.

## Threat model

| Case | What happens |
|---|---|
| A bank session of a dual account calls a console route | 403: the session holds no platform permission |
| A console session of a dual account calls a bank route | 404 or 403: the session has no bank, so it holds no bank permission |
| A stolen access token is used to switch | 403 `step_up_required` unless the thief also passes a passkey ceremony on that session |
| A switch to a bank the person left, or never joined | 404 `not_found`; nothing written |
| A dual account asks for support access to its own bank as platform staff and approves it as the bank's admin | 409: four eyes compares the account id |
| A dual account files a library proposal from its bank and approves it in the console | 409: four eyes compares the account id |
| A platform role is granted to a bank member | The bank's audit log shows `platform_role.assigned`; Members marks them |
| A bank administrator re-issues enrolment for a member who is also in another bank or holds a platform role (review 2026-11-11 S-2) | 409 `account_held_elsewhere` from the bank route and the console route, and nothing is written: passkeys have no bank, so only the platform owner re-enrols such an account, with `bootstrap_platform --reenrol`, which ends its sessions and tokens in every zone. A full session of an account that is not `active` resolves to nothing in any zone |

## Consequences

- One person may now appear in a bank's member list and in the console's staff. The marker
  and the bank-side audit row are what keep that visible to the bank.
- Signing in lands where it did; the switch is an explicit, stepped-up act each time.
- The old 422 `platform_account` is gone from the contract.
