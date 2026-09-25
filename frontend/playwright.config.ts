import { fileURLToPath } from 'node:url';

import { defineConfig, devices } from '@playwright/test';

// One command runs it (playbook 8.3): webServer boots the real backend
// (throwaway DB, migrate from zero, seed_e2e, Django with E2E_MODE) and a
// PRODUCTION Next build. Never `next dev`: it hands specs un-hydrated HTML
// (measured in the last repo: 3 to 6 minutes with retries under next dev,
// 35 seconds and zero flakes under next start).
//
// E2E_SKIP_BACKEND=1 drops the backend entry. It exists for the Phase 0
// window in which the backend does not exist yet and for the gallery and
// spike specs that make no API call; api-guard prints a loud notice whenever
// it is set. It is not a way to run journeys without the API.
//
// Cold start (docs/runbooks/FIRST_RUN_SETUP.md): `npm run test:e2e -- --grep
// @coldstart` runs the one journey that walks a first deploy, so its stack is
// booted the way a deploy boots — migrate, seed_reference, nothing else. It
// gets its own database name and its own ports, five above the ordinary ones
// and so still inside the worktree slot's band of ten (scripts/worktree.sh),
// and it can never reuse or recreate the seeded run's stack. Every other run
// filters the journey out, because a seeded database would prove nothing.

// The mode is chosen once, from the command line, and then travels in the
// environment: a worker process loads this file again with its own argv, which
// carries no `--grep`, and pointed the first cold-start run at the seeded
// stack's ports. Everything the workers and the servers need is exported
// below, and every derivation is written so that reading it back changes
// nothing.
const COLD_SUFFIX = '_cold';
const coldStart = process.env.E2E_COLD_START === '1' || /(^|[\s=])@coldstart([\s]|$)/.test(process.argv.join(' '));
const COLD_PORT_OFFSET = coldStart ? 5 : 0;

const configuredDatabase = process.env.E2E_DATABASE_NAME ?? 'compliance_watch_e2e';
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3000) + COLD_PORT_OFFSET;
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8000) + COLD_PORT_OFFSET;
const DATABASE_NAME = coldStart && !configuredDatabase.endsWith(COLD_SUFFIX) ? `${configuredDatabase}${COLD_SUFFIX}` : configuredDatabase;
const API_URL = coldStart ? `http://localhost:${BACKEND_PORT}` : (process.env.NEXT_PUBLIC_API_URL ?? `http://localhost:${BACKEND_PORT}`);
const WEB_URL = `http://localhost:${FRONTEND_PORT}`;

// A worker that never saw the command line still resolves the same ports, the
// same database and the same base URL. The port variables are deliberately left
// alone: the offset is applied to them on every load.
if (coldStart) process.env.E2E_COLD_START = '1';
// support/passkeys.ts reads the mail outbox on E2E_BACKEND_URL, and the
// cold-start journey runs its management command against E2E_DATABASE_NAME.
process.env.E2E_BACKEND_URL = API_URL;
process.env.E2E_DATABASE_NAME = DATABASE_NAME;

const skipBackend = process.env.E2E_SKIP_BACKEND === '1';
const isCI = process.env.CI !== undefined;

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: isCI ? 2 : undefined,
  reporter: isCI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  timeout: 30_000,
  ...(coldStart ? { grep: /@coldstart/ } : { grepInvert: /@coldstart/ }),
  expect: {
    timeout: 5_000,
    toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: 'disabled' },
  },
  use: {
    baseURL: WEB_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'en-GB',
    timezoneId: 'Europe/Stockholm',
    colorScheme: 'light',
  },
  // Screenshot baselines are generated on Chromium only (playbook 6.7).
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    ...(skipBackend
      ? []
      : [
          {
            command: 'bash tests/e2e/support/start-backend.sh',
            url: `http://127.0.0.1:${BACKEND_PORT}/health/`,
            timeout: 240_000,
            reuseExistingServer: !isCI,
            stdout: 'pipe' as const,
            stderr: 'pipe' as const,
            env: {
              E2E_BACKEND_PORT: String(BACKEND_PORT),
              E2E_DATABASE_NAME: DATABASE_NAME,
              ...(coldStart
                ? {
                    E2E_COLD_START: '1',
                    // The cold web app is on its own port, so it is its own origin.
                    CORS_ALLOWED_ORIGINS: WEB_URL,
                    WEBAUTHN_ORIGINS: WEB_URL,
                    APP_BASE_URL: WEB_URL,
                    E2E_WORKER_LOG: fileURLToPath(new URL('./test-results/e2e-worker-coldstart.log', import.meta.url)),
                  }
                : {}),
            },
          },
        ]),
    {
      // CI's E2E job builds the app earlier in the job, beside its other setup, and sets
      // E2E_PREBUILT (D-90): the same production build with the same NEXT_PUBLIC_API_URL.
      command: `${process.env.E2E_PREBUILT === '1' ? '' : 'npm run build && '}npm run start -- --port ${FRONTEND_PORT}`,
      url: `${WEB_URL}/`,
      timeout: 300_000,
      reuseExistingServer: !isCI,
      env: {
        // Same site as the web app (localhost, docs/runbooks/DNS_DOMAINS.md): the
        // refresh cookie is SameSite=Strict, and 127.0.0.1 would be another site.
        NEXT_PUBLIC_API_URL: API_URL,
        NEXT_TELEMETRY_DISABLED: '1',
      },
    },
  ],
});
