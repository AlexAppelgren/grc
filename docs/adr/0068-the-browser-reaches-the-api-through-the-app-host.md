# ADR 0068 — The browser reaches the API through the app host

**Date:** 2026-11-11 · **Status:** accepted (Alex, 2026-11-11, in chat, asked whether to ship it: "yeah lets do that"; D-134)

## Context

The browser loaded its pages from the app host (`app.bleqq.com`) and called the API on a
second host (`api.bleqq.com`), cross-origin, with credentials. On 2026-11-11 the owner's
bank let the app host through its web filter (Broadcom re-rated it Finance that morning),
the sign-in page loaded, and pressing "Sign in with a passkey" answered "The server could
not be reached". From outside the bank the same calls answered correctly: the preflight 200
with the CORS headers, the call itself 200.

Broadcom documents this class of failure for its proxy: "CORS presents a problem for
authentication when using origin-cookie-redirect and form-cookie-redirect modes", and
"There is no known solution for authenticating un-credentialed CORS requests"
(`Verification_Log.md`). A CORS preflight carries no credentials by definition. Which mode
the bank's proxy runs was not confirmed, so this is the documented cause that fits, not a
proven one.

The owner's two other products (ESC-App and the older bleqq) run on the same registrar, DNS,
proxy and platform and have no such trouble. Both serve pages and API from one host: Next
rewrites `/api/*` to the backend on the server, so their browser never makes a cross-origin
call.

## Decision

- **One host for the browser.** The client calls `/api/...` on the page's own origin
  (`shared/utils/api-client.ts` sets no base address). `next.config.ts` rewrites
  `/api/:path*` to the API. No call is cross-origin, none needs a preflight, and a bank's
  filter has one host to rate and allow.
- **`NEXT_PUBLIC_API_URL` keeps its name and its place.** It names where the API is, as
  before, and the build fixes the rewrite's destination from it, as it fixed the client's
  base address before. It is no longer read by any code the browser runs. No variable
  changes on any environment.
- **The rewrite, not the proxy file.** Requests under `/api` skip `src/proxy.ts` (its
  matcher). A proxy buffers a request body in memory and cuts it at 10 MB
  (`proxyClientMaxBodySize`), and evidence uploads go to 25 MB (`EVIDENCE_MAX_BYTES`). So
  the API's paths are answered by the API on every host of the web service, the public
  host included, where they used to move to the app host.
- **The session design is unchanged (D-06).** The access token stays in memory. The refresh
  cookie is the same cookie with the same attributes (`HttpOnly`, `Secure`,
  `SameSite=Strict`, path `/api/v1/auth`); it now belongs to the app host, because that is
  the host the browser called. Passkeys, their RP ID and the origin check are untouched.
- **The Ask stream says `no-transform`.** Next compresses what it passes on and holds a
  compressed stream back until it ends: measured, five events 400 ms apart arrived together
  after two seconds, and one by one once the response said `no-transform`. The route's
  stream format adds it (`apps/search/api.py`), which also tells every other proxy on the
  way to leave the stream alone (NFR-02, first token under 2 s).
- **The content policy closes.** `connect-src` is `'self'`: the page calls nothing on
  another origin.

## Consequences

- **A bank allows one host fewer.** The browser never contacts the API host. The API host
  stays public for agents and integrations, which call it with a key.
- **One more hop per call.** A call goes browser, edge, web server, API. With
  `NEXT_PUBLIC_API_URL` at the API's public address that second leg crosses the edge again.
  Pointing it at the platform's private address shortens it; that is an owner step, and the
  API's `ALLOWED_HOSTS` must then name that address.
- **The address the API sees.** `client_ip` reads `X-Forwarded-For` from the right by
  `TRUSTED_PROXY_HOPS`. The web server passes the header on unchanged and appends nothing
  (Next's proxy sets no `xfwd`). Through the public address the edge appends its own hops
  again, so the rightmost entries are the edge's, shared by every caller: per-address
  limits then count all callers together, which is stricter and not looser, and the
  security log names the edge. Over the private address the header arrives exactly as the
  web service received it and the reading is what it was. Which entry is the caller's on
  the deployed chain has to be read once from a real request before
  `TRUSTED_PROXY_HOPS` is changed; a wrong value would trust an entry the caller wrote.
  `TODO_FOR_alex.md` holds it.
- **CORS stays configured and unused by the app.** Nothing the browser does needs it any
  more; removing it is a separate change.
- **Journeys run the same path as production.** The E2E stack calls the API through the web
  server too. The host-split journey fails if the app calls any origin but its own, and the
  Ask journey fails if the stream arrives compressed or without `no-transform`.

## Not done

The API's private address, `TRUSTED_PROXY_HOPS` on the new chain, and removing the unused
CORS configuration.
