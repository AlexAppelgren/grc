# ADR 0068 — The browser reaches the API through the app host

**Date:** 2026-11-12 · **Status:** accepted (Alex, 2026-11-11, in chat, asked whether to ship it: "yeah lets do that"; after the outage, 2026-11-12: "I still want cloudflare of course, but we should fix so it works"; D-134). Both steps are built: the route answered on the live site before the browser was switched to it.

## Context

The browser loads its pages from the app host (`app.bleqq.com`) and calls the API on a
second host (`api.bleqq.com`), cross-origin, with credentials. On 2026-11-11 the owner's
bank let the app host through its web filter, the sign-in page loaded, and pressing "Sign in
with a passkey" answered "The server could not be reached". The owner's Network tab on the
bank's device (2026-11-12) shows the one call the button makes first, `options`, failed
with no status and no bytes. The app shows that sentence only when a call got
no answer at all; a refused passkey shows another sentence, and the passkey prompt comes
after this call. From outside the bank the same call answers correctly.

Broadcom documents this class of failure for its proxy: "There is no known solution for
authenticating un-credentialed CORS requests" (`Verification_Log.md`), and a preflight is
one. Which mode the bank's proxy runs was not confirmed. The owner's two other products
serve pages and API from one host and have no such trouble: their web server passes `/api`
on to the backend.

**The first attempt broke sign-in for everyone.** The same was built here with the web
server passing `/api` on to the API's public address, and reached `main` at 01:16 UTC on
2026-11-12. Every call then answered 403 from Cloudflare, "Error 1000, DNS points to
prohibited IP", until the revert reached `main` at 02:01 UTC and was live by 02:09. The request came in through
Cloudflare, which adds `CF-Connecting-IP`; the web server passed it on to a host in the same
Cloudflare zone; Cloudflare refuses a request that carries that header and no
`CDN-Loop: cloudflare`. Measured afterwards against the live zone, and reproduced with a
local build of the reverted commit (`Verification_Log.md`). Cloudflare's own guidance for
this error is to send to the origin and not through the proxy a second time. No journey
could see it: the test stack has no Cloudflare.

Two more faults of that attempt were found by measurement before the second one. Next cuts
a request body it passes on at 10 MB, with or without the proxy file in the way, so an
11 MiB upload answered 500. Next gives up on an answer after 30 s of silence, and an Ask
stream may be silent for longer.

## Decision

- **One host for the browser, and behind it an address that does not pass Cloudflare.**
  The browser calls `/api/...` on the page's own origin. `next.config.ts` rewrites
  `/api/:path*` to the address in `API_INTERNAL_URL`. It is never the API's address behind
  Cloudflare. Since 2026-11-12 it is the API's own Railway address
  (`https://grc-backend-staging.up.railway.app`), which the API already accepted as a host.
  The platform's private network is the shorter leg and the intended one: it needs a fixed
  port, and Railway picks the API's port itself and does not let another service refer to
  it (`Verification_Log.md`), so the port must be pinned on the live API first. The
  variable is the web service's own, stays on the server, and is read when the build runs.
- **Two steps, so that a wrong address could not take sign-in down.**
  1. *The route.* The web server passed `/api` on once the variable was set, while the
     browser still called the API host, so nothing a person did depended on the route. The
     owner set the variable, and the route was called on the live site from outside.
  2. *The switch.* Only then: the client has no base address and calls `/api/...` on the
     page's origin, `connect-src` is `'self'`, and the journeys run the same path. The
     refresh cookie belongs to the app host; D-06 is otherwise unchanged. A production
     build without `API_INTERNAL_URL` stops with an error, so a web service that could not
     reach its API is never deployed; the deployment before it stays live.
- **The web server cuts nothing short.** `experimental.proxyClientMaxBodySize` is 26 MiB,
  just above the API's `EVIDENCE_MAX_BYTES` (25 MiB), and `experimental.proxyTimeout` is
  200 s, above `LLM_DEADLINE_S` (180 s). Both have a variable
  (`API_INTERNAL_MAX_BODY_BYTES`, `API_INTERNAL_TIMEOUT_MS`). The API keeps its own limits
  and refuses in its own words. Next holds each body in memory while it passes it on, which
  is why the first is no larger than it has to be.
- **A body above the limit never reaches the API.** Next does not refuse such a body: it
  cuts it and passes the rest on, and the API then waits for bytes that never come, with a
  worker held until the wait ends (measured: no answer for 90 s and more). Eight such calls
  would hold every worker. So `src/proxy.ts` answers a call under `/api` itself when its
  `Content-Length` is above the limit (413 `payload_too_large`) or when the body does not
  say how large it is (411 `length_required`), in the API's problem format, at once. Every
  other call under `/api` goes on untouched, and the rules for pages do not apply to it.
- **The Ask stream says `no-transform`.** Next compresses what it passes on and holds a
  compressed stream back until it ends: measured, five events 400 ms apart arrived together
  after two seconds, and one by one once the response said `no-transform`
  (`apps/search/api.py`; NFR-02).
- **The API's paths are the API's on every host** of the web service, the public host
  included, where they used to move to the app host.

## Consequences

- **What the API receives over the route.** Next sends `Host` as the destination's, so the
  API's `ALLOWED_HOSTS` must name it, and passes `X-Forwarded-Proto` and `X-Forwarded-For`
  on unchanged, appending nothing (measured with a local build and an echo server). Over
  the private network the API would therefore read the caller's address as on the direct
  path. Over the Railway address the call passes Railway's edge a second time, and what
  that edge does with `X-Forwarded-For` is not documented: the per-address limits and the
  security log may read the web service's address for every caller. That is stricter, not
  looser, and it is open in `TODO_FOR_alex.md`.
- **The API's Railway address is a door to the API that Cloudflare does not guard.** It
  existed before this decision and the route now depends on it. The private network would
  let it be closed.
- **A bank allows one host fewer.** The browser never contacts the API host. It stays public, behind
  Cloudflare as before, for agents and integrations that call it with a key.
- **Cloudflare stays in front of everything a browser touches.** A call through the route
  has already passed Cloudflare on the app host; only the leg between our two services
  leaves it out.
- **Everyone signs in once more.** A browser that signed in before the switch holds its
  refresh cookie for the API host, which the app no longer calls.
- **The calendar feed's address comes from `APP_BASE_URL`**, not from the request's host
  (`apps/home/feed.py`): over the route that host is the address the web server reaches
  the API on, which is not one to hand out. Addresses handed out earlier name the API host and keep
  working.
- **A file's size.** A file between the API's cap and the web server's limit gets the API's
  own sentence, as before; one above the limit gets the web server's 413. The evidence
  journey attaches and downloads a file above 10 MB through the screen.
- **The API reads a refused body to its end before it answers.** Without that, a large
  upload the API refuses at once could come back as the web server's 500. Measured on the
  live route: an 11 MiB body to a call the API answers without reading the body (a 401)
  came back as the API's 401 nine times in ten and as a 500 once; on the API's own
  addresses ten in ten. Repeated on a laptop with gunicorn: two in twenty, each "write
  EPIPE" in Next's log. The API answered and closed while Next was still sending, and Next
  reports the broken send. `UnreadBodyMiddleware` (`apps/shared/middleware.py`) reads what
  the view left unread, up to `UNREAD_BODY_MAX_BYTES` (26 MiB, the web server's own limit):
  forty in forty then answered 401. An upload the API accepts was never affected.
- **`NEXT_PUBLIC_API_URL` is gone.** Nothing reads it: not the browser's code, not the
  build. CORS stays configured and unused by the app; removing it is a separate change.
- **A wrong address is the remaining risk.** The API's address behind Cloudflare in
  `API_INTERNAL_URL` would repeat the outage. The runbook says so, and the check after any
  change to it is one call from outside (`DNS_DOMAINS.md`).

## Not done

The move to the private network, which needs the API's port pinned. Removing the unused CORS
configuration. Which `X-Forwarded-For` entry is the caller's
on the deployed chain has still to be read from a real request before `TRUSTED_PROXY_HOPS`
changes (`TODO_FOR_alex.md`).
