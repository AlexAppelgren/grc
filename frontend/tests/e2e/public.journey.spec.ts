import type { APIRequestContext, APIResponse } from '@playwright/test';

import { DEMO_FRAME_NAME } from '@/features/demo/frame';

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

  test('no other site can frame the app, while its own public page frames the demo', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    const response = await page.goto('/welcome');
    expect(response?.headers()['content-security-policy']).toBe("frame-ancestors 'self'");
    expect(response?.headers()['x-frame-options']).toBe('SAMEORIGIN');
    const app = page.url();

    // A page on another origin frames it: the browser puts its own error page in the frame instead.
    await page.goto(`data:text/html,<iframe name="elsewhere" src="${app}"></iframe>`);
    await expect.poll(() => page.frame({ name: 'elsewhere' })?.url()).toMatch(/^chrome-error:/);
  });
});

// What a bank's web filter checks before it trusts the site (docs/runbooks/DNS_DOMAINS.md
// "Site trust"): an address that is not there says so with its status, crawlers may read the
// public page and nothing else, security.txt names a contact, and every page sends the
// security headers.
test.describe('site trust', () => {
  const HEADERS = {
    'content-security-policy': "frame-ancestors 'self'",
    'x-frame-options': 'SAMEORIGIN',
    'strict-transport-security': 'max-age=31536000',
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'strict-origin-when-cross-origin',
    'permissions-policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
  };

  test('an address no route serves answers 404, and the pages that exist answer 200', async ({ request }) => {
    for (const path of ['/this-page-does-not-exist-9x', '/inventory/not-a-screen/deeper', '/console/not-a-screen']) {
      expect((await request.get(path)).status(), path).toBe(404);
    }
    for (const path of ['/', '/welcome', '/sign-in', '/admin/audit-log', '/me/passkeys']) {
      expect((await request.get(path)).status(), path).toBe(200);
    }
  });

  test('a signed-in person at an unknown address keeps the shell and is told it is not there', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    const response = await page.goto('/this-page-does-not-exist-9x');
    expect(response?.status()).toBe(404);
    await expect(page.locator('[data-not-found]')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
  });

  test('an anonymous visitor at an unknown address gets a 404 and goes on to the public page', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    const response = await page.goto('/inventory/not-a-screen/deeper');
    expect(response?.status()).toBe(404);
    await expect(page).toHaveURL(/\/welcome$/);
    await expect(page.getByRole('heading', { level: 1, name: PLATE })).toBeVisible();
  });

  test('security.txt names a contact, an expiry still ahead and its own address (RFC 9116)', async ({ request }) => {
    const response = await request.get('/.well-known/security.txt');
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toMatch(/^text\/plain; charset=utf-8$/i);
    const fields = Object.fromEntries(
      (await response.text()).trim().split('\n').map((line) => [line.slice(0, line.indexOf(':')), line.slice(line.indexOf(':') + 1).trim()]),
    );
    expect(fields.Contact).toMatch(/^mailto:[^@\s]+@bleqq\.com$/);
    expect(Date.parse(fields.Expires ?? '')).toBeGreaterThan(Date.now());
    expect(fields['Preferred-Languages']).toBe('en, sv');
    expect(fields.Canonical).toBe('https://bleqq.com/.well-known/security.txt');
  });

  test('crawlers may read the public page and its sitemap, and nothing of the app', async ({ page, apiGuard, request }) => {
    allowFreshContext(apiGuard);
    const robots = await (await request.get('/robots.txt')).text();
    expect(robots).toMatch(/^Allow: \/\$$/m);
    expect(robots).toMatch(/^Allow: \/welcome$/m);
    expect(robots).toMatch(/^Disallow: \/$/m);
    expect(robots).toMatch(/^Sitemap: https:\/\/bleqq\.com\/sitemap\.xml$/m);

    const sitemap = await request.get('/sitemap.xml');
    expect(sitemap.status()).toBe(200);
    expect([...(await sitemap.text()).matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1])).toEqual(['https://bleqq.com/welcome']);

    // The public page may be indexed; the app's pages may not.
    await page.goto('/welcome');
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'index, follow');
    await page.goto('/sign-in');
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, nofollow');
  });

  test('every page sends the security headers, and a passkey still signs in', async ({ page, apiGuard, request }) => {
    for (const path of ['/welcome', '/admin/audit-log', '/this-page-does-not-exist-9x', '/.well-known/security.txt']) {
      const headers = (await request.get(path)).headers();
      for (const [name, value] of Object.entries(HEADERS)) expect(headers[name], `${name} on ${path}`).toBe(value);
    }
    // The policy leaves WebAuthn at its default, our own origin, so the ceremony runs.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
  });
});

// The public site and the app on hosts of their own (src/proxy.ts,
// docs/runbooks/DNS_DOMAINS.md): a second server of the same build runs with
// PUBLIC_SITE_HOST and APP_HOST set (support/split-hosts.mjs). The app host is
// localhost, so it shares a site with the API and the passkeys' RP ID as the
// deployed app and API hosts do; the public host is public.localhost.
test.describe('the public site and the app on hosts of their own', () => {
  const APP = process.env.E2E_SPLIT_APP_URL ?? 'http://localhost:3001';
  const PUBLIC = process.env.E2E_SPLIT_PUBLIC_URL ?? 'http://public.localhost:3001';
  test.use({ baseURL: APP });

  // What a crawler or a web filter sends: no JavaScript and no Sec-Fetch headers.
  // Node does not resolve public.localhost, so the request names its host in the
  // Host header, which is all a request to the real host carries.
  function crawl(request: APIRequestContext, url: string): Promise<APIResponse> {
    const { host, pathname, search } = new URL(url);
    return request.get(`${APP}${pathname}${search}`, { headers: { Host: host }, maxRedirects: 0 });
  }

  test('a crawler reads the whole public page at / on the public host, and everything else moves to the app host', async ({ request }) => {
    const home = await crawl(request, `${PUBLIC}/`);
    expect(home.status()).toBe(200);
    const html = await home.text();
    expect(html).toContain(PLATE);
    expect(html).toMatch(/<meta name="robots" content="index, follow"/);
    expect(home.headers()['x-robots-tag']).toBeUndefined();

    const welcome = await crawl(request, `${PUBLIC}/welcome?from=a`);
    expect(welcome.status()).toBe(301);
    expect(welcome.headers().location).toBe(`${PUBLIC}/?from=a`);

    for (const path of ['/sign-in', '/enrol', '/invite', '/inventory', '/admin/audit-log', '/console/queue', '/api/v1/auth/session', '/not-a-page']) {
      const moved = await crawl(request, `${PUBLIC}${path}`);
      expect(moved.status(), path).toBe(301);
      expect(moved.headers().location, path).toBe(`${APP}${path}`);
    }

    // The public files stay; the sitemap lists the public host's front door.
    for (const path of ['/robots.txt', '/.well-known/security.txt']) expect((await crawl(request, `${PUBLIC}${path}`)).status(), path).toBe(200);
    const sitemap = await (await crawl(request, `${PUBLIC}/sitemap.xml`)).text();
    expect([...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1])).toEqual([`https://${new URL(PUBLIC).host}/`]);
  });

  test('the app host keeps the app, marks every page noindex, and sends the public page to the public host', async ({ request }) => {
    for (const path of ['/', '/sign-in', '/enrol', '/inventory']) {
      const response = await request.get(path, { maxRedirects: 0 });
      expect(response.status(), path).toBe(200);
      expect(response.headers()['x-robots-tag'], path).toBe('noindex');
    }
    const welcome = await request.get('/welcome', { maxRedirects: 0 });
    expect(welcome.status()).toBe(301);
    expect(welcome.headers().location).toBe(`${PUBLIC}/`);
  });

  test('the sign-in and enrolment pages say what the service is and who runs it before any script runs', async ({ browser }) => {
    const context = await browser.newContext({ baseURL: APP, javaScriptEnabled: false });
    const page = await context.newPage();
    for (const path of ['/sign-in', '/enrol']) {
      await page.goto(path);
      const about = page.getByRole('contentinfo', { name: 'About this service' });
      await expect(about.getByText(/keeps a bank's regulatory obligations in one inventory/)).toBeVisible();
      await expect(about.getByRole('link', { name: 'bleqq', exact: true })).toHaveAttribute('href', '/welcome');
      await expect(about.getByRole('link', { name: 'privacy@bleqq.com' })).toBeVisible();
      await expect(about.getByRole('link', { name: 'security@bleqq.com' })).toBeVisible();
    }
    await expect(page.getByRole('heading', { level: 1, name: 'Enter your code' })).toBeVisible();
    await page.goto('/sign-in');
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();

    // Without JavaScript the public host still shows the whole public page at /.
    await page.goto(`${PUBLIC}/`);
    await expect(page).toHaveURL(`${PUBLIC}/`);
    await expect(page.getByRole('heading', { level: 1, name: PLATE })).toBeVisible();
    await context.close();
  });

  test('a visitor goes from the public host to sign in on the app host, and back', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await page.goto(`${PUBLIC}/`);
    await expect(page.getByRole('heading', { level: 1, name: PLATE })).toBeVisible();
    await page.getByRole('banner').getByRole('link', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(`${APP}/sign-in`);
    await expect(page.getByRole('button', { name: 'Sign in with a passkey' })).toBeVisible();

    // The company name and the back link both lead to the public host.
    await page.getByRole('contentinfo', { name: 'About this service' }).getByRole('link', { name: 'bleqq', exact: true }).click();
    await expect(page).toHaveURL(`${PUBLIC}/`);
    await page.goto('/sign-in');
    await page.getByRole('link', { name: '← Back' }).click();
    await expect(page).toHaveURL(`${PUBLIC}/`);
    await expect(page.getByRole('heading', { level: 1, name: PLATE })).toBeVisible();

    // Without a session the app host's front door goes on to the public host, as it goes to /welcome today.
    await page.goto('/');
    await expect(page).toHaveURL(`${PUBLIC}/`);
    await expect(page.getByRole('heading', { level: 1, name: PLATE })).toBeVisible();
  });

  test('a passkey signs in on the app host', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    expect(new URL(page.url()).origin).toBe(APP);
    await page.reload();
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
  });

  test('the demo runs the app in its frame on the public host', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    const frameLoad = page.waitForResponse((response) => response.frame().name() === DEMO_FRAME_NAME && new URL(response.url()).pathname === '/');
    const pageLoad = await page.goto(`${PUBLIC}/`);
    // The page and the frame get different answers at one address, so neither may sit in a shared cache.
    expect(pageLoad?.headers()['cache-control']).toBe('private, no-cache');
    expect((await frameLoad).headers()['cache-control']).toBe('private, no-cache');
    const app = page.frameLocator(`iframe[name="${DEMO_FRAME_NAME}"]`);
    await app.getByRole('link', { name: 'Watch', exact: true }).first().click();
    await expect(app.getByRole('tab', { selected: true })).toBeVisible();
    expect(new URL(page.frame({ name: DEMO_FRAME_NAME })?.url() ?? 'http://x/none').origin).toBe(PUBLIC);
  });
});
