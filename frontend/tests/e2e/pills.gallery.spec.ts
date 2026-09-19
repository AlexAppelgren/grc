import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';

// Pins the pill gallery in both themes (playbook 6.7, 9: "the design's
// tones, slots and labels drifting, in either theme"). The gallery renders a
// light column and a dark column with their own theme classes, so ONE
// baseline covers both themes. The second test loads the page under a dark
// system theme and compares it to the SAME baseline: that is the proof that
// the columns do not follow the visitor's theme. Two separate baselines were
// byte-identical (2026-09-19), which is a control that reports green while
// proving nothing; comparing to one baseline makes the equality the assertion.

async function settled(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
}

test.describe('pill gallery', () => {
  test('renders every tone and slot, light system theme', async ({ page }) => {
    await page.goto('/dev/pills');
    await expect(page.locator('[data-theme-column="light"]')).toBeVisible();
    await expect(page.locator('[data-theme-column="dark"]')).toBeVisible();
    await expect(page.locator('[data-pill]').first()).toBeVisible();
    await settled(page);
    await expect(page).toHaveScreenshot('pills-gallery.png', { fullPage: true });
  });

  test('renders every tone and slot, dark system theme', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.goto('/dev/pills');
    await expect(page.locator('[data-pill]').first()).toBeVisible();
    await settled(page);
    await expect(page).toHaveScreenshot('pills-gallery.png', { fullPage: true });
  });
});
