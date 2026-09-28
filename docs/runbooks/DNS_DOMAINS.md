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

## Site trust: what a bank's web filter checks

On 2026-09-28 SEB's corporate web filter blocked `https://www.bleqq.com/` as
"Suspicious" (threat score 7). A reputation engine scores a new domain on what
it can see from outside, so the site has to look like what it is. The code
half is built (package `r2f-site-trust`); the rest is DNS, Cloudflare and the
filter vendors, and only the owner can do it.

**What the site now does (code):**

- An address no route serves answers **404**, with the same not-found screen.
  Before, every unknown path (`/this-page-does-not-exist-9x`,
  `/.well-known/security.txt`) answered 200 with the app: a soft 404, the
  pattern of phishing kits and parked domains. The catch-all lives in
  `frontend/src/app/(missing)/`, outside the session gate, so the server
  renders it and sets the status.
- `robots.txt` lets crawlers read `/`, `/welcome` and what that page loads,
  closes everything else by default, and points at `sitemap.xml`, which lists
  only `https://bleqq.com/welcome`. Every page except the public route group
  carries `noindex, nofollow`.
- `/.well-known/security.txt` (RFC 9116): contact `security@bleqq.com`,
  expiry within a year, languages en and sv, canonical
  `https://bleqq.com/.well-known/security.txt`. Renew `Expires` before
  2027-09-27; the public journey fails once it has passed.
- Every page sends `Strict-Transport-Security: max-age=31536000`,
  `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin` and a
  `Permissions-Policy` denying camera, microphone, geolocation, payment and
  USB, beside the existing frame rules (`frontend/next.config.ts`). WebAuthn
  stays at its default of our own origin. HSTS carries no
  `includeSubDomains` or `preload` until every `bleqq.com` subdomain is known
  to serve HTTPS: both are hard to take back.

**What was found from outside on 2026-09-28 (DNS over HTTPS, curl):**

| Check | Found |
|---|---|
| `www.bleqq.com` | Proxied by Cloudflare (A and AAAA are Cloudflare addresses), but not attached to any Railway service: it answers Railway's fallback, 404 JSON with `x-railway-fallback: true` |
| `http://bleqq.com/…` | 301 to `https://bleqq.com/…` already |
| SPF, `bleqq.com` TXT | `v=spf1 include:secureserver.net -all`. MX is `secureserver.net` (the mailbox host), but the invitation mail goes out through Brevo, which this record does not name |
| Brevo | `brevo-code:…` TXT present (domain verified); no DKIM record checked in |
| DMARC, `_dmarc.bleqq.com` | `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` |

**Steps only the owner can take** (the same list sits in `docs/TODO_FOR_alex.md`,
block `r2f-site-trust`; review addresses in `docs/plans/Verification_Log.md`):

1. **www.** In Cloudflare, Rules › Overview › Create rule › Redirect Rule:
   wildcard pattern, request URL `https://www.bleqq.com/*`, target
   `https://bleqq.com/${1}`, status **301**, query string preserved. The `www`
   record is already proxied, which the rule needs. The alternative is to
   attach `www.bleqq.com` to the frontend service in Railway, but then two
   hosts serve the same pages; the redirect is the better choice.
2. **HTTPS everywhere.** SSL/TLS › Edge Certificates › **Always Use HTTPS**
   on (the apex already redirects; this makes it true for every host).
3. **SPF.** Change the `bleqq.com` TXT record to
   `v=spf1 include:secureserver.net include:spf.brevo.com -all`
   (`spf.brevo.com` resolves to Brevo's SPF record, checked 2026-09-28).
4. **DKIM.** In Brevo's domain settings for `bleqq.com`, authenticate the
   domain: add the DKIM record(s) Brevo shows, exactly as shown, in
   Cloudflare DNS (DNS only, never proxied), and let Brevo verify them.
5. **DMARC.** Once the aggregate reports at `rua@dmarc.brevo.com` show only
   Brevo and the mailbox host passing for a few weeks, move `_dmarc` to
   `v=DMARC1; p=quarantine; rua=mailto:rua@dmarc.brevo.com`.
6. **The filters.** Ask SEB IT to recategorise or allow `bleqq.com`, and
   submit `bleqq.com` for categorisation as Business / Software (and
   Financial Services where offered) to each vendor: Zscaler, Palo Alto
   Networks, Broadcom (Symantec), Cisco Talos, Fortinet and Forcepoint. Do
   this after steps 1 to 5 and after this package is deployed, so the
   reviewer sees the fixed site.
