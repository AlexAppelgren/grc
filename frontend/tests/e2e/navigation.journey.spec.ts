import type { Locator, Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, openMore, signInAs, signOut } from './support/passkeys';

// Navigation at every width (design/system/navigation.md 16): the floating
// tab bar and its More sheet below 1024 px, the rail from 1024 px, and what
// happens when a rotation or a resize crosses that line. The real stack, no
// mocks. Each block sets its own viewport, so the rest of the suite keeps
// Desktop Chrome and does not double. Phones and tablets set hasTouch, which
// gives a coarse pointer; phones also set isMobile. English only (playbook 8.3).

type Box = { x: number; y: number; width: number; height: number };

const mainNav = (page: Page) => page.getByRole('navigation', { name: 'Main' });
const bar = (page: Page) => page.locator('[data-slot="tab-bar"]');
const rail = (page: Page) => page.locator('[data-slot="sidebar"]');
const sheet = (page: Page) => page.getByRole('dialog', { name: 'More' });
const moreButton = (page: Page) => bar(page).getByRole('button', { name: 'More' });

async function boxOf(locator: Locator): Promise<Box> {
  const box = await locator.boundingBox();
  if (box === null) throw new Error('navigation: the element has no box');
  return box;
}

function intersects(a: Box, b: Box): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

async function noHorizontalScroll(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

/** The bottom edge of the page's last element after scrolling to the end, and the bar's top edge. */
async function lastElementAndBar(page: Page): Promise<{ lastBottom: number; barTop: number }> {
  return page.evaluate(() => {
    window.scrollTo(0, document.documentElement.scrollHeight);
    const last = document.querySelector('main > div')?.lastElementChild;
    const barBox = document.querySelector('[data-slot="tab-bar"]')?.getBoundingClientRect();
    if (!last || !barBox) throw new Error('navigation: no page content or no bar');
    return { lastBottom: last.getBoundingClientRect().bottom, barTop: barBox.top };
  });
}

/** Every label in the bar: its height against one line, and whether its text overflows its box. */
async function labels(page: Page): Promise<{ text: string; height: number; lineHeight: number; clipped: boolean }[]> {
  return bar(page)
    .locator('li > * > span')
    .evaluateAll((spans) =>
      spans.map((span) => ({
        text: span.textContent ?? '',
        height: span.getBoundingClientRect().height,
        lineHeight: parseFloat(getComputedStyle(span).lineHeight),
        clipped: span.scrollWidth > span.clientWidth,
      })),
    );
}

async function overlaysGone(page: Page): Promise<void> {
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('menu')).toHaveCount(0);
  await expect(page.locator('#main')).toBeFocused();
  // Visible by role means no stray aria-hidden is left on the page.
  await expect(mainNav(page)).toBeVisible();
  expect(await page.evaluate(() => getComputedStyle(document.body).pointerEvents)).not.toBe('none');
}

test.describe('navigation on a phone, 375 × 812', () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true });

  test('a reader signs in to the tab bar, with no rail and no sideways scroll @smoke', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    const nav = mainNav(page);
    await expect(nav.getByRole('link')).toHaveText(['Today', 'Watch', 'Inventory', 'Search']);
    await expect(nav.getByRole('link', { name: 'Today', exact: true })).toHaveAttribute('aria-current', 'page');
    await expect(nav.getByRole('button', { name: 'More' })).toBeVisible();
    await expect(rail(page)).toBeHidden();
    await expect(page.locator('[data-mobile-header]').getByRole('img', { name: 'bleqq, pronounced blek' })).toBeVisible();
    await noHorizontalScroll(page);
  });

  test('every tab keeps the navigation, on the screens not built yet too', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    for (const [name, path] of [
      ['Watch', '/watch'],
      ['Inventory', '/inventory'],
      ['Search', '/search'],
    ] as const) {
      await mainNav(page).getByRole('link', { name, exact: true }).tap();
      await expect(page).toHaveURL(new RegExp(`${path}$`));
      await expect(page.getByRole('heading', { level: 1, name: 'Not found' })).toBeVisible();
      await expect(mainNav(page).getByRole('link', { name, exact: true })).toHaveAttribute('aria-current', 'page');
    }
    await mainNav(page).getByRole('link', { name: 'Today', exact: true }).tap();
    await expect(page).toHaveURL(/\/$/);
    await expect(mainNav(page).getByRole('link', { name: 'Today', exact: true })).toHaveAttribute('aria-current', 'page');
  });

  test('More opens a sheet with the rest and the account, and closes every way', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    const more = moreButton(page);

    await more.tap();
    await expect(sheet(page).getByRole('link', { name: 'Roadmap' })).toBeVisible();
    await expect(sheet(page).getByRole('group', { name: 'Account' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(sheet(page)).toHaveCount(0);
    await expect(more).toBeFocused();

    await more.tap();
    await expect(sheet(page)).toBeVisible();
    // The scrim, above the sheet.
    await page.touchscreen.tap(187, 40);
    await expect(sheet(page)).toHaveCount(0);

    await more.tap();
    await sheet(page).getByRole('button', { name: 'Close' }).tap();
    await expect(sheet(page)).toHaveCount(0);
  });

  test('a page reached through More marks More as current', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await (await openMore(page)).getByRole('link', { name: 'My passkeys' }).tap();
    await expect(page).toHaveURL(/\/me\/passkeys$/);
    await expect(sheet(page)).toHaveCount(0);
    await expect(moreButton(page)).toHaveAttribute('data-active', 'true');
    await expect(moreButton(page)).toHaveAttribute('aria-current', 'true');
    await expect(bar(page).locator('a[aria-current="page"]')).toHaveCount(0);

    await expect((await openMore(page)).getByRole('link', { name: 'My passkeys' })).toHaveAttribute('aria-current', 'page');
  });

  test('the admin finds Admin in More', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await (await openMore(page)).getByRole('link', { name: 'Admin' }).tap();
    await expect(page).toHaveURL(/\/admin$/);
    await expect(moreButton(page)).toHaveAttribute('aria-current', 'true');
  });

  test('going back closes the sheet along with the page', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await (await openMore(page)).getByRole('link', { name: 'Admin' }).tap();
    await page.locator('[data-admin-section="admin-organisation"]').tap();
    await expect(page).toHaveURL(/\/admin\/organisation$/);
    await openMore(page);
    await page.goBack();
    await expect(page).toHaveURL(/\/admin$/);
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });

  test('the bar steps aside for the keyboard, and the next control lands clear of it', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/organisation');
    const name = page.locator('#org-name');
    await expect(name).toBeVisible();

    await name.focus();
    await expect(bar(page)).toBeHidden();
    await name.blur();
    await expect(bar(page)).toBeVisible();

    const timezone = page.locator('#org-timezone');
    await timezone.evaluate((el) => el.scrollIntoView({ block: 'end' }));
    await timezone.focus();
    await page.keyboard.press('Tab');
    const focused = page.locator(':focus');
    await expect(focused).toHaveAttribute('id', 'org-default-language');
    await expect(bar(page)).toBeVisible();
    expect(intersects(await boxOf(focused), await boxOf(bar(page)))).toBe(false);
  });

  test('the bar never hides the end of a page or a focused control', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/organisation');
    await expect(page.locator('#org-name')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollHeight > window.innerHeight)).toBe(true);

    const { lastBottom, barTop } = await lastElementAndBar(page);
    expect(lastBottom).toBeLessThanOrEqual(barTop);

    await page.evaluate(() => window.scrollTo(0, 0));
    let checked = 0;
    for (let step = 0; step < 60; step += 1) {
      await page.keyboard.press('Tab');
      const where = await page.evaluate(() => {
        const active = document.activeElement;
        return { inMain: active?.closest('main') !== null && active !== document.querySelector('main'), wrapped: active === document.body };
      });
      if (where.wrapped) break;
      if (!where.inMain || !(await bar(page).isVisible())) continue;
      expect(intersects(await boxOf(page.locator(':focus')), await boxOf(bar(page)))).toBe(false);
      checked += 1;
    }
    expect(checked).toBeGreaterThan(3);
  });

  test('signing out works from More', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await signOut(page);
  });

  test('the bar and the open sheet look as designed', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await page.evaluate(() => document.fonts.ready);
    await expect(bar(page)).toHaveScreenshot('tab-bar.png');
    await openMore(page);
    await expect(sheet(page)).toHaveScreenshot('more-sheet.png');
  });
});

for (const viewport of [
  { width: 360, height: 780 },
  { width: 320, height: 640 },
]) {
  test.describe(`navigation on a narrow phone, ${viewport.width} × ${viewport.height}`, () => {
    test.use({ viewport, hasTouch: true, isMobile: true });

    test('every tab label fits on one line, whole, with no sideways scroll', async ({ page, apiGuard }) => {
      allowFreshContext(apiGuard);
      await signInAs(page, LOGINS.reader);
      const found = await labels(page);
      expect(found.map((l) => l.text)).toEqual(['Today', 'Watch', 'Inventory', 'Search', 'More']);
      for (const label of found) {
        expect(label.height, `${label.text} is one line`).toBeLessThanOrEqual(label.lineHeight + 0.5);
        expect(label.clipped, `${label.text} is not clipped`).toBe(false);
      }
      await noHorizontalScroll(page);
    });
  });
}

test.describe('navigation on a phone in landscape, 844 × 390', () => {
  test.use({ viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true });

  test('the bar is short, each icon beside its label, clear of the page', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    expect((await boxOf(bar(page))).height).toBeLessThanOrEqual(56);
    const cells = await bar(page)
      .locator('li > *')
      .evaluateAll((items) =>
        items.map((cell) => {
          const icon = cell.querySelector('svg')?.getBoundingClientRect();
          const label = cell.querySelector('span');
          const box = label?.getBoundingClientRect();
          return {
            text: label?.textContent ?? '',
            oneLine: box !== undefined && label !== null && box.height <= parseFloat(getComputedStyle(label).lineHeight) + 0.5,
            beside: icon !== undefined && box !== undefined && icon.right <= box.left && icon.top < box.bottom && box.top < icon.bottom,
          };
        }),
      );
    expect(cells.map((c) => c.text)).toEqual(['Today', 'Watch', 'Inventory', 'Search', 'More']);
    for (const cell of cells) {
      expect(cell.oneLine, `${cell.text} is one line`).toBe(true);
      expect(cell.beside, `${cell.text} sits beside its icon`).toBe(true);
    }
    const { lastBottom, barTop } = await lastElementAndBar(page);
    expect(lastBottom).toBeLessThanOrEqual(barTop);
  });
});

test.describe('navigation in a very short window, 320 × 256', () => {
  test.use({ viewport: { width: 320, height: 256 } });

  test('the bar leaves the fixed layer and scrolls with the page', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    expect(await bar(page).evaluate((el) => getComputedStyle(el).position)).toBe('static');
  });
});

test.describe('navigation on a tablet, 768 × 1024', () => {
  test.use({ viewport: { width: 768, height: 1024 }, hasTouch: true });

  test('the bar hugs its cells and sits centred; the sheet is centred at 560px', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await expect(bar(page)).toBeVisible();
    await expect(rail(page)).toBeHidden();
    const barBox = await boxOf(bar(page));
    expect(barBox.width).toBeLessThanOrEqual(5 * 96 + 14);
    expect(Math.abs(barBox.x - (768 - barBox.x - barBox.width))).toBeLessThanOrEqual(1);

    await moreButton(page).tap();
    const sheetBox = await boxOf(sheet(page));
    expect(sheetBox.width).toBeLessThanOrEqual(560);
    expect(Math.abs(sheetBox.x - (768 - sheetBox.x - sheetBox.width))).toBeLessThanOrEqual(1);
    await sheet(page).getByRole('button', { name: 'Close' }).tap();
    await expect(sheet(page)).toHaveCount(0);
  });
});

test.describe('navigation in a narrow desktop window, 800 × 900', () => {
  test.use({ viewport: { width: 800, height: 900 } });

  test('a fine pointer keeps the bar while a text field has focus', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/organisation');
    await page.locator('#org-name').focus();
    await expect(page.locator('#org-name')).toBeFocused();
    await expect(bar(page)).toBeVisible();
  });
});

test.describe('navigation when the width crosses 1024 px', () => {
  test.use({ hasTouch: true });

  test('rotating an iPad with More open closes it and focuses the page', async ({ page, apiGuard }) => {
    await page.setViewportSize({ width: 834, height: 1194 });
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await openMore(page);
    await page.setViewportSize({ width: 1194, height: 834 });
    await expect(rail(page)).toBeVisible();
    await overlaysGone(page);
  });

  test('rotating an iPad with the account menu open closes it and focuses the page', async ({ page, apiGuard }) => {
    await page.setViewportSize({ width: 1194, height: 834 });
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await page.locator('[data-who-panel]').getByRole('button', { name: /, account menu$/ }).click();
    await expect(page.getByRole('menu')).toBeVisible();
    await page.setViewportSize({ width: 834, height: 1194 });
    await expect(bar(page)).toBeVisible();
    await overlaysGone(page);
  });

  test('1023 px has the bar, 1024 px has the rail', async ({ page, apiGuard }) => {
    await page.setViewportSize({ width: 1023, height: 800 });
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await expect(bar(page)).toBeVisible();
    await expect(rail(page)).toBeHidden();
    await page.setViewportSize({ width: 1024, height: 800 });
    await expect(rail(page)).toBeVisible();
    await expect(bar(page)).toBeHidden();
  });
});
