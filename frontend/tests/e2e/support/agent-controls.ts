import type { Locator, Page } from '@playwright/test';

import { expect } from './api-guard';

// A bank's controls over its own agent on /admin/agents (AGT-S5, AGT-S6), driven
// through the screen the way an admin drives them, and the teardown that puts
// tenant A's seeded agent and cap back (backend/apps/shared/e2e_seed.py,
// EXPECTED_CHUNK11) whatever state a failed journey left them in.

/** Tenant A's own agent and its seeded state. */
export const SEEDED_AGENT = 'tenant-source-watch';
export const SEEDED_CAP = '7.00';
/** Tenant A's markets as the screen offers them: operating first, then watched. */
export const SEEDED_MARKETS = ['Sweden', 'Denmark'] as const;

export function agentCard(page: Page): Locator {
  return page.locator(`[data-agent-key="${SEEDED_AGENT}"]`);
}

/** Open the agents screen and settle on the seeded agent's card. */
export async function openAgents(page: Page): Promise<Locator> {
  await page.goto('/admin/agents');
  const card = agentCard(page);
  await expect(card).toBeVisible();
  return card;
}

/** "Set cap" with `amount` euro, settled on the confirmation. */
export async function setCap(page: Page, amount: string): Promise<void> {
  const form = page.locator('[data-cap-form]');
  await form.getByLabel('Monthly cap in euro').fill(amount);
  await form.getByRole('button', { name: 'Set cap' }).click();
  await expect(form.getByText('Cap set.')).toBeVisible();
}

/** "Change when and what": pick a cadence and exactly the markets named, then save. */
export async function changeSchedule(card: Locator, cadence: string, markets: readonly string[]): Promise<void> {
  await card.getByRole('button', { name: 'Change when and what' }).click();
  const form = card.locator('[data-schedule-form]');
  await form.getByLabel('Runs').selectOption({ label: cadence });
  for (const market of SEEDED_MARKETS) {
    await form.getByRole('checkbox', { name: new RegExp(`^${market}`) }).setChecked(markets.includes(market));
  }
  await form.getByRole('button', { name: 'Save' }).click();
}

/** Put tenant A's agent and cap back as seeded: no run left open, on, not paused,
 * weekly over both markets, and the seeded cap. Safe to call from any state. */
export async function restoreSeededAgent(page: Page): Promise<void> {
  const card = await openAgents(page);
  await expect(card.locator('[data-run-id]').first()).toBeVisible();
  const stop = card.getByRole('button', { name: 'Stop run' });
  if (await stop.isVisible()) {
    await stop.click();
    await card.getByRole('button', { name: 'Stop the run' }).click();
    await expect(card.getByText('Stopped. The run shows as stopped under Recent runs.')).toBeVisible();
  }
  const switchOn = card.getByRole('button', { name: 'Switch on' });
  if (await switchOn.isVisible()) {
    await switchOn.click();
    await expect(card.getByText('Switched on.')).toBeVisible();
  }
  const resume = card.getByRole('button', { name: 'Resume' });
  if (await resume.isVisible()) {
    await resume.click();
    await expect(card.getByText('Resumed.')).toBeVisible();
  }
  await changeSchedule(card, 'Weekly', SEEDED_MARKETS);
  await expect(card.getByText('Saved.')).toBeVisible();
  await setCap(page, SEEDED_CAP);
}

/** The bank's AI switch on /admin/organisation, through the passkey prompt it opens. */
export async function setBankAi(page: Page, enabled: boolean): Promise<void> {
  await page.goto('/admin/organisation');
  const panel = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Ask and AI drafts' }) });
  const target = enabled ? 'Switch on' : 'Switch off';
  const already = enabled ? 'Switch off' : 'Switch on';
  await expect(panel.getByRole('button', { name: target }).or(panel.getByRole('button', { name: already })).first()).toBeVisible();
  if (await panel.getByRole('button', { name: already }).isVisible()) return;
  await panel.getByRole('button', { name: target }).click();
  await expect(panel.getByRole('button', { name: already })).toBeVisible();
}
