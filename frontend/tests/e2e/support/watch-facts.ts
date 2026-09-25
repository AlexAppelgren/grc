import type { Page } from '@playwright/test';

import { expect } from './api-guard';

// Helpers for the journeys that read a change page whole and settle a change for one bank
// on its own case (WAT-S6's bank half, WAT-S7). Kept apart from support/watch.ts and
// support/watch-coverage.ts so no helper file has two owners (chunk 5 plan rule 5).

/**
 * Opens a change's page from the feed by the row carrying this stable key, and answers the
 * change's id. The feed is read with "Show outside our scope", because whether the change is
 * in this bank's scope is not what these journeys prove. The id is the address another
 * bank's reader is sent to: a change is one library row every bank reads by the same id,
 * while each bank's case for it is its own.
 */
export async function openChangeFromFeed(page: Page, stableKey: string): Promise<string> {
  await page.goto('/watch?scope=all');
  await page.locator(`a[data-change="${stableKey}"]`).click();
  await expect(page).toHaveURL(/\/watch\/[0-9a-f-]{36}$/);
  // The row carries the same data-change, so the page has settled only once a panel the
  // feed never shows is on screen.
  await expect(page.locator('[data-change-classification]')).toBeVisible();
  return new URL(page.url()).pathname.split('/').at(-1) ?? '';
}
