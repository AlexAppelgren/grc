import type { Page } from '@playwright/test';

import { AA_NON_TEXT, AA_NORMAL_TEXT, contrastRatio, flatten, NON_TEXT, PAIRS, type Pair } from '@/styles/contrast';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

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

/** Each pair's two colours as the browser computes them in the screen's own content, under the page's theme. */
async function measurePairs(page: Page, pairs: readonly Pair[]): Promise<MeasuredPair[]> {
  return page.evaluate(
    (list) => {
      const host = document.querySelector('#main') ?? document.body;
      return list.map(({ name, fg, bg }) => {
        const probe = document.createElement('span');
        probe.style.color = `var(${fg})`;
        probe.style.backgroundColor = `var(${bg})`;
        host.append(probe);
        const style = getComputedStyle(probe);
        const measured = { name, fg: style.color, bg: style.backgroundColor, missing: [fg, bg].filter((v) => style.getPropertyValue(v).trim() === '') };
        probe.remove();
        return measured;
      });
    },
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

/** What falls short of AA on the page as it stands: 4.5:1 for text and every pill, 3:1 for non-text. Empty when all pass. */
async function contrastFailures(page: Page, where: string): Promise<string[]> {
  const failures: string[] = [];
  const check = (name: string, fg: string, bg: string, floor: number): void => {
    const ratio = contrastRatio(fg, bg);
    if (ratio < floor) failures.push(`${where}: ${name} is ${ratio.toFixed(2)}:1, under ${floor}:1 (${fg} on ${bg})`);
  };
  for (const [pairs, floor] of [
    [PAIRS, AA_NORMAL_TEXT],
    [NON_TEXT, AA_NON_TEXT],
  ] as const) {
    for (const pair of await measurePairs(page, pairs)) {
      if (pair.missing.length > 0) failures.push(`${where}: ${pair.name} names ${pair.missing.join(' and ')}, which the page does not define`);
      else check(pair.name, pair.fg, pair.bg, floor);
    }
  }
  for (const pill of await measurePills(page)) check(pill.name, pill.fg, flatten(pill.layers), AA_NORMAL_TEXT);
  return failures;
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
    // The gallery holds every tone, slot and record type in a light and a dark
    // column, so each system theme sweeps all six tones in both themes.
    const failures: string[] = [];
    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto('/dev/pills');
      await expect(page.locator('[data-theme-column="dark"] [data-pill]').first()).toBeVisible();
      await expectScheme(page, scheme);
      failures.push(...(await contrastFailures(page, `pill gallery, ${scheme}`)));
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
        failures.push(...(await contrastFailures(page, `${screen.name}, ${scheme}`)));
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
        failures.push(...(await contrastFailures(page, `console queue, ${tab}, ${scheme}`)));
      }
      expect(proposalPills, `no tab of the console queue listed a proposal (${scheme})`).toBeGreaterThan(0);
    }
    expect(failures).toEqual([]);
  });

  test.fixme("I18N-S3: Every UI string is in the catalog for every shipped language", async () => {
    // pending: I18N-S3 (I18N-02)
  });

  test.fixme("I18N-S4: Dates, numbers and partial dates format per language and timezone", async () => {
    // pending: I18N-S4 (I18N-02)
  });
});
