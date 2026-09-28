import type { NextConfig } from 'next';

// Playbook 2.3 and 8.3: E2E and Docker run a production build. The Docker
// image is built with NEXT_OUTPUT_STANDALONE=1 (see Dockerfile) and runs the
// emitted server.js; everywhere else `next start` serves the normal build,
// because Next refuses `next start` on a standalone output. Nothing
// Railway-specific here (DECISIONS D-16).
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
  // approve or sign off. Our own origin may, because the public page frames the
  // app as its demo (design/public/README.md "The demo"). The API refuses every
  // frame on its own side (backend/config/settings.py). X-Frame-Options is the
  // same rule for browsers that predate frame-ancestors.
  //
  // The rest is what a bank's web filter looks for on a site it is asked to
  // trust (docs/runbooks/DNS_DOMAINS.md "Site trust"). HSTS names this host
  // only: includeSubDomains and preload wait until every bleqq.com subdomain is
  // known to serve HTTPS (docs/TODO_FOR_alex.md), since both are hard to take
  // back. Browsers ignore HSTS over plain HTTP, so local runs are unaffected.
  // Permissions-Policy denies what no screen uses; it leaves WebAuthn
  // (publickey-credentials-get and -create) at its default of our own origin,
  // which the passkey ceremonies and the framed demo need.
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Content-Security-Policy', value: "frame-ancestors 'self'" },
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
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
