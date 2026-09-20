# ADR 0042 — Support access is requested by the platform and granted by the bank, read-only

**Date:** 2026-09-20 · **Status:** accepted (D-49, Alex 2026-09-19; PRD 0.4 §6)

## Context

Two sources disagreed. `ADM-S6` says a support request grants nothing until a
tenant admin approves it, and the designed schema makes `approved_by` the
tenant admin, while PRD §6 gives `support_access.grant` to the platform admin.
The product invariant is that platform staff have no bypass: the app role
`cw_app` cannot bypass row-level security and refuses to boot on a role that
can. Something has to let bleqq answer "our feed is stuck" without reading a
bank's case files unannounced.

## Decision

A platform admin requests read-only access to one bank with a required purpose,
an optional ticket and a duration of at most `SUPPORT_ACCESS_MAX_HOURS`
(4); a pending request lapses after `SUPPORT_ACCESS_REQUEST_TTL_HOURS`. The
request grants nothing and needs no step-up, and until approval every read
answers 404. A tenant admin approves it under `security.manage` with a passkey,
or declines, and any holder may revoke it at any time. A database CHECK keeps
`approved_by` from being the platform person, and a guard trigger refuses
DELETE and refuses any change to the tenant, person, purpose, ticket, level or
duration after insert, so only a one-shot write-level row can exist, which is
the last-admin recovery that already exists.

Entering needs `support_access.grant` plus step-up and replaces the console
session with a support session carrying the grant id and expiring with the
window. Every request re-reads the grant; a revoked or expired one answers 401
`support_access_ended`. The support principal holds `library.read`,
`watch.read`, `roadmap.read`, `register.read`, `cases.read`, `reports.read` and
`audit.read`, and nothing else: no search and no Ask, because both are POST and
would spend the bank's AI budget, no evidence or export download, no role rows
and no platform grants. Any other method answers 403 `support_read_only`. Every
request writes a `support_access.read` audit row in the bank holding the route
template and path ids, never a query string or a body, and it reaches the
bank's SIEM stream through the outbox.

Deliberately not done: the platform granting itself access, the tenant creating
grants unprompted, a tenant "requires approval" setting, write-level grants,
reusing `identity_lookup` for the console's own list, and a grant header on
each request instead of a session.

## Consequences

Easier: a bank can see who from bleqq looked at what, from its own audit log,
and an incident needs no database console. Harder: support cannot search or
download evidence, so some investigations still need the bank to export
something itself. To remember: the console list of a person's own grants runs
through one SELECT-only policy keyed on `app.platform_user_id`, set only by
`identity/session_logic.py` under an AST guard, and `tests_rls` pins it.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The table, the CHECK, the guard trigger and the request and decide routes | `c8-ten-support-grants` |
| 2 | The support session, the read-only principal and the audit row | `c8-support-access-mechanism` |
| 3 | The tenant's Support access panel, the console list and the read-only banner | `c8-card-people-access` |
