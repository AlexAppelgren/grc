# ADR 0051 — SSO proves who a person is; the passkey stays the only way in

**Date:** 2026-09-20 · **Status:** accepted (D-58, Alex 2026-09-19; PRD 0.4 ID-02, ID-12)

## Context

ID-12 offers SSO, verified domains and SCIM as a tenant option in R3, and
`ID-S23` read as though a member could sign in through the identity provider.
The product's first invariant is that nobody has a password and a passkey is
the only way in; an identity provider that could open a session would be a
second way in, and its password reset would become ours. Banks still need their
directory to control who may enrol and to end access when someone leaves. This
is the SSO stance the ADR index has owed since Phase 0.

## Decision

SSO proves who a person is; the passkey stays the only way in. For addresses on
a bank's verified domains, the bank's identity provider replaces the emailed
code at enrolment and re-enrolment, and with enforcement on it must also pass
at every sign-in, after the passkey. There is no "Sign in with your
organisation" button, no sign-in that starts at the provider, and unsolicited
responses are refused. SSO never opens a session on its own, never recovers a
lost passkey and never replaces step-up. Addresses outside the verified
domains, an external auditor's for example, keep the emailed code, and a code
request for a verified-domain address sends nothing.

With enforcement on, the passkey comes first; the API then answers `next: idp`
and stores a single-use challenge bound to the user, the tenant, the assertion
and the browser, the last through a short-lived single-use cookie compared at
the callback. Callbacks arrive by POST, never in a URL. Switching enforcement
on needs `security.manage`, a step-up and a successful round trip by the acting
admin, otherwise 409; the screen first shows how many members are not yet
linked, and members outside the domains are marked "outside SSO". Platform
support may switch enforcement off after an out-of-band check. A link is the
directory id SCIM provisioned, or is made at an invitation or re-enrolment
where the token and the provider's proof arrive together, and never by matching
an email claim at sign-in; every link emails the member and notifies the other
admins. Domains are verified by a DNS TXT record, one tenant per domain, under
`security.manage` with a step-up. A SCIM key is an API key with the single
scope `scim`, created only on the SSO route under `security.manage` and
`members.manage` with a step-up; `POST /tenant/api-keys` refuses that scope
(422). SCIM creates invitations with one default role, which may not hold
`members.manage`, `roles.manage`, `security.manage` or `integrations.manage`,
checked when the default is chosen, when that role is edited and at every
create, and SCIM deactivates people as today and never changes roles. OIDC
comes first; SAML only if its library passes the Alpine image and Trivy.

Deliberately not done: SSO as an alternative way to sign in, SSO replacing
passkeys, the provider first and the passkey second, enforcing for every
domain, group-to-role sync, joining by domain, a separate SCIM token column,
and matching on the email claim.

## Consequences

Easier: the passkey invariant is unchanged word for word, and SCIM
deprovisioning ends access without a second credential to revoke. Harder: two
proofs at sign-in where enforcement is on, and an E2E identity provider to
build and to keep out of production, like the mail outbox. To remember:
`record()` audits the provider, enforcement, domains, links and every SCIM
action; the security log gains `idp_verified` and `idp_failed`; and if time
runs short, SAML is cut first and enforcement second.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Verified domains and the provider configuration | `c13-sso-domains` |
| 2 | OIDC at enrolment and re-enrolment, enforcement at sign-in, and the E2E provider | `c13-sso-oidc` |
| 3 | SCIM with its single-scope key and role guard | `c13-scim` |
