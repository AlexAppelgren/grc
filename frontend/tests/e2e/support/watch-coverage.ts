import type { Page } from '@playwright/test';

import { expect } from './api-guard';
import { seedPasskeyFor } from './passkeys';

// Helpers for c5-e2e-watch-journeys-a (WAT-S1, WAT-S2, WAT-S9): the coverage log, a
// change's timeline and a feed row's pill order. Kept apart from support/watch.ts and
// support/watch-facts.ts so no helper file has two owners (chunk 5 plan rule 5).
//
// The literal names below are seeded data (backend/apps/shared/e2e_seed.py,
// `EXPECTED_CHUNK5_WATCH`), not catalog copy, so they are matched as data rather than
// looked up by a translated label.
export const CHUNK5_WATCH = {
  timelineChange: 'chg-e2e-c5-timeline',
  obligationsChange: 'chg-e2e-c5-obligations',
  paymentsChange: 'chg-e2e-c5-payments',
  healthySource: 'EUR-Lex legal database (E2E)',
  failingSource: 'Open web sweep, payments (E2E)',
  failingSourceError: '502 from the publisher after three retries',
} as const;

/** The feed has settled when its rows or its empty state is on screen. */
export async function openWatchFeed(page: Page): Promise<void> {
  await page.goto('/watch');
  await expect(page.locator('[data-change-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
}

/** Opens a change's page from the feed, by the row carrying this stable key. */
export async function openChangeByStableKey(page: Page, stableKey: string): Promise<void> {
  await openWatchFeed(page);
  const row = page.locator(`[data-change="${stableKey}"]`);
  await row.click();
  await expect(page.locator(`[data-change="${stableKey}"]`)).toBeVisible();
}

/** A console Sources row, found by the source's name: `data-source-id` carries its id, which is not fixed. */
export function consoleSourceRow(page: Page, name: string) {
  return page.locator('[data-source-id]').filter({ has: page.getByRole('heading', { name, exact: true }) });
}

/**
 * The passkey ceremony `support/passkeys.ts`'s `signInAs()` runs, without its final wait:
 * that wait names the shell's "Main" navigation landmark literally, which is this reader's
 * own catalog copy everywhere else (playbook 8.3, one pinned language) — but the one
 * seeded login whose own `locale` is Swedish (WAT-S2's `LOGINS.readerSv`) renders the
 * shell in Swedish once signed in, where the same landmark is named "Huvudmeny". Proven to
 * fail 2026-09-21 against the real stack: `signInAs()` timed out on `getByRole('navigation',
 * { name: 'Main' })` although the Swedish shell, landmark included, was already on screen.
 * Waits for either name rather than widening the shared helper for its one caller.
 */
export async function signInAsSv(page: Page, login: string): Promise<void> {
  await seedPasskeyFor(page.context(), login);
  await page.goto('/sign-in');
  await page.getByRole('button', { name: 'Sign in with a passkey' }).click();
  await expect(page.getByRole('navigation', { name: 'Main' }).or(page.getByRole('navigation', { name: 'Huvudmeny' })).first()).toBeVisible({
    timeout: 15_000,
  });
}
