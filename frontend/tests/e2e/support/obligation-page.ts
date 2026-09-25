import { expect, type Browser, type Page } from '@playwright/test';

import type { ApiGuard } from './api-guard';
import { allowFreshContext, signInAs } from './passkeys';

// The obligation page for the register panel journeys (REG-S7, REG-S8,
// COL-S6, COL-S7). Library titles are rows, not catalog copy, so a card is
// found by its stable key: the inventory row's link carries the id.

/** The seed's anchor date, which the inventory list is read as of (library.journey.spec.ts). */
const AS_OF = '2026-09-16';

export async function openObligation(page: Page, stableKey: string): Promise<void> {
  await page.goto(`/inventory?asOf=${AS_OF}`);
  await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
  await page.locator(`[data-obligation="${stableKey}"]`).click();
  await expect(page.locator(`[data-obligation="${stableKey}"] [data-header-pills]`)).toBeVisible();
}

/**
 * The participants panel reads the owners from the register entry, whose read
 * answers 501 `not_built` until its own package lands (register/status_logic.py);
 * the panel stands without them. Declared here, where every panel journey opens
 * the page.
 */
export function allowRegisterEntryPending(apiGuard: ApiGuard): void {
  apiGuard.allow(/\/api\/v1\/obligations\/[^/]+\/register$/, 501, 'the register entry read lands with its own package; the owners wait for it');
}

/** A second person in a browser context of their own, held to the same guard. */
export async function signInElsewhere(browser: Browser, baseURL: string | undefined, apiGuard: ApiGuard, login: string): Promise<Page> {
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();
  allowFreshContext(apiGuard);
  apiGuard.watch(page);
  await signInAs(page, login);
  return page;
}
