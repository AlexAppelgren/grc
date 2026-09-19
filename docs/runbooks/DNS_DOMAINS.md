# DNS, domains and the passkey RP ID

For the owner. The agent keeps this true as environments are added.

## Why the host matters more than usual

A passkey is bound to one relying-party ID (D-02, ADR 0002; verified
2026-09-19, `Verification_Log.md`). Credentials enrolled under one RP ID do
not work under another. So the host a user enrols on has to be a host we
keep. Passkeys made on a `*.up.railway.app` host stop working the day that
host changes.

## Hosts per environment

| Environment | Web host | API host | `WEBAUTHN_RP_ID` | `WEBAUTHN_ORIGINS` |
|---|---|---|---|---|
| Local | `localhost:3000` | `localhost:8000` | `localhost` | `http://localhost:3000` |
| CI and E2E | `localhost:3000` (production Next build) | `localhost:8000` | `localhost` | `http://localhost:3000` |
| Railway test | `compliance-test.bleqq.com` (proposed) | `api.compliance-test.bleqq.com` (proposed), or the api's Railway host if the API does not need a custom domain | `compliance-test.bleqq.com` | `https://compliance-test.bleqq.com` |
| Production (later) | `compliance.bleqq.com` (proposed, D-02) | `api.compliance.bleqq.com` (proposed) | `compliance.bleqq.com` | `https://compliance.bleqq.com` |

The RP ID is the exact web host, never the registrable domain `bleqq.com`,
so no other bleqq.com site can request these credentials. The API host is
not the RP ID: the ceremony runs on the web origin and the API verifies it
against `WEBAUTHN_ORIGINS`.

## Steps for the test environment

1. In DNS for `bleqq.com`, add a `CNAME` for `compliance-test` pointing at the
   Railway `web` service's domain target (Railway shows it when you add a
   custom domain to the service). Railway issues the TLS certificate.
2. If the API gets its own host, add `api.compliance-test` the same way for
   the `api` service, and set `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`
   accordingly (`RAILWAY_VARIABLES.md`).
3. Set `WEBAUTHN_RP_ID=compliance-test.bleqq.com` and
   `WEBAUTHN_ORIGINS=https://compliance-test.bleqq.com` on the `api` service
   before anyone enrols.
4. Set `NEXT_PUBLIC_API_URL` on `web` to the API's public URL and redeploy
   `web` (the value is baked at build time).
5. For the mail sender's domain, add SPF and DKIM records as the provider
   instructs, so invitation codes are delivered.

Test deploys use throwaway passkeys: if the test host changes, everyone
re-enrols, which is fine there and not fine in production.

## Related Origin Requests

If the product ever needs a second origin to use the same passkeys (a
rebrand to a new domain, a bank-hosted tenant zone on its own host), the
WebAuthn Related Origin Requests mechanism lets the RP ID's host publish
`/.well-known/webauthn` listing the origins allowed to use its credentials.
Support: Chrome and Edge 128, Safari 18, Firefox 152 (verified 2026-09-19).
This means a rebrand has two options: re-enrol everyone under the new host,
or keep `compliance.bleqq.com` alive serving `/.well-known/webauthn` with the
new origin listed. Decide before the first real user enrols
(`TODO_FOR_alex.md`). Until then nothing serves that path.

## Cookies and paths

The refresh token cookie is `HttpOnly`, `Secure`, `SameSite=Strict` and
scoped to the auth path, so the web app and the API must share a site or
the API must be reachable from the web origin through the same registrable
domain. With the hosts above (`compliance-test.bleqq.com` and
`api.compliance-test.bleqq.com`) they do.
