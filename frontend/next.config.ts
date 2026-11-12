import type { NextConfig } from 'next';

import { API_MAX_BODY_BYTES } from './src/shared/navigation/api-body';

// Playbook 2.3 and 8.3: E2E and Docker run a production build. The Docker
// image is built with NEXT_OUTPUT_STANDALONE=1 (see Dockerfile) and runs the
// emitted server.js; everywhere else `next start` serves the normal build,
// because Next refuses `next start` on a standalone output. Nothing
// Railway-specific here (DECISIONS D-16).
// The API behind this origin (D-134, ADR 0068). The browser calls /api/... on the page's
// own host and this server passes each call on to the API at API_INTERNAL_URL, so the
// browser talks to one host: no call is cross-origin, none needs a preflight, and a bank's
// web filter has one host to rate and allow. The variable names the address the two
// services share on the platform's private network, never the API's public one: a call to
// the public address goes back through the edge proxy the request came in by, and that
// proxy refuses it (the outage of 2026-11-12). Read when the build runs. `next dev` falls
// back to the local API; a production build without it stops here, because the app it
// would make could not reach its API.
const apiInternalUrl = process.env.API_INTERNAL_URL ?? (process.env.NODE_ENV === 'development' ? 'http://localhost:8000' : '');
if (!URL.canParse(apiInternalUrl)) throw new Error('API_INTERNAL_URL is not set to an address: the web server passes /api on to it (docs/adr/0068).');
const apiInternal = new URL(apiInternalUrl).origin;
// What this server must not cut short on the way. Left alone, Next cuts a request body it
// passes on at 10 MB and gives up on an answer after 30 s of silence (both measured
// 2026-11-12: an 11 MiB upload and a 35 s wait each answered 500). The API has its own
// limits and refuses in its own words, so these two sit just above them: the body at
// API_MAX_BODY_BYTES, above which src/proxy.ts refuses a call before it is passed on, the
// wait above LLM_DEADLINE_S (180 s), the longest an Ask stream may stay silent.
const apiTimeoutMs = Number(process.env.API_INTERNAL_TIMEOUT_MS) || 200_000;

// The content policy (review 2026-11-11 S-12): the app loads nothing from another
// origin and calls nothing on another origin, so everything is 'self'. Inline
// scripts and styles stay allowed because Next and next-themes write them; a nonce from
// src/proxy.ts is the later, stricter step. `next dev` alone needs eval (React's dev
// call stacks and fast refresh). object-src, base-uri and form-action close the ways a
// stray script or markup could load a plugin, rebase links or post a form elsewhere.
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === 'development' ? " 'unsafe-eval'" : ''}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "frame-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'self'",
].join('; ');

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT_STANDALONE === '1' ? 'standalone' : undefined,
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: { proxyClientMaxBodySize: API_MAX_BODY_BYTES, proxyTimeout: apiTimeoutMs },
  // In an agent worktree (scripts/worktree.sh), node_modules is a link to the main
  // checkout, and Turbopack refuses a link that leaves its root ("points out of the
  // filesystem root", 2026-09-19). The worktree slot sets the root to the main checkout,
  // which contains both. Unset everywhere else, so nothing changes outside a worktree.
  ...(process.env.NEXT_TURBOPACK_ROOT ? { turbopack: { root: process.env.NEXT_TURBOPACK_ROOT } } : {}),
  // Clickjacking: no other site may frame a page of the app, where one click can
  // approve or sign off (frame-ancestors in the policy above). Our own origin may,
  // because the public page frames the app as its demo (design/public/README.md "The
  // demo"), at "/" on its own origin, which frame-src 'self' allows. The API refuses
  // every frame on its own side (backend/config/settings.py). X-Frame-Options is the
  // same rule for browsers that predate frame-ancestors. Cross-Origin-Opener-Policy
  // keeps a window of another site, opened from here or opening us, out of this
  // browsing context group: no screen opens a window or reads an opener.
  //
  // The rest is what a bank's web filter looks for on a site it is asked to
  // trust (docs/runbooks/DNS_DOMAINS.md "Site trust"). HSTS names this host
  // only: includeSubDomains and preload wait until every bleqq.com subdomain is
  // known to serve HTTPS (docs/TODO_FOR_alex.md), since both are hard to take
  // back. Browsers ignore HSTS over plain HTTP, so local runs are unaffected.
  // Permissions-Policy denies what no screen uses; it leaves WebAuthn
  // (publickey-credentials-get and -create) at its default of our own origin,
  // which the passkey ceremonies and the framed demo need.
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${apiInternal}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Content-Security-Policy', value: contentSecurityPolicy },
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
          { key: 'Strict-Transport-Security', value: 'max-age=31536000' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=()' },
        ],
      },
    ];
  },
};

export default nextConfig;
