import { expect, test } from './support/api-guard';

// Phase 0 shell smoke (@smoke): the app boots under `next start`, the
// wordmark has its accessible name, and Today shows its empty state. No API
// call is made yet, so this spec does not depend on the backend.

test.describe('app shell', () => {
  test('loads Today with the wordmark and the empty state @smoke', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('img', { name: 'bleqq, pronounced blek' }).first()).toBeVisible();
    await expect(page.getByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeVisible();
    await expect(page.getByText('Nothing to show yet')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Set the footprint under Admin' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' }).first()).toBeVisible();
  });
});
