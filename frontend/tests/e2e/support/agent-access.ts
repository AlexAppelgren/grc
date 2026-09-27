import type { Locator, Page } from '@playwright/test';

import { expect, type ApiGuard } from './api-guard';

// A bank's own agent, set up the way its administrator does it (ACC-01, ACC-03):
// registered under Admin, Agents, Access, then given a key on its entry page,
// each write behind a passkey step-up. Journeys that need an agent access
// credential to call the real API (ACC-S3, ACC-S11) take it from here rather
// than from the seed, so the credential they read with is one the screens made.
//
// The plain key is returned to the caller and nowhere else: this helper never
// writes it to disk, attaches it to the report or logs it, and it closes the
// one-time panel before returning so no later screenshot carries it.

const ACCESS = '/admin/agents/access';

/**
 * Settles an action that may ask for a passkey: the session's step-up lasts a
 * few minutes, so only the first sensitive write of a journey opens the prompt.
 */
export async function confirmWithPasskey(page: Page, done: Locator): Promise<void> {
  const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
  await expect(prompt.or(done).first()).toBeVisible();
  if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  await expect(done).toBeVisible();
}

/** The step-up answers the entry and key writes give before the prompt opens. */
export function allowAgentAccessStepUps(apiGuard: ApiGuard): void {
  apiGuard.allow(/\/api\/v1\/agent-access(\/[^/]+(\/(tenant-reach|keys|revoke))?)?$/, 403, 'an agent access write answers step_up_required first and opens the prompt');
  // The register dialog's department and product pickers read the organisation routes,
  // which answer 501 not_built until their own package lands; the dialog says so and
  // saves an entry over the whole regulatory scope without them.
  apiGuard.allow(/\/api\/v1\/tenant\/(org-units|products)$/, 501, 'the organisation pickers read routes not built on this branch');
}

/** Registers an entry over the bank's whole regulatory scope and returns its id. */
export async function registerEntry(page: Page, name: string): Promise<string> {
  await page.goto(ACCESS);
  await page.getByRole('button', { name: 'Register an agent' }).click();
  const dialog = page.getByRole('dialog', { name: 'Register an agent' });
  await dialog.getByLabel('Name', { exact: true }).fill(name);
  await dialog.getByLabel('Purpose', { exact: true }).fill('Builds the order router and asks what applies to it.');
  const team = dialog.getByLabel('Owned by', { exact: true });
  await expect(team.locator('option')).not.toHaveCount(1);
  await team.selectOption({ index: 1 });
  const created = page.waitForResponse((r) => r.url().endsWith('/api/v1/agent-access') && r.request().method() === 'POST' && r.ok());
  await dialog.getByRole('button', { name: 'Register', exact: true }).click();
  await confirmWithPasskey(page, page.getByText('Registered. Issue it a key to let it read.'));
  return ((await (await created).json()) as { id: string }).id;
}

export async function openEntry(page: Page, entryId: string): Promise<void> {
  await page.goto(`${ACCESS}/${entryId}`);
  await expect(page.locator(`[data-entry="${entryId}"]`)).toBeVisible();
}

/** Switches the entry's own half of tenant reach on; the bank's half must already be on. */
export async function allowEntryReach(page: Page, entryId: string): Promise<void> {
  await openEntry(page, entryId);
  const toggle = page.locator('[data-entry-reach]').getByLabel('Reads our register decisions');
  await expect(toggle).toBeEnabled();
  // The box follows the server's answer, so it is clicked rather than checked.
  await toggle.click();
  await confirmWithPasskey(page, page.locator('[data-entry-reach] input[type="checkbox"]:checked'));
}

/** Issues a key on the entry and returns its plain value, shown once. */
export async function issueEntryKey(page: Page, entryId: string, request: { name: string; scopes: readonly string[] }): Promise<string> {
  await openEntry(page, entryId);
  await page.getByRole('button', { name: 'Issue a key' }).click();
  const form = page.locator('[data-issue-form]');
  await form.getByLabel('Name', { exact: true }).fill(request.name);
  for (const scope of request.scopes) {
    // A scope's label reads its key as words, then what it reads.
    await form.getByLabel(new RegExp(`^${scope.replace(/[._:-]/g, ' ')}`)).check();
  }
  await form.getByRole('button', { name: 'Issue key' }).click();
  const panel = page.locator('[data-new-key]');
  await confirmWithPasskey(page, panel);
  const plainKey = (await panel.locator('[data-plain-key]').textContent())?.trim() ?? '';
  expect(plainKey).toMatch(/^cw_/);
  await panel.getByRole('button', { name: 'Done' }).click();
  await expect(panel).toHaveCount(0);
  return plainKey;
}

/** Revokes the entry, which stops every key and token under it; a revoked one is left alone. */
export async function revokeEntry(page: Page, entryId: string): Promise<void> {
  await openEntry(page, entryId);
  if ((await page.locator('[data-entry-revoked]').count()) > 0) return;
  await page.getByRole('button', { name: 'Revoke', exact: true }).first().click();
  await page.getByRole('dialog').getByRole('button', { name: 'Revoke the agent' }).click();
  await confirmWithPasskey(page, page.locator('[data-entry-revoked]'));
}
