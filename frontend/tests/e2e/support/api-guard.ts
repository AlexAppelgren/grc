import { test as base, expect, type Page } from '@playwright/test';

// The API guard (playbook 8.3): an auto fixture that fails an otherwise
// passing journey on any undeclared `/api/` response of 400 or more, or any
// uncaught page exception. A journey that provokes an error on purpose
// declares it where it happens:
//   apiGuard.allow(/\/signoff\/approve/, 409, 'the requester cannot sign off')
// Every spec imports `test` from here; ESLint enforces it.

export interface AllowedFailure {
  pattern: RegExp;
  status: number;
  reason: string;
}

export interface ApiGuard {
  allow(pattern: RegExp | string, status: number, reason: string): void;
  /** Guards a page from another browser context, e.g. the second person of a four-eyes journey. */
  watch(page: Page): void;
}

// Known smells awaiting a fix. Each entry is a task; delete it when the task
// closes; never widen. Empty in Phase 0.
export const DEFAULT_ALLOWLIST: readonly AllowedFailure[] = [];

const SKIP_BACKEND_NOTICE = [
  '',
  '=================================================================',
  '  E2E_SKIP_BACKEND=1: the backend webServer is DISABLED.',
  '  Only specs that make no API call are valid in this mode',
  '  (pills gallery, green spike, the Phase 0 shell smoke).',
  '  Any journey that needs the API is NOT being tested.',
  '=================================================================',
  '',
].join('\n');

let noticePrinted = false;

function watch(page: Page, allowed: AllowedFailure[], failures: string[]): void {
  page.on('response', (response) => {
    const url = response.url();
    const status = response.status();
    if (!url.includes('/api/') || status < 400) return;
    const path = new URL(url).pathname;
    const declared = allowed.some((a) => a.status === status && a.pattern.test(path));
    if (!declared) failures.push(`${status} ${response.request().method()} ${path}`);
  });
  page.on('pageerror', (error) => {
    failures.push(`page error: ${error.message}`);
  });
}

export const test = base.extend<{ apiGuard: ApiGuard }>({
  apiGuard: [
    async ({ page, context }, use, testInfo) => {
      if (process.env.E2E_SKIP_BACKEND === '1') {
        testInfo.annotations.push({ type: 'warning', description: 'E2E_SKIP_BACKEND=1: backend webServer disabled' });
        if (!noticePrinted) {
          noticePrinted = true;
          process.stderr.write(SKIP_BACKEND_NOTICE);
        }
      }
      const allowed: AllowedFailure[] = [...DEFAULT_ALLOWLIST];
      const failures: string[] = [];
      watch(page, allowed, failures);
      context.on('page', (opened) => watch(opened, allowed, failures));

      await use({
        allow(pattern, status, reason) {
          const regex = typeof pattern === 'string' ? new RegExp(pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) : pattern;
          allowed.push({ pattern: regex, status, reason });
        },
        // A second person in their own browser context (four eyes) is held to
        // the same rules as the fixture's page: their undeclared failures fail
        // the journey too.
        watch(other) {
          watch(other, allowed, failures);
          other.context().on('page', (opened) => watch(opened, allowed, failures));
        },
      });

      if (failures.length > 0) {
        throw new Error(`api-guard: undeclared failures during the journey:\n  ${failures.join('\n  ')}`);
      }
    },
    { auto: true },
  ],
});

export { expect };
