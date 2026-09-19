import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// The shell smoke (@smoke): the app boots under `next start`, a person signs
// in with a passkey, the wordmark has its accessible name, and Today shows
// its empty state. Since chunk 1 every tenant screen sits behind the session
// gate, so this spec needs the real backend.

test.describe('app shell', () => {
  test('loads Today with the wordmark and the empty state @smoke', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('img', { name: 'bleqq, pronounced blek' }).first()).toBeVisible();
    await expect(page.getByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeVisible();
    await expect(page.getByText('Nothing to show yet')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Set the footprint under Admin' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' }).first()).toBeVisible();
  });

  test('an anonymous visitor is sent to sign in', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in with a passkey' })).toBeVisible();
  });
});
