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

const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3000);
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8000);
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
  expect: {
    timeout: 5_000,
    toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: 'disabled' },
  },
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
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
            env: { E2E_BACKEND_PORT: String(BACKEND_PORT) },
          },
        ]),
    {
      command: `npm run build && npm run start -- --port ${FRONTEND_PORT}`,
      url: `http://localhost:${FRONTEND_PORT}/`,
      timeout: 300_000,
      reuseExistingServer: !isCI,
      env: {
        // Same site as the web app (localhost, docs/runbooks/DNS_DOMAINS.md): the
        // refresh cookie is SameSite=Strict, and 127.0.0.1 would be another site.
        NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? `http://localhost:${BACKEND_PORT}`,
        NEXT_TELEMETRY_DISABLED: '1',
      },
    },
  ],
});
