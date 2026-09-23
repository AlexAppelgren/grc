import { readFileSync } from 'node:fs';

import type { Page } from '@playwright/test';

import { AA_NON_TEXT, AA_NORMAL_TEXT, contrastRatio, flatten, NON_TEXT, PAIRS, type Pair } from '@/styles/contrast';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';
import { CHUNK5_WATCH, openChangeByStableKey, openWatchFeed, signInAsSv } from './support/watch-coverage';

// shared: the @e2e scenarios from backend/apps/shared/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// NFR-S8, the pill gallery, is real in pills.gallery.spec.ts, beside the
// screenshot baselines it compares against.

// ---------------------------------------------------------------------------
// NFR-S9: WCAG AA measured in a browser. contrast.test.ts proves the named
// pairs from the stylesheets; this proves them from the colours Chromium
// computes, under a light and a dark system theme (the app follows the
// system: next-themes puts `light` or `dark` on <html>, providers.tsx), and
// sweeps every pill actually on screen against what is actually behind it.
// ---------------------------------------------------------------------------

const SCHEMES = ['light', 'dark'] as const;
type Scheme = (typeof SCHEMES)[number];

async function expectScheme(page: Page, scheme: Scheme): Promise<void> {
  await expect(page.locator('html')).toHaveClass(new RegExp(`(^|\\s)${scheme}(\\s|$)`));
}

interface MeasuredPair {
  name: string;
  fg: string;
  bg: string;
  /** Custom properties the page does not define: the browser would fall back silently and measure something else. */
  missing: string[];
}

/** Each pair's two colours as the browser computes them under the page's theme. */
async function measurePairs(page: Page, pairs: readonly Pair[]): Promise<MeasuredPair[]> {
  return page.evaluate(
    (list) =>
      list.map(({ name, fg, bg }) => {
        const probe = document.createElement('span');
        probe.style.color = `var(${fg})`;
        probe.style.backgroundColor = `var(${bg})`;
        document.body.append(probe);
        const style = getComputedStyle(probe);
        const measured = { name, fg: style.color, bg: style.backgroundColor, missing: [fg, bg].filter((v) => style.getPropertyValue(v).trim() === '') };
        probe.remove();
        return measured;
      }),
    [...pairs],
  );
}

/** Every pill on the page: its text colour, and the backgrounds of it and its ancestors, innermost first, down to the first opaque one. */
async function measurePills(page: Page): Promise<{ name: string; fg: string; layers: string[] }[]> {
  return page.locator('[data-pill]').evaluateAll((pills) =>
    pills.map((pill) => {
      const layers: string[] = [];
      for (let node: Element | null = pill; node !== null; node = node.parentElement) {
        const background = getComputedStyle(node).backgroundColor;
        layers.push(background);
        // Chromium writes an opaque colour as rgb() and a translucent one as rgba().
        if (background.startsWith('rgb(')) break;
      }
      return { name: `${pill.getAttribute('data-pill') ?? ''} pill "${pill.textContent ?? ''}"`, fg: getComputedStyle(pill).color, layers };
    }),
  );
}

function shortfall(where: string, name: string, fg: string, bg: string, floor: number): string[] {
  const ratio = contrastRatio(fg, bg);
  return ratio < floor ? [`${where}: ${name} is ${ratio.toFixed(2)}:1, under ${floor}:1 (${fg} on ${bg})`] : [];
}

/**
 * The named pairs that fall short of AA under the page's theme: 4.5:1 for
 * text, 3:1 for non-text. Every pair's tokens are set once on the theme class
 * (theme.css, tokens.generated.css) and no screen overrides one, so one page
 * per theme measures them for every screen.
 */
async function pairFailures(page: Page, where: string): Promise<string[]> {
  const failures: string[] = [];
  for (const [pairs, floor] of [
    [PAIRS, AA_NORMAL_TEXT],
    [NON_TEXT, AA_NON_TEXT],
  ] as const) {
    for (const pair of await measurePairs(page, pairs)) {
      if (pair.missing.length > 0) failures.push(`${where}: ${pair.name} names ${pair.missing.join(' and ')}, which the page does not define`);
      else failures.push(...shortfall(where, pair.name, pair.fg, pair.bg, floor));
    }
  }
  return failures;
}

/** Every pill on the page that falls short of 4.5:1 against what is actually behind it, once nothing on the page is still loading. */
async function pillFailures(page: Page, where: string): Promise<string[]> {
  // A panel with a query of its own can still be loading after the screen's
  // first pill shows; its pills belong in the sweep.
  await expect(page.locator('[data-loading-state]')).toHaveCount(0);
  return (await measurePills(page)).flatMap((pill) => shortfall(where, pill.name, pill.fg, flatten(pill.layers), AA_NORMAL_TEXT));
}

interface Screen {
  name: string;
  /** Opens the screen and settles on a pill in its own content, so a sweep is never of an empty page. */
  open: (page: Page) => Promise<void>;
}

// The seeded screens a bank reads. Library titles and keys are seeded data
// (apps/shared/e2e_seed.py), so records are found by stable key or by pattern.
const TENANT_SCREENS: readonly Screen[] = [
  {
    name: 'Today',
    open: async (page) => {
      await page.goto('/');
      await expect(page.locator('[data-lead-card] [data-pill]').first()).toBeVisible();
    },
  },
  {
    name: 'Watch',
    open: async (page) => {
      await page.goto('/watch');
      await expect(page.locator('[data-change-rows] [data-pill]').first()).toBeVisible();
    },
  },
  {
    name: 'Inventory',
    open: async (page) => {
      await page.goto('/inventory');
      await expect(page.locator('[data-obligation-rows] [data-pill]').first()).toBeVisible();
    },
  },
  {
    name: 'an instrument',
    open: async (page) => {
      await page.goto('/inventory?tab=instruments');
      await page.locator('[data-instrument="fffs-2017-2"]').click();
      await expect(page.locator('[data-instrument="fffs-2017-2"] [data-header-pills] [data-pill]').first()).toBeVisible();
      // The obligations panel loads on its own query; the research payment
      // duty is one of this instrument's.
      await expect(page.locator('[data-obligations-panel] [data-obligation="obl-research-payments"] [data-pill]').first()).toBeVisible();
    },
  },
  {
    name: 'Roadmap',
    open: async (page) => {
      await page.goto('/roadmap');
      // An expanded date carries its urgency as a pill (HOM-S6).
      await page.getByRole('button', { name: /Amended reporting of securities financing transactions/ }).click();
      await expect(page.locator('[data-roadmap-detail] [data-pill]').first()).toBeVisible();
    },
  },
  {
    name: 'Search',
    open: async (page) => {
      await page.goto('/search');
      await page.getByRole('searchbox', { name: 'Search' }).fill('FFFS 2017:2');
      await page.getByRole('button', { name: 'Search', exact: true }).click();
      await expect(page.locator('[data-search-rows] [data-pill]').first()).toBeVisible();
    },
  },
];

test.describe('shared journeys', () => {
  test.fixme("NFR-S7: Every screen reaches real data within its budget", async () => {
    // pending: NFR-S7 (NFR-02)
  });

  test("NFR-S9: Every text-on-surface pair passes WCAG AA in both themes", async ({ page }) => {
    // The named pairs are measured here, once per system theme, for every
    // screen. The gallery holds every tone, slot and record type in a light
    // and a dark column, so each system theme also sweeps all six tones in
    // both themes.
    const failures: string[] = [];
    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto('/dev/pills');
      await expect(page.locator('[data-theme-column="dark"] [data-pill]').first()).toBeVisible();
      await expectScheme(page, scheme);
      failures.push(...(await pairFailures(page, `named pairs, ${scheme}`)), ...(await pillFailures(page, `pill gallery, ${scheme}`)));
    }
    expect(failures).toEqual([]);
  });

  test("NFR-S9: Every pill on the seeded tenant screens passes WCAG AA in both themes", async ({ page, apiGuard }) => {
    // One sign-in for twelve views: a passkey ceremony is the most expensive
    // step a journey takes, so the views share one and the time limit grows.
    test.slow();
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);

    const failures: string[] = [];
    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      for (const screen of TENANT_SCREENS) {
        await screen.open(page);
        await expectScheme(page, scheme);
        failures.push(...(await pillFailures(page, `${screen.name}, ${scheme}`)));
      }
    }
    expect(failures).toEqual([]);
  });

  test("NFR-S9: Every pill on the console queue passes WCAG AA in both themes", async ({ page, apiGuard }) => {
    // Six views on one sign-in, as above.
    test.slow();
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.editor);

    const failures: string[] = [];
    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      // The seeded proposals wait in the queue until a journey decides them,
      // so every tab is swept and one of them lists them.
      let proposalPills = 0;
      for (const tab of ['waiting', 'approved', 'rejected']) {
        await page.goto(`/console/queue?tab=${tab}`);
        await expect(page.locator('[data-proposal-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
        await expectScheme(page, scheme);
        proposalPills += await page.locator('[data-proposal-rows] [data-pill]').count();
        failures.push(...(await pillFailures(page, `console queue, ${tab}, ${scheme}`)));
      }
      expect(proposalPills, `no tab of the console queue listed a proposal (${scheme})`).toBeGreaterThan(0);
    }
    expect(failures).toEqual([]);
  });

  // The catalog half of I18N-S3 runs before any journey: `npm run check:messages`
  // fails on a key missing in either language (scripts/messages-check.test.mjs),
  // and `npm run lint` on a string literal in JSX text (react/jsx-no-literals,
  // eslint.config.js). This is the person's half: the interface switched to
  // Swedish from the rail's account menu and back from the More sheet on a phone,
  // the vocabulary labels coming from their Swedish rows. The login is its own
  // (reserved for I18N-S3), because the language is saved on the person and every
  // session of theirs follows it.
  test('I18N-S3: Every UI string is in the catalog for every shipped language', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    const desktop = page.viewportSize();
    if (desktop === null) throw new Error('the journey needs a fixed viewport');
    // Waits for the shell in either language, so a retry after a run whose teardown
    // failed still signs in, fails on English below and restores it in the teardown.
    await signInAsSv(page, LOGINS.language);
    const who = page.locator('[data-who-panel]');
    // Named "…, account menu" in English and "…, kontomeny" in Swedish.
    const accountMenu = who.getByRole('button', { name: /^Nils Åberg, / });
    // Each language is named by its own row, in its own words, never by a catalog.
    const svenskaName = /^Svenska$/;
    const englishName = /^English$/;
    const svenska = page.getByRole('menuitemradio', { name: svenskaName });
    const english = page.getByRole('menuitemradio', { name: englishName });
    // The role and the urgency are vocabulary rows, seeded with a label per language.
    const change = page.locator(`[data-change="${CHUNK5_WATCH.timelineChange}"]`);
    const urgency = (label: RegExp) => change.locator('[data-pill]').filter({ hasText: label });
    try {
      await openWatchFeed(page);
      await expect(who).toContainText('Example Bank AB · Contributor');
      await expect(urgency(/^Within 3 months$/)).toBeVisible();

      await accountMenu.click();
      await expect(english).toHaveAttribute('aria-checked', 'true');
      await svenska.click();
      // The menu stays open and changes language with the rest of the page.
      await expect(svenska).toHaveAttribute('aria-checked', 'true');
      await expect(page.getByRole('group', { name: svCopy('common', 'language.label') })).toBeVisible();
      await page.keyboard.press('Escape');

      const main = page.getByRole('navigation', { name: svCopy('nav', 'nav.main') });
      await expect(main.getByRole('link', { name: svCopy('nav', 'nav.watch') })).toHaveAttribute('aria-current', 'page');
      await expect(who).toContainText('Example Bank AB · Bidragsgivare');
      await expect(urgency(/^Inom 3 månader$/)).toBeVisible();

      // Saved on the person, not the page: another screen, loaded from cold, reads Swedish too.
      await page.goto('/');
      await expect(page.getByRole('heading', { level: 1, name: svCopy('today', 'today.title') })).toBeVisible();

      // Back to English on a phone, where the account lives in the More sheet.
      await page.setViewportSize({ width: 375, height: 812 });
      await page
        .getByRole('navigation', { name: svCopy('nav', 'nav.main') })
        .getByRole('button', { name: svCopy('nav', 'nav.more') })
        .click();
      const svSheet = page.getByRole('dialog', { name: svCopy('nav', 'nav.more') }).getByRole('group', { name: svCopy('common', 'language.label') });
      await expect(svSheet.getByRole('radio', { name: svenskaName })).toBeChecked();
      // A click, not check(): the radio follows the saved language, so it turns only once the save lands.
      await svSheet.getByRole('radio', { name: englishName }).click();
      // The sheet stays open and changes language with the rest of the page.
      const enSheet = page.getByRole('dialog', { name: 'More' }).getByRole('group', { name: 'Language' });
      await expect(enSheet.getByRole('radio', { name: englishName })).toBeChecked();
      await page.keyboard.press('Escape');
      await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
      await expect(page.getByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeVisible();

      await page.setViewportSize(desktop);
      await expect(who).toContainText('Example Bank AB · Contributor');
    } finally {
      // Teardown that runs on failure too: the login goes back to English, from the
      // rail. A fresh load closes whatever was open; choosing the language in use saves nothing.
      await page.setViewportSize(desktop);
      await page.goto('/');
      await accountMenu.click();
      await english.click();
      await expect(english).toHaveAttribute('aria-checked', 'true');
      await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
    }
  });

  // The browser runs in New York, so only the tenant's own timezone can put Stockholm
  // wall time on the screen: a moment formatted in the browser's local time fails.
  // That the tenant's zone beats the default one is format.test.ts's, because tenant A
  // and the default are both Europe/Stockholm.
  test.describe('in a browser in another timezone', () => {
    test.use({ timezoneId: 'America/New_York' });

    test('I18N-S4: Dates, numbers and partial dates format per language and timezone', async ({ page, apiGuard }) => {
      allowFreshContext(apiGuard);
      // The one seeded login whose own language is Swedish, in tenant A (Europe/Stockholm).
      await signInAsSv(page, LOGINS.readerSv);
      // The journeys run in one pinned language: the browser is English
      // (playwright.config.ts, `locale: 'en-GB'`) and every seeded login's own
      // language is `en` unless the roster says otherwise (e2e_logins.py). The
      // Swedish below is this person's own saved language, never the browser's.
      expect(await page.evaluate(() => navigator.language)).toBe('en-GB');

      // The dates are read from the change as the server sends it, so the journey
      // asserts how they render, never a date written into the test.
      const read = page.waitForResponse(async (response) => {
        if (response.request().method() !== 'GET' || !/^\/api\/v1\/changes\/[^/]+$/.test(new URL(response.url()).pathname)) return false;
        return ((await response.json()) as ChangeRead).stableKey === CHUNK5_WATCH.timelineChange;
      });
      await openChangeByStableKey(page, CHUNK5_WATCH.timelineChange);
      const change = (await (await read).json()) as ChangeRead;

      // A moment stored in UTC reads as Stockholm wall time, in Swedish ("23 sep. 2026 16:20").
      const fetched = change.documents.find((d) => d.fetchedAt !== null);
      if (fetched?.fetchedAt == null) throw new Error('the seeded change has no fetched document');
      const fetchedAt = fetched.fetchedAt;
      const stockholm = await page.evaluate(
        (iso) =>
          new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Stockholm', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(
            new Date(iso),
          ),
        fetchedAt,
      );
      const line = page.locator(`[data-document="${fetched.id}"]`);
      await expect(line).toContainText(stockholm);
      // Never the UTC clock the moment is stored in.
      await expect(line).not.toContainText(new Date(fetchedAt).toISOString().slice(11, 16));

      // An in-force date known only to its quarter reads as the Swedish quarter ("kv. 4 2026").
      const inForce = change.events.find((e) => e.datePrecision === 'quarter' && e.eventDate !== null);
      if (inForce?.eventDate == null) throw new Error('the seeded change has no quarter-precision date');
      const year = inForce.eventDate.slice(0, 4);
      const quarter = Math.ceil(Number(inForce.eventDate.slice(5, 7)) / 3);
      await expect(page.locator('[data-change-timeline]').getByText(`kv. ${quarter} ${year}`, { exact: true })).toBeVisible();
    });
  });
});

/** What I18N-S4 reads of a change: its pages and its timeline, as `GET /changes/{id}` sends them. */
interface ChangeRead {
  stableKey: string;
  documents: { id: string; fetchedAt: string | null }[];
  events: { eventDate: string | null; datePrecision: string | null }[];
}

/** Swedish copy, read from the catalog the app itself loads, so a reworded string never breaks the journey. */
function svCopy(namespace: string, key: string): string {
  const catalog = JSON.parse(readFileSync(new URL(`../../src/messages/${namespace}/sv.json`, import.meta.url), 'utf8')) as Record<string, string>;
  const value = catalog[key];
  if (value === undefined) throw new Error(`the sv catalog of ${namespace} has no "${key}"`);
  return value;
}
