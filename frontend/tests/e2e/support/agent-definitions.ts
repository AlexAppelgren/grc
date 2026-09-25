import type { APIResponse, Locator, Page } from '@playwright/test';

import { expect } from './api-guard';
import { BACKEND_URL } from './passkeys';

// Helpers for c11-e2e-console (AGT-S4, AGT-S13, PRO-S8): the console's agent
// definition screen, the passkey step-up it asks for, and the one direct call a
// journey makes as the person signed in.
//
// The direct call carries the session the page itself holds: the access token
// lives in the web app's memory only (D-06), so it is read off a request the app
// sent, never minted, stored or set on the browser. It is how a journey proves
// the server's own answer to a request the screen never offers to send.

/** The seeded platform runs of watch-sweeper (apps/shared/e2e_seed.py C11_PLATFORM_RUNS): on v1, then on v2. */
export const SWEEPER_RUN_ON_V1 = '00000000-0000-4000-8000-00000c110000';
export const SWEEPER_RUN_ON_V2 = '00000000-0000-4000-8000-00000c110001';

/** Clicks through the passkey prompt when the action asks for one, then waits for `done`. */
export async function completeStepUp(page: Page, done: Locator): Promise<void> {
  const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
  await expect(prompt.or(done).first()).toBeVisible();
  if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  await expect(done).toBeVisible();
}

/** One request to the API as the person `page` is signed in as. */
export interface SessionApi {
  get(path: string): Promise<APIResponse>;
  post(path: string, data: unknown, headers?: Record<string, string>): Promise<APIResponse>;
  put(path: string, data: unknown): Promise<APIResponse>;
}

/** Reloads `page` and takes the bearer the web app sends with its own next API call. */
export async function sessionApi(page: Page): Promise<SessionApi> {
  const sent = page.waitForRequest((r) => r.url().startsWith(`${BACKEND_URL}/api/v1/`) && r.headers()['authorization']?.startsWith('Bearer ') === true);
  await page.reload();
  const authorization = (await sent).headers()['authorization'] ?? '';
  return {
    get: (path) => page.request.get(`${BACKEND_URL}/api/v1${path}`, { headers: { Authorization: authorization } }),
    post: (path, data, headers = {}) => page.request.post(`${BACKEND_URL}/api/v1${path}`, { data, headers: { Authorization: authorization, ...headers } }),
    put: (path, data) => page.request.put(`${BACKEND_URL}/api/v1${path}`, { data, headers: { Authorization: authorization } }),
  };
}

/** The answer's body once its status is the one expected; the problem's own words otherwise. */
export async function answered<T = unknown>(call: Promise<APIResponse>, status: number): Promise<T> {
  const response = await call;
  expect(response.status(), `${response.url()} answered ${await response.text()}`).toBe(status);
  return (await response.json()) as T;
}

/** A version row on the definition screen. */
export function versionRow(page: Page, versionNo: number): Locator {
  return page.locator(`[data-agent-versions] [data-agent-version="${versionNo}"]`);
}

/** The state pill of a version row: "Current", "Retired", or none. */
export function versionPill(row: Locator, label: 'Current' | 'Retired'): Locator {
  return row.locator('[data-pill]', { hasText: new RegExp(`^${label}$`) });
}

/**
 * Opens one agent definition in the console and reads its versions as the screen
 * does. Returns the numbers published, newest first.
 */
export async function openDefinition(page: Page, agentKey: string): Promise<number[]> {
  const read = page.waitForResponse((r) => new URL(r.url()).pathname === `/api/v1/agent-definitions/${agentKey}` && r.ok());
  await page.goto(`/console/agents/${agentKey}`);
  const { versions } = (await (await read).json()) as { versions: { versionNo: number }[] };
  await expect(page.locator('[data-agent-versions] [data-agent-version]')).toHaveCount(versions.length);
  return versions.map((v) => v.versionNo);
}

/** Publishes `versionNo` from the screen's form, through the passkey prompt. */
export async function publishVersion(page: Page, versionNo: number, changeNote: string): Promise<void> {
  await page.getByRole('button', { name: 'Publish a version' }).click();
  const form = page.getByRole('dialog', { name: 'Publish a new version' });
  await form.getByLabel('Version', { exact: true }).fill(String(versionNo));
  await form.getByLabel('What changed', { exact: true }).fill(changeNote);
  await form.getByRole('button', { name: `Publish version ${versionNo}` }).click();
  await completeStepUp(page, versionRow(page, versionNo));
}
