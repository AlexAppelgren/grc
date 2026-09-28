# Network access: what a bank allows in its web filter and proxy

For a bank's vendor review and its network team. Written by package
`r2f-host-split` (2026-09-28); the pack's `README.md` (chunk 14,
`c14-assurance-locations-a`) will list it.

## What to allow

Allow **`*.bleqq.com`** (and `bleqq.com` itself) in the bank's web filter,
secure web gateway and outbound proxy, for HTTPS on port 443. Compliance Watch
runs on separate hosts under that one domain:

| Host | What it serves |
|---|---|
| `bleqq.com` (and `www.bleqq.com`, which redirects to it) | The public page: what the service is, how to get access, the security contact (`/.well-known/security.txt`) |
| `compliance-test.bleqq.com` today, `compliance.bleqq.com` in production | The application: sign-in with a passkey, and every screen |
| The API host under `bleqq.com` | The application's API, called by the browser from the application host |

A filter that allows only one of them breaks the service: the public page's
Sign in moves to the application host, and the application calls the API host.
Allowing the one domain, rather than each host, keeps working when a host is
added (production, a region) without a change request at the bank.

## Why a filter may flag the domain before it is allowed

`bleqq.com` is a young domain, and reputation engines score young domains
cautiously. On 2026-09-28 one bank's filter classed it as "Suspicious". What
the site does about it, and what the owner asks of the filter vendors, is in
`docs/runbooks/DNS_DOMAINS.md` ("Site trust", "The public site and the app on
their own hosts"): the public page is fully readable without JavaScript, the
application sits on its own host marked noindex, unknown addresses answer 404,
every page sends HSTS and the other security headers, and `security.txt` names
a contact.

## What the service needs from the browser

- JavaScript, cookies for the API host (the rotating refresh cookie is
  `HttpOnly`, `Secure`, `SameSite=Strict`), and WebAuthn: a passkey is the only
  way in, so a proxy that strips or blocks the WebAuthn prompt, or a browser
  policy that disables passkeys, stops sign-in.
- No TLS interception is required. Passkeys need a secure page, so a proxy
  that intercepts TLS must present a certificate the browser trusts.

Unverified: the exact API host of the test deployment. It is the owner's to
confirm (`docs/TODO_FOR_alex.md`, block `r2f-host-split`).
