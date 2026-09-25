# ADR 0056 — A service key and a personal access token, on one table, and a token can never step up

**Date:** 2026-09-20 · **Status:** accepted (owner decision, 2026-09-20; D-77, PRD 0.5 ACC-03, ID-10)

## Context

An agent a bank runs needs a credential. Two shapes are wanted and they are not
interchangeable. A deployed or scheduled agent holds a long-lived secret that
belongs to the agent, and the audit log should name the agent. A developer
wiring an agent to their own session wants a credential that is theirs, bounded
by their own access, and that names them in the audit log.

Alex asked for both, keys first, and then restated it as "access provided through
a key / personal access tokens".

This sits against the product's hardest invariant. There is no password anywhere,
the emailed code dies at first passkey, and a passkey is the only way in. A
bearer token that works without a passkey looks, from a distance, exactly like the
thing the product refuses to have.

## Decision

Both kinds are `api_key` rows, separated by a new `kind` column.

- **`kind = service`** is bound to an agent access entry through
  `api_key.agent_access`, acts as that entry, and takes its permissions from the
  key's scopes. Created under `agent_access.manage` behind a step-up.
- **`kind = personal`** is minted by a member holding the new permission
  `tokens.create`, from an authenticated session, behind a passkey step-up. It
  **acts as that person**: the audit log names the human, and its effective
  permissions are that person's permissions intersected with the token's scopes
  and, where it names an entry, that entry's scope.

A personal token does not break "a passkey is the only way in", because the
passkey is how the person got in to mint it. That reasoning only holds while the
token is fenced, so the fence is part of the decision and not an implementation
detail:

- It **cannot open a UI session**. It authenticates API and MCP requests only.
- It **cannot step up**. Every route carrying `@requires_step_up` answers 403
  `step_up_required` to it, always, with no route to an assertion. A token
  therefore cannot approve, sign off, export, change the footprint, create a key
  or change a role, which is the entire list of what four eyes protects.
- It **must carry an expiry**, defaulting to 90 days, and cannot be minted
  without one.
- It **dies with the person**: deactivation, loss of membership, or loss of the
  permission a token's scope depends on revokes it, checked on every request
  rather than by a nightly sweep.
- Every mint, use and revocation is a `LoginEvent` with its own method, so ID-11's
  security log shows it beside sign-ins and key use. The person sees their own
  tokens in their settings; an admin sees and revokes every token in the tenant.

`tokens.create` is granted by default to Admin, Compliance officer and Owner, and
a bank may grant it to any role.

## Why

One table means one hashing path, one revocation path, one security log and one
admin screen. Two tables would mean two of each, and the second would be the one
that forgets to check `revoked_at`.

The step-up fence is what keeps the invariant honest rather than merely
technically satisfied. A token that could step up would be a password with a
longer name. A token that cannot step up is structurally incapable of doing
anything four eyes protects, which means the worst a stolen token can do is read
what its holder could already read, and the tenant reach switch bounds even that.

"Dies with the person" is checked per request rather than swept because the sweep
is the version that leaves a leaver's credential live overnight. It costs one
join on a path that already loads the principal.

## Consequences

- `api_key` gains `kind` and `agent_access`. `ApiKeyAuth` gains the acts-as-person
  branch and the step-up refusal. Nothing else in identity changes shape.
- A person's tokens are revoked by TEN-05's member removal flow, which already
  handles reassigning their open work and now also stops their credentials.
- **Reversal.** Refusing `kind = personal` at the mint route leaves service keys
  alone, which is where ID-10 already was.
