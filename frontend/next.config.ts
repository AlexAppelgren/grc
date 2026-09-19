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
};

export default nextConfig;
