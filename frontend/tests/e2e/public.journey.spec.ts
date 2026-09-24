import { expect, test } from './support/api-guard';
import { allowFreshContext, BACKEND_URL, LOGINS, signInAs, signOut } from './support/passkeys';

const PLATE = 'A register of record for everything regulation asks of your bank.';

// The public page (design/public/): what a visitor who is not signed in sees at
// the front door, and the way from it into the passkey sign-in flow. The page
// itself calls no API; the fresh-context allowance covers the session check at
// / and on /sign-in.

test.describe('public page', () => {
  test('an anonymous visitor at / lands on the public page', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await page.goto('/');
    await expect(page).toHaveURL(/\/welcome$/);
    await expect(page.getByRole('heading', { level: 1, name: PLATE })).toBeVisible();
    await expect(page.getByRole('img', { name: 'bleqq, pronounced blek' }).first()).toBeVisible();
  });

  test('the sign-in page has a way back to the public page', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await page.goto('/sign-in');
    await page.getByRole('link', { name: '← Back' }).click();
    await expect(page).toHaveURL(/\/welcome$/);
    await expect(page.getByRole('heading', { level: 1, name: PLATE })).toBeVisible();
  });

  test('signing out lands on the public page and kills the session on the server', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    // The refresh cookie is scoped to the auth routes (REFRESH_COOKIE_PATH).
    const authUrl = `${BACKEND_URL}/api/v1/auth/refresh`;
    const refresh = (await page.context().cookies(authUrl)).find((cookie) => cookie.name === 'cw_refresh');
    expect(refresh, 'the refresh cookie a signed-in browser holds').toBeDefined();

    await signOut(page);
    await expect(page).toHaveURL(/\/welcome$/);

    // The browser no longer holds the cookie, and a copy taken before sign-out
    // is dead too: the session row is revoked, and every access token checks it.
    expect((await page.context().cookies(authUrl)).some((cookie) => cookie.name === 'cw_refresh')).toBe(false);
    const replay = await page.request.post(authUrl, { headers: { Cookie: `cw_refresh=${refresh?.value ?? ''}` } });
    expect(replay.status()).toBe(401);

    // Back at the front door nothing signs the person in again.
    await page.goto('/');
    await expect(page).toHaveURL(/\/welcome$/);
    await expect(page.getByRole('navigation', { name: 'Main' })).toHaveCount(0);
  });

  test('Sign in in the top bar opens the passkey sign-in flow', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await page.goto('/welcome');
    await page.getByRole('banner').getByRole('link', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/sign-in$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in with a passkey' })).toBeVisible();
  });

  test('on a 320 px phone the top bar keeps both actions on one row and stays on screen', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await page.setViewportSize({ width: 320, height: 700 });
    await page.goto('/welcome');
    const bar = page.getByRole('banner');
    const requestAccess = bar.getByRole('link', { name: 'Request access' });
    const signIn = bar.getByRole('link', { name: 'Sign in' });
    await expect(signIn).toBeVisible();
    await expect(requestAccess).toBeVisible();
    const secondary = await requestAccess.boundingBox();
    const primary = await signIn.boundingBox();
    expect(secondary).not.toBeNull();
    expect(primary).not.toBeNull();
    expect(Math.abs((secondary?.y ?? 0) - (primary?.y ?? 0))).toBeLessThan(2);
    expect(secondary?.x ?? 0).toBeLessThan(primary?.x ?? 0);
    await page.getByRole('contentinfo').scrollIntoViewIfNeeded();
    await expect(signIn).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  });

  test('Request access jumps to the invitation section, clear of the bar', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await page.goto('/welcome');
    await page.getByRole('banner').getByRole('link', { name: 'Request access' }).click();
    await expect(page).toHaveURL(/#request$/);
    await expect(page.getByRole('heading', { level: 2, name: 'Access is by invitation.' })).toBeInViewport();
    const barHeight = (await page.getByRole('banner').boundingBox())?.height ?? 0;
    const sectionTop = await page.locator('#request').evaluate((section) => section.getBoundingClientRect().top);
    expect(sectionTop).toBeGreaterThanOrEqual(barHeight);
  });

  test('the footer switches the page to the dark theme', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await page.goto('/welcome');
    const footer = page.getByRole('contentinfo');
    await footer.getByRole('button', { name: 'Dark theme' }).click();
    await expect(page.locator('html')).toHaveClass(/(^|\s)dark(\s|$)/);
    await expect(footer.getByRole('button', { name: 'Light theme' })).toBeVisible();
  });
});
