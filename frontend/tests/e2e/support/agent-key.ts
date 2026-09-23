import type { Page } from '@playwright/test';

import { expect, type ApiGuard } from './api-guard';
import { allowFreshContext, LOGINS, signInAs } from './passkeys';

// Minting a platform agent key the way a platform administrator does it (ID-10,
// AGT-01): signed in as agent-keys@bleqq.test, through /console/agent-keys, its
// agent select and its passkey step-up. Journeys that need an agent to call the
// real API (J-4, PRO-S13) take their key from here rather than from the seed, so
// the key they run on is one the console really made.
//
// The plain key is returned to the caller and nowhere else: this helper never
// writes it to disk, attaches it to the report or logs it, and it closes the
// one-time panel before returning so no later screenshot carries it.

export interface MintedAgentKey {
  /** The key's id, for revoking it in the journey's teardown. */
  id: string;
  /** The plain key, shown once. Hold it in memory only. */
  plainKey: string;
}

export interface AgentKeyRequest {
  /** The name the key is listed under; make it unique to the journey. */
  name: string;
  /** The agent definition's stable key, such as `watch-sweeper`. */
  agent: string;
  /** Scope keys, such as `agent-runs:write`. */
  scopes: readonly string[];
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Signs `page` in as the agent-keys login and mints one key; `page` should be a fresh context. */
export async function mintAgentKey(page: Page, apiGuard: ApiGuard, request: AgentKeyRequest): Promise<MintedAgentKey> {
  allowFreshContext(apiGuard);
  apiGuard.allow(/\/api\/v1\/agent-keys$/, 403, 'creating a key answers step_up_required first and opens the prompt');
  await signInAs(page, LOGINS.agentKeys);
  await page.goto('/console/agent-keys');
  await page.getByRole('button', { name: 'Create a key' }).click();

  const form = page.locator('[data-agent-key-form]');
  await form.getByLabel('Name', { exact: true }).fill(request.name);
  const agent = form.getByRole('combobox', { name: 'Agent' });
  const option = agent.locator('option', { hasText: new RegExp(`^${escape(request.agent)} v\\d+$`) });
  await expect(option).toHaveCount(1);
  await agent.selectOption((await option.getAttribute('value')) ?? '');
  for (const scope of request.scopes) {
    await form.getByLabel(scope.replace(/[._:-]/g, ' '), { exact: true }).check();
  }

  const created = page.waitForResponse((r) => r.url().endsWith('/api/v1/agent-keys') && r.request().method() === 'POST' && r.ok());
  await form.getByRole('button', { name: 'Create the key' }).click();
  const panel = page.locator('[data-new-key]');
  const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
  await expect(prompt.or(panel).first()).toBeVisible();
  if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  const { id } = (await (await created).json()) as { id: string };

  const plainKey = ((await panel.locator('[data-plain-key]').textContent()) ?? '').trim();
  expect(plainKey, 'the console showed a plain key').toMatch(/^cw_/);
  await panel.getByRole('button', { name: 'Done' }).click();
  await expect(panel).toHaveCount(0);
  return { id, plainKey };
}

/** Revokes the key on /console/agent-keys if it is still live; safe to call from a teardown. */
export async function revokeAgentKey(page: Page, id: string): Promise<void> {
  await page.goto('/console/agent-keys');
  const row = page.locator(`[data-agent-key-id="${id}"]`);
  await expect(row).toBeVisible();
  if ((await row.getByRole('button', { name: 'Revoke' }).count()) === 0) return;
  await row.getByRole('button', { name: 'Revoke' }).click();
  await row.getByRole('button', { name: 'Revoke the key' }).click();
  await expect(row).toContainText('Revoked');
}
