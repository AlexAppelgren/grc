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
| Railway test | `compliance-test.bleqq.com` (proposed; the public page on `bleqq.com`, see "The public site and the app on their own hosts") | `api.compliance-test.bleqq.com` (proposed), or the api's Railway host if the API does not need a custom domain | `compliance-test.bleqq.com` | `https://compliance-test.bleqq.com` |
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

## The public site and the app on their own hosts

Package `r2f-host-split`, approved by Alex on 2026-09-28. Seen without
JavaScript, `https://bleqq.com/` served the app's shell (title "Compliance
Watch", text "Loading your session…"), the sign-in page was one link away and
the real public page lived at `/welcome`. An empty page that loads a login, on
a young domain aimed at banks, is the profile a web filter scores as phishing.
So the public page and the app get hosts of their own, as the table above
already planned for the app (D-02).

**What the web service does** (`frontend/src/proxy.ts`, the rules in
`frontend/src/shared/navigation/hosts.ts`, read at run time):

| Host | Request | Answer |
|---|---|---|
| A `PUBLIC_SITE_HOST` (`bleqq.com`, `www.bleqq.com`) | `/` | The public page, fully rendered on the server, 200, indexable |
| | `/welcome` | 301 to `/` on the same host, query kept |
| | any other path: sign-in, enrolment, invitation, the app, the console, `/api/…`, an unknown path | 301 to the same path and query on `APP_HOST` |
| | `robots.txt`, `sitemap.xml`, `icon.svg`, `/.well-known/…`, `/demo/…`, `/_next/…` | Served as they are |
| `APP_HOST` (`compliance-test.bleqq.com`) | `/welcome` | 301 to `/` on the first `PUBLIC_SITE_HOST` |
| | everything else, `/` included | The app, as today, with `X-Robots-Tag: noindex` |
| Any other host (the service's `*.up.railway.app` address, the health check) | anything | As today |
| Any host, while `PUBLIC_SITE_HOST` or `APP_HOST` is unset | anything | As today: this is the default, and every journey but the host-split one runs so |

Two details a reviewer asks about:

- **The demo.** The public page frames the app as its demo, and the demo only
  runs in a frame whose parent is its own origin (`features/demo/frame.ts`), so
  on a public host the app has to load inside the frame. Only a page load
  moves: a request whose `Sec-Fetch-Dest` is `document`, or that has none (a
  crawler, a filter's fetcher). The frame's own load (`iframe`) and the app's
  navigations inside it (`empty`) pass, marked noindex. A browser too old to
  send `Sec-Fetch-Dest` (Safari before 16.4) sees the public page in the frame
  instead of the demo; nothing else changes for it.
- **The sign-in and enrolment pages** carry, under the passkey panel and
  rendered on the server, what the service is, the company name linking to the
  public page, and the privacy (`privacy@bleqq.com`, default taken) and
  security (`security@bleqq.com`, the address `security.txt` names) contacts.
  The enrolment page's first byte is the code step a visitor without a session
  gets, never an empty "Loading…". The passkey flow itself is unchanged: no
  password, the emailed code only for enrolment.

`sitemap.xml` lists `https://<first PUBLIC_SITE_HOST>/` once the hosts are
split, `https://bleqq.com/welcome` before. `robots.txt` is the same file on
every host.

**Variables that change** (`RAILWAY_VARIABLES.md` has each row):

| Service | Variable | Before | After |
|---|---|---|---|
| web | `PUBLIC_SITE_HOST` | unset | `bleqq.com,www.bleqq.com` |
| web | `APP_HOST` | unset | `compliance-test.bleqq.com` |
| web | `NEXT_PUBLIC_API_URL` | the api's public URL | unchanged |
| api | `CORS_ALLOWED_ORIGINS` | `https://bleqq.com` | `https://compliance-test.bleqq.com`. The public host calls no API: the demo answers from its recordings |
| api | `WEBAUTHN_ORIGINS` | `https://bleqq.com` | `https://compliance-test.bleqq.com` |
| api | `WEBAUTHN_RP_ID` | `bleqq.com` | `compliance-test.bleqq.com` |
| api | `APP_BASE_URL` | `https://bleqq.com`, or unset | `https://compliance-test.bleqq.com`, where invitation links point. Unset, it follows the first CORS origin |
| api | `ALLOWED_HOSTS` | the api host | unchanged |

Nothing else changes. The API sets no `CSRF_TRUSTED_ORIGINS` (it authenticates
with a bearer token) and no cookie domain: the refresh cookie stays host-only
on the api host, `SameSite=Strict`, scoped to `/api/v1/auth`, so the api host
must stay under `bleqq.com`, the same site as the app host, as it is today.

**The RP ID follows this runbook's rule: the exact web host,
`compliance-test.bleqq.com`.** `bleqq.com` would still be a valid RP ID for
that origin, and would keep today's passkeys working, but it lets every
`bleqq.com` site request them, which is what the rule exists to prevent, and
production will move to `compliance.bleqq.com` anyway. **Changing the RP ID
means every test user re-enrols their passkeys**: a passkey made under
`bleqq.com` is not offered on `compliance-test.bleqq.com` once the RP ID says
otherwise. The way back, in order:

1. The platform admin, whose own passkey stops working at the same moment:
   `bootstrap_platform` refuses an address that still holds a passkey, so run
   it with a new address of your own
   (`python manage.py bootstrap_platform --admin-email <new address>`) and
   enrol that. The old platform account stays unusable, which is harmless on
   a test deployment.
2. One administrator of each test bank: the platform re-issues their
   enrolment with `POST /api/v1/console/tenants/{tenantId}/members/{userId}/reissue-enrolment`
   (step-up, audited). The console has no screen for it yet, so on a test
   deployment it can be simpler to create the test bank again (`FIRST_RUN_SETUP.md`
   step 6).
3. Everyone else in the bank: their administrator re-issues each enrolment
   from Admin › Members, and the person enrols again from the email.

**Railway and Cloudflare** (Railway's "Working with domains", checked
2026-09-28, `Verification_Log.md`): the web service's Settings › Public
Networking › `+ Custom Domain` shows a `CNAME` target and a `TXT` record; both
are required ("If the TXT record is missing, requests to your custom domain
will return a 404"). Railway issues a Let's Encrypt certificate, usually within
an hour. Behind Cloudflare's proxy SSL/TLS must be **Full**, not Full (Strict).
The owner's steps, in order, are the `r2f-host-split` block of
`docs/TODO_FOR_alex.md`.

**Tests.** `frontend/src/shared/navigation/hosts.test.ts` pins every row of
the table. The public journey (`frontend/tests/e2e/public.journey.spec.ts`,
"the public site and the app on hosts of their own") runs a second server of
the same build with both variables set: the app host is `localhost:3001`, the
same site as the API and the passkeys' RP ID as in a deployment, and the public
host `public.localhost:3001`. `support/split-hosts.mjs` sits in front of Next
the way Railway's edge does: Next writes a redirect to its own origin
(`localhost` and the port it listens on) as a relative one, which a deployed
app host never is.

**For a bank.** A bank's web filter or proxy should allow `*.bleqq.com`: the
public page, the app and the API are separate hosts under it, and a filter that
allows only one of them breaks sign-in. `FIRST_RUN_SETUP.md` asks this of a bank
before its first person enrols, and `docs/assurance/network-access.md` states it
for a vendor review.
