import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// The shell smoke (@smoke): the app boots under `next start`, a person signs
// in with a passkey, the wordmark has its accessible name, and Today renders.
// Since chunk 1 every tenant screen sits behind the session gate, so this spec
// needs the real backend.
//
// It asserts the shell, never Today's contents: the empty state it used to look
// for disappeared the moment chunk 6 gave Today real panels and the seed gave
// the bank real changes (2026-09-21). What Today shows belongs to HOM-S1 in
// home.journey.spec.ts, which seeds what it asserts.

test.describe('app shell', () => {
  test('loads Today with the wordmark and the navigation @smoke', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('img', { name: 'bleqq, pronounced blek' }).first()).toBeVisible();
    await expect(page.getByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeVisible();
    await expect(page.locator('#main')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' }).first()).toBeVisible();
  });

  // At / an anonymous visitor lands on the public page instead
  // (public.journey.spec.ts); every other gated address still sends them here.
  test('an anonymous visitor on a gated address is sent to sign in', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await page.goto('/watch');
    await expect(page).toHaveURL(/\/sign-in$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in with a passkey' })).toBeVisible();
  });
});
