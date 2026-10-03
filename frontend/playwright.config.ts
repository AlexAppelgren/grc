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

// The public page's demo (design/public/README.md "The demo"): `npm run test:e2e --
// --grep @demo`, and `npm run demo:record`, walk the demo person's screens on a stack of
// their own, seeded the way the demo's data is made — migrate, then seed_public_demo: the
// real library baseline through the proposal door and a made-up bank on top. Its own
// database and ports, seven above the ordinary ones and inside the slot's band of ten, so
// it never shares the seeded run's data and the recordings never hold a fixture.
//
// The mode is chosen once, from the command line, and then travels in the
// environment: a worker process loads this file again with its own argv, which
// carries no `--grep`, and pointed the first cold-start run at the seeded
// stack's ports. Everything the workers and the servers need is exported
// below, and every derivation is written so that reading it back changes
// nothing.
const argv = process.argv.join(' ');
const coldStart = process.env.E2E_COLD_START === '1' || /(^|[\s=])@coldstart([\s]|$)/.test(argv);
const demoStack = !coldStart && (process.env.E2E_DEMO_STACK === '1' || /(^|[\s=])@demo([\s]|$)/.test(argv));
// A stack of its own: its database suffix, its port offset and its worker log's name.
const OWN_STACK = coldStart ? { suffix: '_cold', offset: 5, name: 'coldstart' } : demoStack ? { suffix: '_demo', offset: 7, name: 'demo' } : null;

const configuredDatabase = process.env.E2E_DATABASE_NAME ?? 'compliance_watch_e2e';
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3000) + (OWN_STACK?.offset ?? 0);
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8000) + (OWN_STACK?.offset ?? 0);
const DATABASE_NAME = OWN_STACK && !configuredDatabase.endsWith(OWN_STACK.suffix) ? `${configuredDatabase}${OWN_STACK.suffix}` : configuredDatabase;
const API_URL = OWN_STACK ? `http://localhost:${BACKEND_PORT}` : (process.env.NEXT_PUBLIC_API_URL ?? `http://localhost:${BACKEND_PORT}`);
const WEB_URL = `http://localhost:${FRONTEND_PORT}`;
// The same build once more with the public site and the app on hosts of their
// own (src/proxy.ts, support/split-hosts.mjs); every other journey runs on
// WEB_URL, where neither host setting is set.
const SPLIT_PORT = FRONTEND_PORT + 1;
const SPLIT_APP_URL = `http://localhost:${SPLIT_PORT}`;
const SPLIT_PUBLIC_URL = `http://public.localhost:${SPLIT_PORT}`;

// A worker that never saw the command line still resolves the same ports, the
// same database and the same base URL. The port variables are deliberately left
// alone: the offset is applied to them on every load.
if (coldStart) process.env.E2E_COLD_START = '1';
if (demoStack) process.env.E2E_DEMO_STACK = '1';
// support/passkeys.ts reads the mail outbox on E2E_BACKEND_URL, and the
// cold-start journey runs its management command against E2E_DATABASE_NAME.
process.env.E2E_BACKEND_URL = API_URL;
process.env.E2E_DATABASE_NAME = DATABASE_NAME;
// The host-split journey in public.journey.spec.ts reads both.
process.env.E2E_SPLIT_APP_URL = SPLIT_APP_URL;
process.env.E2E_SPLIT_PUBLIC_URL = SPLIT_PUBLIC_URL;

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
  ...(coldStart ? { grep: /@coldstart/ } : demoStack ? { grep: /@demo/ } : { grepInvert: /@coldstart|@demo/ }),
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
            // The demo's seed files and approves the whole library baseline, about four
            // minutes on a CI runner, before the server starts.
            timeout: demoStack ? 900_000 : 240_000,
            reuseExistingServer: !isCI,
            stdout: 'pipe' as const,
            stderr: 'pipe' as const,
            env: {
              E2E_BACKEND_PORT: String(BACKEND_PORT),
              E2E_DATABASE_NAME: DATABASE_NAME,
              ...(OWN_STACK
                ? {
                    ...(coldStart ? { E2E_COLD_START: '1' } : { E2E_DEMO_STACK: '1' }),
                    // A stack of its own is on its own port, so its web app is its own origin.
                    CORS_ALLOWED_ORIGINS: WEB_URL,
                    WEBAUTHN_ORIGINS: WEB_URL,
                    APP_BASE_URL: WEB_URL,
                    E2E_WORKER_LOG: fileURLToPath(new URL(`./test-results/e2e-worker-${OWN_STACK.name}.log`, import.meta.url)),
                  }
                : {
                    // The split server's app host is an origin of its own.
                    CORS_ALLOWED_ORIGINS: `${WEB_URL},${SPLIT_APP_URL}`,
                    WEBAUTHN_ORIGINS: `${WEB_URL},${SPLIT_APP_URL}`,
                  }),
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
    // Started after the entry above has built the app, since web servers start in order.
    ...(OWN_STACK
      ? []
      : [
          {
            command: 'node tests/e2e/support/split-hosts.mjs',
            url: `${SPLIT_APP_URL}/robots.txt`,
            timeout: 60_000,
            reuseExistingServer: !isCI,
            env: {
              E2E_SPLIT_PORT: String(SPLIT_PORT),
              PUBLIC_SITE_HOST: new URL(SPLIT_PUBLIC_URL).host,
              APP_HOST: new URL(SPLIT_APP_URL).host,
              NEXT_PUBLIC_API_URL: API_URL,
              NEXT_TELEMETRY_DISABLED: '1',
            },
          },
        ]),
  ],
});
