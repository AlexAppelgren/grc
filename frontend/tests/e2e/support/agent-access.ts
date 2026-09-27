import { execFileSync } from 'node:child_process';
import path from 'node:path';

import type { APIRequestContext, Page, PlaywrightWorkerArgs, Response } from '@playwright/test';

import { expect, test, type ApiGuard } from './api-guard';
import { BACKEND_URL } from './passkeys';

// Agent access as a tenant admin works it (ACC-01, ACC-03, ACC-08, J-11), through
// /admin/agents/access and /admin/security and their passkey step-ups, and the
// agent itself, which is the REST API and its key and nothing else. The plain
// key is returned to the caller and nowhere else: never written to disk,
// attached or logged, and the one-time panel is closed before returning.

const ACCESS_ROUTES = /\/api\/v1\/agent-access(\/[^?]*)?$/;
const REACH_ROUTES = /\/api\/v1\/tenant\/reach\/(requests|off)(\/[^?]*)?$/;

/** The step-up answers every agent access write gives before the passkey prompt opens. */
export function allowAccessStepUps(apiGuard: ApiGuard): void {
  apiGuard.allow(ACCESS_ROUTES, 403, 'an agent access write answers step_up_required first and opens the passkey prompt');
  apiGuard.allow(REACH_ROUTES, 403, 'a tenant reach write answers step_up_required first and opens the passkey prompt');
}

/**
 * Clicks `trigger` and waits for the write it sends to be answered past its step-up: the
 * prompt opens unless this session's passkey assertion is still fresh, and is confirmed.
 */
async function withStepUp(page: Page, matches: (response: Response) => boolean, trigger: () => Promise<void>): Promise<Response> {
  const answered = page.waitForResponse((r) => matches(r) && r.status() !== 403);
  await trigger();
  const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
  const prompted = prompt.waitFor({ state: 'visible' }).then(
    () => true,
    () => false,
  );
  if (await Promise.race([answered.then(() => false), prompted])) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  const response = await answered;
  expect(response.ok(), `${response.url()} answered ${response.status()}`).toBe(true);
  return response;
}

const writeTo = (suffix: RegExp, method: string) => (r: Response) => suffix.test(new URL(r.url()).pathname) && r.request().method() === method;

export interface EntryRequest {
  /** Unique to the attempt, so a retry never finds an earlier attempt's entry. */
  name: string;
  purpose: string;
  /** The owning team's key, such as `trading`. */
  team: string;
  /** Department names to narrow it to; none reads the whole regulatory scope. */
  departments: readonly string[];
}

/** Registers an entry on /admin/agents/access and returns its id. */
export async function registerEntry(page: Page, request: EntryRequest): Promise<string> {
  await page.goto('/admin/agents/access');
  await page.getByRole('button', { name: 'Register an agent' }).click();
  const form = page.locator('[data-entry-form]');
  await form.getByLabel('Name', { exact: true }).fill(request.name);
  await form.getByLabel('Purpose', { exact: true }).fill(request.purpose);
  await form.getByLabel('Owned by', { exact: true }).selectOption(request.team);
  for (const department of request.departments) {
    await form.getByRole('checkbox', { name: new RegExp(`^${department}`) }).check();
  }
  const created = await withStepUp(page, writeTo(/\/api\/v1\/agent-access$/, 'POST'), () => form.getByRole('button', { name: 'Register', exact: true }).click());
  await expect(page.getByText('Registered. Issue it a key to let it read.', { exact: true })).toBeVisible();
  return ((await created.json()) as { id: string }).id;
}

/** Issues a key on the entry's page and returns its id and plain key, shown once. */
export async function issueEntryKey(page: Page, entryId: string, name: string, scopes: readonly string[]): Promise<{ id: string; plainKey: string }> {
  await page.goto(`/admin/agents/access/${entryId}`);
  await page.locator('[data-credentials]').getByRole('button', { name: 'Issue a key' }).click();
  const form = page.locator('[data-issue-form]');
  await form.getByLabel('Name', { exact: true }).fill(name);
  for (const scope of scopes) await form.locator(`[id="issue-scope-${scope}"]`).check();
  const created = await withStepUp(page, writeTo(/\/keys$/, 'POST'), () => form.getByRole('button', { name: 'Issue key' }).click());
  const { id } = (await created.json()) as { id: string };
  const panel = page.locator('[data-new-key]');
  const plainKey = ((await panel.locator('[data-plain-key]').textContent()) ?? '').trim();
  expect(plainKey, 'the entry showed a plain key').toMatch(/^cw_/);
  await panel.getByRole('button', { name: 'Done' }).click();
  await expect(panel).toHaveCount(0);
  return { id, plainKey };
}

/** Switches the entry's own half of tenant reach on, on its page. */
export async function enableEntryReach(page: Page, entryId: string): Promise<void> {
  await page.goto(`/admin/agents/access/${entryId}`);
  const toggle = page.locator('[data-entry-reach]').getByRole('checkbox', { name: /^Reads our register decisions/ });
  await expect(toggle).toBeEnabled();
  // The box follows the server's answer, so it is clicked rather than checked.
  await withStepUp(page, writeTo(/\/tenant-reach$/, 'PUT'), () => toggle.click());
  await expect(toggle).toBeChecked();
}

/** Revokes the entry on its page, if it is still active; safe from a teardown. */
export async function revokeEntry(page: Page, entryId: string): Promise<void> {
  await page.goto(`/admin/agents/access/${entryId}`);
  // The entry's own Revoke heads the page; each live key has one of its own further down.
  const revoke = page.getByRole('button', { name: 'Revoke', exact: true }).first();
  await expect(revoke.or(page.locator('[data-entry-revoked]')).first()).toBeVisible();
  if (!(await revoke.isVisible())) return;
  await revoke.click();
  await withStepUp(page, writeTo(/\/revoke$/, 'POST'), () => page.getByRole('button', { name: 'Revoke the agent' }).click());
  await expect(page.getByText('Revoked. Its credentials stopped working.', { exact: true })).toBeVisible();
}

/** The organisation's half of tenant reach: `requester` asks on Security, `approver` approves. */
export async function switchTenantReachOn(requester: Page, approver: Page): Promise<void> {
  await requester.goto('/admin/security');
  const panel = requester.locator('[data-tenant-reach]');
  await expect(panel).toHaveAttribute('data-tenant-reach', /^(on|off|pending)$/);
  if ((await panel.getAttribute('data-tenant-reach')) === 'off') {
    await withStepUp(requester, writeTo(/\/tenant\/reach\/requests$/, 'POST'), () => panel.getByRole('button', { name: 'Ask to switch it on' }).click());
  }
  await approver.goto('/admin/security');
  const other = approver.locator('[data-tenant-reach]');
  await expect(other).toHaveAttribute('data-tenant-reach', /^(on|pending)$/);
  if ((await other.getAttribute('data-tenant-reach')) === 'pending') {
    await withStepUp(approver, writeTo(/\/approve$/, 'POST'), () => other.getByRole('button', { name: 'Approve with passkey' }).click());
  }
  await expect(other).toHaveAttribute('data-tenant-reach', 'on');
}

/** Switches the organisation's tenant reach off on Security if it is on; safe from a teardown. */
export async function switchTenantReachOff(page: Page): Promise<void> {
  await page.goto('/admin/security');
  const panel = page.locator('[data-tenant-reach]');
  await expect(panel).toHaveAttribute('data-tenant-reach', /^(on|off|pending)$/);
  if ((await panel.getAttribute('data-tenant-reach')) !== 'on') return;
  await panel.getByRole('button', { name: 'Switch off' }).click();
  await withStepUp(page, writeTo(/\/tenant\/reach\/off$/, 'POST'), () => page.getByRole('dialog').getByRole('button', { name: 'Switch off' }).click());
  await expect(panel).toHaveAttribute('data-tenant-reach', 'off');
}

/** No entry of tenant A reaches the register any more (`manage.py e2e_reach_off`), for a teardown. */
export function entriesReachOff(): void {
  // Forward slashes: bash opens the script by this path, and a Windows checkout hands path.join backslashes.
  const script = path.join(test.info().project.testDir, 'support', 'start-backend.sh').split(path.sep).join('/');
  execFileSync('bash', [script, 'manage', 'e2e_reach_off'], { encoding: 'utf8' });
}

/** The agent: the REST API and its key, nothing else. */
export async function agentWith(playwright: PlaywrightWorkerArgs['playwright'], plainKey: string): Promise<APIRequestContext> {
  return playwright.request.newContext({ baseURL: BACKEND_URL, extraHTTPHeaders: { 'X-API-Key': plainKey } });
}
