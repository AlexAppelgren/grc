import type { Page } from '@playwright/test';

import { expect } from './api-guard';

// Helpers for c5-e2e-vocab-footprint-feed (VOC-S15's watch steps, the footprint
// recompute block). Kept apart from support/watch-coverage.ts and
// support/watch-facts.ts so no helper file has two owners (chunk 5 plan rule 5).

/** The console queue has settled when its rows or its empty state is on screen. */
export async function queueSettled(page: Page): Promise<void> {
  await expect(page.locator('[data-proposal-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
}

/**
 * Approves a vocabulary proposal from the console queue by its auto-generated title
 * (`apps/taxonomy/library_lists_logic.py`: "Add X to flag", "Change x on flag", "Merge x
 * into y on flag"), through the global step-up dialog. A vocabulary kind offers a plain
 * Approve, never the obligation-version correction form (`ProposalDetailScreen.tsx`).
 */
export async function approveQueueProposal(page: Page, titleFragment: RegExp): Promise<void> {
  await page.goto('/console/queue');
  await queueSettled(page);
  await page.getByRole('link', { name: titleFragment }).click();
  await expect(page.getByRole('heading', { level: 1, name: titleFragment })).toBeVisible();

  const applied = page.locator('[data-proposal-applied]');
  const approve = page.getByRole('button', { name: 'Approve and apply' });
  await expect(applied.or(approve).first()).toBeVisible();
  if (await approve.isVisible()) {
    await approve.click();
    const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
    await expect(prompt.or(applied).first()).toBeVisible();
    if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  }
  await expect(applied).toBeVisible();
}
