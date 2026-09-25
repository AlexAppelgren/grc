# ADR 0048 — A stricter passkey policy binds at registration now and at sign-in from a notice date

**Date:** 2026-09-20 · **Status:** accepted (D-55, Alex 2026-09-19; ADR 0003's third tranche)

## Context

ID-07 lets a bank require attested device-bound authenticators. No passkey
registered today under attestation `none` can prove its model, so enforcing on
the day the policy is saved would lock every member out, while enforcing at
registration only would leave every existing synced passkey working for ever. A
bank has to be able to show that its choice of authenticator holds when someone
signs in, not only when they enrolled. py_webauthn's own verification accepts
self attestation and formats rooted in vendor certificates, so its result alone
is not the policy.

## Decision

A stricter policy binds new registrations from the moment it is saved, and
existing non-compliant passkeys stop working at a notice date the admin sets,
14 days ahead by default; loosening takes effect at once. The policy lives on
the tenant `security_policy` row in three fields: `credential_policy`
(`any_passkey` or `device_bound`), `allowed_authenticators`, chosen from a
committed platform list of models built from the FIDO Metadata Service, and
`device_bound_from`. A change needs `security.manage` plus step-up, is audited
with before and after, and notifies the other admins.

One compliance function decides, and does not trust the library's result alone.
In a `device_bound` tenant, registration asks for direct attestation and
accepts only `packed` or `tpm` statements carrying a certificate chain; the
chain is verified against the roots of the claimed model only, an empty root
set is refused, the certificate's AAGUID extension must match the
authenticator's when present and must be present when a root serves several
models, and backup eligibility must be unset. The `apple`, `android-key` and
`android-safetynet` formats are refused, because the library adds its own
vendor roots for them. After an assertion verifies, a non-compliant passkey in
a `device_bound` tenant past the date answers 403 `credential_policy` with a
security-log row, a refused step-up leaves the action undone, and sessions
opened before the date run out at the absolute limit. Any edit, of the date or
of the allow-list, that would refuse the acting admin's own passkeys from now
on answers 409. Non-compliant passkeys are kept but open nothing; recovery is
an admin re-issuing enrolment, or platform support for the last admin.

For every bank now, and not only for `device_bound` ones, the backup-eligibility
flag in each assertion is compared with the stored one at sign-in and at
step-up, as WebAuthn Level 3 requires and today's code does not do.

Deliberately not done: checking at registration only, enforcing at sign-in from
the moment the policy is saved, a restricted "upgrade" session, an AAGUID
allow-list without attestation, and downloading FIDO metadata at runtime.

## Consequences

Easier: a bank can tighten its policy without locking anyone out, and can show
an auditor when the tightening took effect. Harder: our own code now carries
attestation rules the library would otherwise have decided, and the platform
must keep a list of authenticator models. To remember: the FIDO Metadata
Service's terms must be read before its data is used, and the screen a bank
needs is the list of members without a compliant passkey.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The backup-eligibility check for every bank | R1 hardening follow-ups |
| 2 | The three fields, the compliance function, the sign-in and step-up refusals and the lockout guard | `c11-credential-policy` |
| 3 | The policy form, the date picker and the list of members without a compliant passkey | `c11-fe-admin-security` and the frontend package after it |
