import type { NextConfig } from 'next';

// Playbook 2.3 and 8.3: E2E and Docker run a production build. The Docker
// image is built with NEXT_OUTPUT_STANDALONE=1 (see Dockerfile) and runs the
// emitted server.js; everywhere else `next start` serves the normal build,
// because Next refuses `next start` on a standalone output. Nothing
// Railway-specific here (DECISIONS D-16).
// The API behind this origin (D-134, ADR 0068). The browser calls /api/... on the page's
// own host and this server passes each call on to the API, so the browser talks to one
// host: no call is cross-origin, none needs a preflight, and a bank's web filter has one
// host to rate and allow. NEXT_PUBLIC_API_URL names where the API is. It is read here
// and nowhere in the browser's code, and the destination is fixed when the build runs,
// as the variable always was. Unset, nothing is passed on (the unit tests' case).
// Requests under /api skip src/proxy.ts (its matcher): a proxy buffers a request body in
// memory and cuts it at 10 MB, and evidence uploads are larger.
const apiTarget = URL.canParse(process.env.NEXT_PUBLIC_API_URL ?? '') ? new URL(process.env.NEXT_PUBLIC_API_URL as string).origin : '';

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
    return apiTarget === '' ? [] : [{ source: '/api/:path*', destination: `${apiTarget}/api/:path*` }];
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
