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
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Content-Security-Policy', value: "frame-ancestors 'self'" },
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
        ],
      },
    ];
  },
};

export default nextConfig;
