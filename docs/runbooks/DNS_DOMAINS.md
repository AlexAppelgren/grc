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
| The environment banks use (today's Railway environment) | `app.bleqq.com` (D-117; the public page stays on `bleqq.com`, see "The public site and the app on their own hosts") | `api.bleqq.com`, or the api's Railway host if the API does not need a custom domain | `app.bleqq.com` | `https://app.bleqq.com` |
| Internal staging (later, never shown to a bank) | `staging.bleqq.com` (D-117) | `api.staging.bleqq.com` | `staging.bleqq.com` | `https://staging.bleqq.com` |

The RP ID is the exact web host, never the registrable domain `bleqq.com`,
so no other bleqq.com site can request these credentials. The API host is
not the RP ID: the ceremony runs on the web origin and the API verifies it
against `WEBAUTHN_ORIGINS`.

## Steps for the test environment

1. In DNS for `bleqq.com`, add a `CNAME` for `app` pointing at the
   Railway `web` service's domain target (Railway shows it when you add a
   custom domain to the service). Railway issues the TLS certificate.
2. If the API gets its own host, add `api` the same way for
   the `api` service, and set `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`
   accordingly (`RAILWAY_VARIABLES.md`).
3. Set `WEBAUTHN_RP_ID=app.bleqq.com` and
   `WEBAUTHN_ORIGINS=https://app.bleqq.com` on the `api` service
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
or keep `app.bleqq.com` alive serving `/.well-known/webauthn` with the
new origin listed. Decide before the first real user enrols
(`TODO_FOR_alex.md`). Until then nothing serves that path.

## Cookies and paths

The refresh token cookie is `HttpOnly`, `Secure`, `SameSite=Strict` and
scoped to the auth path, so the web app and the API must share a site or
the API must be reachable from the web origin through the same registrable
domain. With the hosts above (`app.bleqq.com` and
`api.bleqq.com`) they do.

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
  USB, `Cross-Origin-Opener-Policy: same-origin`, and a content policy that
  allows only our own origin and the API (`default-src 'self'`, no plugin,
  no other base or form target, frames from our own origin only; review
  2026-11-11 S-12), beside the existing frame rules (`frontend/next.config.ts`). WebAuthn
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
   reviewer sees the fixed site. Submit each host on its own (`bleqq.com`,
   `app.bleqq.com`, `api.bleqq.com`): Broadcom's review takes one URL, and a
   subdomain can be rated apart from its domain.

**Seen on 2026-11-11.** Broadcom's Site Review answers "Suspicious" for
`https://app.bleqq.com/sign-in`, "rated by our WebPulse system". WebPulse is
Broadcom's real-time rater: a host its database does not hold is scored when
first requested, and the Suspicious category "is determined by analysis of web
reputation factors". The fix Broadcom documents is a review request, which puts
the host in the database under a category (24 to 48 hours once accepted). From
outside the same day: `www` 301s to the apex, `bleqq.com/sign-in` 301s to
`app.bleqq.com/sign-in`, both hosts send the headers above, `security.txt`
answers and an unknown address is a 404. `https://app.bleqq.com/` itself then
still answered only the session gate's "Loading your session…" to a reader
without JavaScript; it answers the public page since the same day ("The app
host's front door" below).

**What Broadcom's rater votes on, and what our pages gave it (2026-11-11).** A
new host alone does not reach "Suspicious". Broadcom's white paper on threat
risk levels puts "very new sites, or some evidence of shady behavior" at level
6 and "shady behavior" at 7, the level that returns the Suspicious category,
and says the level is a vote of module groups in which "two medium votes may
equal a high vote". The groups it names: at the request, shady traffic
("Traffic Cops"), new or untrusted, shady name, shady hosting; at DNS, the
address and its range ("Shady Neighborhood"); at the response, shady response,
network error, "Lie Detector" and shady content ("EXE, JAR/ZIP, PDF,
JScript"); afterwards, phishing detectors. Which votes a host drew is not
published, so each row below is what a headless browser measured on the live
hosts, not a proven cause.

| Measured | Whose | State |
|---|---|---|
| The sign-in page asked for `/welcome` ahead of a click on Back; the app host answers that with a move to the public host, another origin, so the browser refused it (`net::ERR_FAILED`) on every load | Code | Fixed: the back link is a plain link |
| `https://app.bleqq.com/` without a session: the same refused request, then a page load to the public host. Sign-out likewise | Code | Fixed: leaving for the public page is a page load (`shared/navigation/leave.ts`); the host-split journey fails on any refused request |
| Cloudflare's `email-decode.min.js` and encoded addresses on sign-in and enrolment | Cloudflare, Email Address Obfuscation (on by default) | Switched off by the owner; gone from outside at 07:44 UTC |
| Cloudflare's analytics beacon on every page, the application included | Cloudflare, Web Analytics automatic setup | Switched off by the owner; gone from outside at 07:44 UTC |
| `https://app.bleqq.com/` answers only "Loading your session…" to a reader without JavaScript; Broadcom: "information will be missing if the website is blank" | Code | Fixed: a visitor's front door is the public page ("The app host's front door" below) |
| `POST /api/v1/auth/refresh` answers 401 to a visitor without a session | Code | Left: it is the answer the client reads as "not signed in" |
| The host name first served in autumn 2026; shared Cloudflare addresses | Neither | Only time and Broadcom's database entry change these |

Cloudflare did not challenge a reader without a browser on any host (five
user agents, 200 each), so its bot settings do not hide the site from a rater.

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
| `APP_HOST` (`app.bleqq.com`) | `/welcome` | 301 to `/` on the first `PUBLIC_SITE_HOST` |
| | `/`, a page load from a browser without the session marker (a visitor, a crawler, a filter's fetcher) | The public page, fully rendered on the server, 200, with `Link: <https://bleqq.com/>; rel="canonical"` and no `noindex` (2026-11-11, "The app host's front door" below) |
| | `/` otherwise: the session marker is present, or the request is the demo's frame or the app's own fetch | The app, with `X-Robots-Tag: noindex` |
| | everything else | The app, as today, with `X-Robots-Tag: noindex` |
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
  instead of the demo; nothing else changes for it. One address therefore has
  two answers, and a shared cache keys on the address alone (Railway's CDN,
  which is on for the web service, keys on method, host, path and query). So
  every answer on a public host except its files goes out `Cache-Control:
  private, no-cache` (`src/proxy.ts`): the edge never stores it, and a browser
  asks again each time. The app host and the build's files stay cached at the
  edge. Without it the edge handed the frame the cached public page
  (2026-10-03).
- **The sign-in and enrolment pages** carry, under the passkey panel and
  rendered on the server, what the service is, the company name linking to the
  public page, and the privacy (`privacy@bleqq.com`, default taken) and
  security (`security@bleqq.com`, the address `security.txt` names) contacts.
  The enrolment page's first byte is the code step a visitor without a session
  gets, never an empty "Loading…". The passkey flow itself is unchanged: no
  password, the emailed code only for enrolment.

**The app host's front door (2026-11-11).** From SEB's network
`https://bleqq.com/` opened and `https://app.bleqq.com/sign-in` was denied as
Suspicious, threat score 7. Both hosts resolve to the same Cloudflare
addresses, sit in the same zone and reach the same Railway service, and a
second domain of the owner's on the same registrar, DNS, proxy and platform,
registered four months later, has no such rating. So the provider, the network
and the domain's age do not explain it. What differed was what each host
answers: the public host a whole page; the app host a sign-in and, at `/`, the
session gate's "Loading your session…", because only script knows whether a
session exists (the access token is in memory, the refresh cookie belongs to
the API host; D-06).

So the app host's front door now answers a visitor with the public page too.
The web server reads one cookie on its own host, `cw_signed_in`
(`shared/navigation/session-marker.ts`): the browser sets it whenever it is
handed an access token and clears it when the token is dropped (a sign-out, a
refresh the server refused). It is a hint and never a proof. It carries no
secret, lasts a day and is renewed at each refresh; `SameSite=Lax`, `Secure`
over HTTPS, readable by script because script writes it. A forged or stale
marker shows the gate, which asks the API exactly as before. A missing one,
with a session still alive, shows the public page, whose Sign in forwards a
signed-in person to their home without a passkey prompt. Every `/` on the app
host goes out `Cache-Control: private, no-cache`, since one address now has
more than one answer there as well.

Not proven: that this changes Broadcom's rating. It makes the app host answer
a rater what the host that passes answers. The review request and the bank's
allowlist stay the way to replace a rating that is already stored.

`sitemap.xml` lists `https://<first PUBLIC_SITE_HOST>/` once the hosts are
split, `https://bleqq.com/welcome` before. `robots.txt` is the same file on
every host.

**Variables that change** (`RAILWAY_VARIABLES.md` has each row):

| Service | Variable | Before | After |
|---|---|---|---|
| web | `PUBLIC_SITE_HOST` | unset | `bleqq.com,www.bleqq.com` |
| web | `APP_HOST` | unset | `app.bleqq.com` |
| web | `NEXT_PUBLIC_API_URL` | the api's public URL | unchanged |
| api | `CORS_ALLOWED_ORIGINS` | `https://bleqq.com` | `https://app.bleqq.com`. The public host calls no API: the demo answers from its recordings |
| api | `WEBAUTHN_ORIGINS` | `https://bleqq.com` | `https://app.bleqq.com` |
| api | `WEBAUTHN_RP_ID` | `bleqq.com` | `app.bleqq.com` |
| api | `APP_BASE_URL` | `https://bleqq.com`, or unset | `https://app.bleqq.com`, where invitation links point. Unset, it follows the first CORS origin |
| api | `ALLOWED_HOSTS` | the api host | unchanged |

Nothing else changes. The API sets no `CSRF_TRUSTED_ORIGINS` (it authenticates
with a bearer token) and no cookie domain: the refresh cookie stays host-only
on the api host, `SameSite=Strict`, scoped to `/api/v1/auth`, so the api host
must stay under `bleqq.com`, the same site as the app host, as it is today.

**The RP ID follows this runbook's rule: the exact web host,
`app.bleqq.com`.** `bleqq.com` would still be a valid RP ID for
that origin, and would keep today's passkeys working, but it lets every
`bleqq.com` site request them, which is what the rule exists to prevent, and
production will move to `app.bleqq.com` anyway. **Changing the RP ID
means every test user re-enrols their passkeys**: a passkey made under
`bleqq.com` is not offered on `app.bleqq.com` once the RP ID says
otherwise. The way back, in order:

1. The platform admin, whose own passkey stops working at the same moment:
   `python manage.py bootstrap_platform --admin-email <your address> --reenrol`
   retires your passkeys, revokes your sessions and personal tokens (in the console
   and in any bank you are a member of), keeps your platform roles and emails a re-enrolment
   link; enrol again from it. An account that is also a bank's member gets its
   bank access back with the same passkey (D-122).
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
