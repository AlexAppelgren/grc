import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page, Response } from '@playwright/test';

import { DEMO_FRAME_NAME } from '@/features/demo/frame';
import { type DemoRecording, type DemoRecordings, requestKey, staleness } from '@/features/demo/recordings';
import { destinations } from '@/shared/navigation/registry';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// The public page's demo is the real app answered from recordings
// (src/features/demo). This journey makes those recordings on the real stack:
// it signs in as the demo person and walks every screen the navigation offers,
// following the records each screen links to, and keeps what the backend
// answered. `npm run demo:record` writes them; every other run compares a
// fresh walk with the committed recordings and fails when a screen asks for
// something they cannot answer, or an answer has changed shape.

const RECORDINGS = fileURLToPath(new URL('../../src/features/demo/recordings.json', import.meta.url));
const RECORDED_AT = fileURLToPath(new URL('../../src/features/demo/recorded-at.json', import.meta.url));
const OPENAPI = fileURLToPath(new URL('../../../openapi.json', import.meta.url));
const TENANT_APP = fileURLToPath(new URL('../../src/app/(tenant)', import.meta.url));

const RECORD = process.env.DEMO_RECORD === '1';
// Recording keeps every record a list shows on its first page (the API pages by
// 20); the comparison needs one of each kind.
const PER_ROUTE = RECORD ? 20 : 1;

// The demo person reads everything and changes nothing.
const DEMO_LOGIN = LOGINS.reader;

// Every tenant screen in the navigation except administration and the person's own settings.
const SCREENS = destinations.filter((d) => d.surface === 'tenant' && d.group !== 'admin' && d.group !== 'account').map((d) => d.href);

// Grants that open only administration, which the demo leaves out: the demo
// person's /me is recorded without them, so the app's own rules hide Admin.
const ADMIN_ONLY = new Set(destinations.filter((d) => d.group === 'admin').flatMap((d) => d.anyOfPermissions));
const NON_ADMIN = new Set(destinations.filter((d) => d.group !== 'admin').flatMap((d) => d.anyOfPermissions));
// The seed marks fixtures the journeys look for by name; a visitor sees the name alone.
const FIXTURE_MARK = / \(E2E\)/g;

function forVisitors(value: unknown): unknown {
  if (typeof value === 'string') return value.replace(FIXTURE_MARK, '');
  if (Array.isArray(value)) return value.map(forVisitors);
  if (value !== null && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([field, inner]) => [field, forVisitors(inner)]));
  return value;
}

function recordedBody(key: string, body: unknown): unknown {
  const shown = forVisitors(body);
  if (key !== 'GET /api/v1/me' || shown === null || typeof shown !== 'object') return shown;
  const me = shown as { permissions?: string[] };
  return { ...me, permissions: (me.permissions ?? []).filter((permission) => !ADMIN_ONLY.has(permission) || NON_ADMIN.has(permission)) };
}

function onAScreen(path: string): boolean {
  return path === '/' || SCREENS.some((href) => href !== '/' && (path === href || path.startsWith(`${href}/`)));
}

/** The app's page routes, `/watch/[changeId]` style, read from the route folders. */
function pageRoutes(dir: string, prefix = ''): string[] {
  const routes: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isFile() && entry.name === 'page.tsx') routes.push(prefix === '' ? '/' : prefix);
    if (entry.isDirectory()) routes.push(...pageRoutes(join(dir, entry.name), entry.name.startsWith('(') ? prefix : `${prefix}/${entry.name}`));
  }
  return routes;
}

const ROUTES = pageRoutes(TENANT_APP).filter((route) => !route.includes('[...'));

function routeOf(path: string): string {
  const segments = path.split('/');
  const route = ROUTES.find((candidate) => {
    const parts = candidate.split('/');
    return parts.length === segments.length && parts.every((part, i) => part.startsWith('[') || part === segments[i]);
  });
  return route ?? path;
}

async function capture(response: Response, entries: Map<string, DemoRecording>): Promise<void> {
  const request = response.request();
  const url = new URL(response.url());
  if (!url.pathname.startsWith('/api/') || url.pathname.startsWith('/api/v1/auth/') || request.method() === 'OPTIONS') return;
  const contentType = (response.headers()['content-type'] ?? '').split(';')[0] ?? '';
  let body: unknown = null;
  if (response.status() !== 204) {
    // A body the browser dropped when the walk moved on is recorded when the next visit asks again.
    const text = await response.text().catch(() => null);
    if (text === null) return;
    body = contentType.includes('json') ? JSON.parse(text) : text;
  }
  const key = requestKey(request.method(), `${url.pathname}${url.search}`, request.method() === 'GET' ? undefined : (request.postData() ?? undefined));
  entries.set(key, { key, status: response.status(), contentType, body: recordedBody(key, body) });
}

async function walk(page: Page): Promise<DemoRecording[]> {
  const entries = new Map<string, DemoRecording>();
  const pending: Promise<void>[] = [];
  page.on('response', (response) => {
    pending.push(capture(response, entries));
  });
  // A tab or a link inside the app navigates without a page load, so "network
  // idle" has nothing to wait for: settle on no request in flight for half a second.
  let inFlight = 0;
  page.on('request', () => (inFlight += 1));
  page.on('requestfinished', () => (inFlight -= 1));
  page.on('requestfailed', () => (inFlight -= 1));
  const settle = async () => {
    await expect.poll(async () => {
      const before = inFlight;
      await page.waitForTimeout(500);
      return before === 0 && inFlight === 0;
    }).toBe(true);
  };
  const queue = [...SCREENS];
  const seen = new Set<string>(queue);
  const perRoute = new Map<string, number>();
  const follow = async () => {
    const hrefs = await page.locator('main a[href^="/"]').evaluateAll((anchors) => anchors.map((anchor) => anchor.getAttribute('href') ?? ''));
    for (const href of hrefs) {
      const url = new URL(href, 'http://demo.invalid');
      const target = `${url.pathname}${url.search}`;
      if (seen.has(target) || !onAScreen(url.pathname)) continue;
      const route = `${routeOf(url.pathname)}?${[...url.searchParams.keys()].sort().join('&')}`;
      const followed = perRoute.get(route) ?? 0;
      if (followed >= PER_ROUTE) continue;
      perRoute.set(route, followed + 1);
      seen.add(target);
      queue.push(target);
    }
  };
  for (let next = queue.shift(); next !== undefined; next = queue.shift()) {
    await page.goto(next);
    await settle();
    await follow();
    // A toggle shows another view of the same page (a version's diff, a filter): press it, follow, release it.
    // Found by name, because pressing one re-renders the others.
    const names = await page.locator('main button[aria-pressed="false"]').evaluateAll((buttons) => buttons.map((button) => button.textContent ?? ''));
    for (const [nth, name] of names.map((text, i) => [names.slice(0, i).filter((other) => other === text).length, text] as const)) {
      const toggle = page.locator('main').getByRole('button', { name, exact: true, pressed: false }).nth(nth);
      if ((await toggle.count()) === 0) continue;
      await toggle.click();
      await settle();
      await follow();
      // Some toggles act once and never stay pressed (the search screen's suggested searches).
      const pressed = page.locator('main').getByRole('button', { name, exact: true, pressed: true });
      if ((await pressed.count()) === 0) continue;
      await pressed.first().click();
      await settle();
    }
    // A screen's tabs are buttons, not links: open each one and follow what it shows.
    const tabs = page.locator('main [role="tab"]');
    for (let i = 0; i < (await tabs.count()); i++) {
      if ((await tabs.nth(i).getAttribute('aria-selected')) === 'true') continue;
      await tabs.nth(i).click();
      await settle();
      await follow();
    }
  }
  await Promise.all(pending);
  return [...entries.values()].sort((a, b) => a.key.localeCompare(b.key));
}

/** One request per line, so a re-recording reads as a diff of what changed. */
function serialise(recordings: DemoRecordings): string {
  return `{"recordedAt":${JSON.stringify(recordings.recordedAt)},"entries":[\n${recordings.entries.map((entry) => JSON.stringify(entry)).join(',\n')}\n]}\n`;
}

test.describe('public page demo', () => {
  test("the demo's recordings still answer every request its screens make @smoke", async ({ page, apiGuard }) => {
    test.setTimeout(RECORD ? 600_000 : 180_000);
    allowFreshContext(apiGuard);
    // The briefing links to the week before its first one, and the demo keeps that answer too.
    apiGuard.allow(/\/api\/v1\/briefings\/\d{4}-\d{2}-\d{2}$/, 404, 'the week before the first briefing has none');
    await signInAs(page, DEMO_LOGIN);
    await page.waitForLoadState('networkidle');
    const recordedAt = new Date().toISOString();
    const fresh: DemoRecordings = { recordedAt, entries: await walk(page) };
    expect(fresh.entries.length, 'the walk reached the screens').toBeGreaterThan(SCREENS.length);

    if (RECORD) {
      writeFileSync(RECORDINGS, serialise(fresh));
      writeFileSync(RECORDED_AT, `${JSON.stringify({ recordedAt }, null, 2)}\n`);
      return;
    }
    const templates = Object.keys((JSON.parse(readFileSync(OPENAPI, 'utf8')) as { paths: Record<string, unknown> }).paths);
    const committed = JSON.parse(readFileSync(RECORDINGS, 'utf8')) as DemoRecordings;
    expect(staleness(committed, fresh, templates), 'The demo no longer matches the app. Run `npm run demo:record` in frontend/ and commit the recordings.').toEqual([]);
  });

  test('the demo runs the app on its recordings and never reaches the API, even beside a signed-in session', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    // This browser now holds a real session cookie, which the demo must never use.
    await signInAs(page, DEMO_LOGIN);
    const fromDemo: string[] = [];
    page.on('request', (request) => {
      if (request.frame().name() === DEMO_FRAME_NAME && request.url().includes('/api/')) fromDemo.push(request.url());
    });
    await page.goto('/welcome');
    await page.getByRole('region', { name: 'Demo' }).scrollIntoViewIfNeeded();
    const app = page.frameLocator(`iframe[name="${DEMO_FRAME_NAME}"]`);
    await app.getByRole('link', { name: 'Watch', exact: true }).first().click();
    await expect(app.getByRole('tab', { selected: true })).toBeVisible();
    await app.getByRole('link', { name: 'Inventory', exact: true }).first().click();
    await expect(app.getByRole('tab', { selected: true })).toBeVisible();
    expect(fromDemo, 'requests from the demo frame to the API').toEqual([]);
  });

  test.describe('on a phone', () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

    test('the demo opens full screen when asked, and loads nothing before', async ({ page, apiGuard }) => {
      allowFreshContext(apiGuard);
      await page.goto('/welcome');
      await expect(page.locator(`iframe[name="${DEMO_FRAME_NAME}"]`)).toHaveCount(0);
      await page.getByRole('button', { name: 'Open the demo' }).click();
      const dialog = page.getByRole('dialog', { name: 'Demo' });
      const app = page.frameLocator(`iframe[name="${DEMO_FRAME_NAME}"]`);
      await expect(app.locator('main')).toBeVisible();
      await dialog.getByRole('button', { name: 'Close the demo' }).click();
      await expect(dialog).toHaveCount(0);
    });
  });
});
