import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// watch: the @e2e scenarios from backend/apps/watch/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('watch journeys', () => {
  test.fixme("WAT-S1: The source registry and coverage log show what was checked and with what result", async () => {
    // pending: WAT-S1 (WAT-01)
  });

  test.fixme("WAT-S2: One record per reform carries a timeline with partial dates", async () => {
    // pending: WAT-S2 (WAT-02)
  });

  test.fixme("WAT-S4: Types, flags and scope come from vocabularies and stay suggestions until confirmed", async () => {
    // pending: WAT-S4 (WAT-03)
  });

  test.fixme("WAT-S6: Links to affected obligations carry a confidence and are confirmed by a person", async () => {
    // pending: WAT-S6 (WAT-04)
  });

  test.fixme("WAT-S7: The \"So what?\" is AI-drafted until a person confirms or rewrites it per tenant", async () => {
    // pending: WAT-S7 (WAT-05)
  });

  test.fixme("WAT-S8: A tenant requests a source and private sources stay private", async () => {
    // pending: WAT-S8 (WAT-06)
  });

  test.fixme("WAT-S9: The change row renders its pills in the fixed slot order", async () => {
    // pending: WAT-S9 (WAT-03, NFR-03)
  });
});

// PRD 0.3: a standard's revision is one watched change that reaches only the
// tenants that follow it (WAT-07). It stays test.fixme until the task in
// docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('standards revisions', () => {
  test.fixme("WAT-S10: A new edition of a standard is one change, and only tenants that follow it see it", async () => {
    // pending: WAT-S10 (WAT-02, WAT-07, CAS-01, AC-FP3)
  });
});

// ---------------------------------------------------------------------------
// The watch feed screen (chunk 5, /watch). These journeys drive the screen
// itself against the real feed read; the scenarios above belong to the two
// journey tasks that own them, and are left alone.
// ---------------------------------------------------------------------------

/** The feed has settled when its rows or one of its empty states is on screen. */
async function openFeed(page: Page, search = ''): Promise<void> {
  await page.goto(`/watch${search}`);
  await expect(page.locator('[data-change-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
}

function tab(page: Page, name: RegExp) {
  return page.getByRole('tab', { name });
}

async function noHorizontalScroll(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test.describe('the watch feed', () => {
  test('a compliance officer opens Watch and finds the tabs, the filters and where the feed stands', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openFeed(page);

    await expect(page.getByRole('heading', { level: 1, name: 'Watch' })).toBeVisible();
    await expect(page.getByText('Changes the agents found, waiting for a person to decide')).toBeVisible();
    // The triage tab carries its count, and the count comes from the route
    // the rows come from: the screen never counts a page of twenty itself.
    await expect(tab(page, /^Needs triage \(\d+\)$/)).toBeVisible();
    for (const name of [/^In progress$/, /^Closed$/, /^Dismissed$/]) {
      await expect(tab(page, name)).toBeVisible();
    }
    await expect(tab(page, /^Needs triage/)).toHaveAttribute('aria-selected', 'true');

    const filters = page.locator('[data-watch-filters]');
    await expect(filters.getByRole('combobox', { name: 'Regime' })).toBeVisible();
    await expect(filters.getByRole('combobox', { name: 'Change type' })).toBeVisible();
    await expect(filters.getByRole('combobox', { name: 'Urgency' })).toBeVisible();
    await expect(filters.getByRole('searchbox', { name: 'Search these changes' })).toBeVisible();
    // The regime filter's options are the taxonomy's own rows, so the read
    // behind it really answered.
    await expect(filters.getByRole('combobox', { name: 'Regime' }).getByRole('option')).not.toHaveCount(1);
  });

  test('the footprint filter holds one value, and the scope the reader chose travels in the address', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openFeed(page);

    const scope = page.getByRole('group', { name: 'Scope' });
    await expect(scope.getByRole('button', { name: 'In our scope' })).toHaveAttribute('aria-pressed', 'true');
    await scope.getByRole('button', { name: 'Markets we watch' }).click();
    await expect(page).toHaveURL(/scope=watched/);
    await expect(scope.getByRole('button', { name: 'Markets we watch' })).toHaveAttribute('aria-pressed', 'true');
    // One value, never a pair: choosing one lets the others go.
    await expect(scope.getByRole('button', { name: 'In our scope' })).toHaveAttribute('aria-pressed', 'false');
    await expect(scope.getByRole('button', { name: 'Show outside our scope' })).toHaveAttribute('aria-pressed', 'false');

    await scope.getByRole('button', { name: 'Show outside our scope' }).click();
    await expect(page).toHaveURL(/scope=all/);
    await expect(page.locator('[data-change-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
  });

  test('a phrase the reader types is sent to the feed and never written into the address', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openFeed(page);

    const asked = page.waitForRequest((request) => request.url().includes('/api/v1/changes') && request.url().includes('q=reconciliation'));
    await page.getByRole('searchbox', { name: 'Search these changes' }).fill('reconciliation');
    await page.getByRole('button', { name: 'Search' }).click();
    await asked;
    // What someone typed is this bank's own words: it reaches the read and
    // stops there, never the browser's history (playbook 4.7).
    await expect(page).toHaveURL(/\/watch$/);
    await expect(page.getByText('Nothing matches these filters')).toBeVisible();
    await page.getByRole('link', { name: 'Clear filters' }).click();
    await expect(page.getByRole('searchbox', { name: 'Search these changes' })).toHaveValue('');
  });

  test('each tab answers for itself, and an empty one says so rather than looking broken', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openFeed(page);

    await tab(page, /^Closed/).click();
    await expect(page).toHaveURL(/tab=closed/);
    await expect(tab(page, /^Closed/)).toHaveAttribute('aria-selected', 'true');
    // Nothing has been worked in R1, so this tab is honestly empty; the
    // triage tab has its own words and its own next step.
    await expect(page.getByText('Nothing in this tab')).toBeVisible();

    await tab(page, /^Needs triage/).click();
    await expect(page).toHaveURL(/\/watch$/);
    await expect(page.getByText('Nothing needs triage').or(page.locator('[data-change-rows]')).first()).toBeVisible();
  });

  test('a reader arriving at a scope with nothing in it is shown the way back', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await openFeed(page, '?scope=watched');

    // "Markets we watch" is declared and empty until a change takes its
    // jurisdiction from its authority, so the feed is empty rather than
    // quietly showing the ordinary one under another name.
    await expect(page.getByText('Nothing matches these filters')).toBeVisible();
    await page.getByRole('link', { name: 'Clear filters' }).click();
    await expect(page).toHaveURL(/\/watch$/);
    await expect(page.getByRole('group', { name: 'Scope' }).getByRole('button', { name: 'In our scope' })).toHaveAttribute('aria-pressed', 'true');
  });

  // One sign-in for all six views. A passkey ceremony is the most expensive
  // thing a journey does, and six of them for a layout check crowded the
  // shared stack enough to time out journeys in other specs (2026-09-21).
  test('the feed holds its shape at every width, in both themes', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);

    for (const [width, height] of [
      [390, 844],
      [820, 1180],
      [1280, 900],
    ] as const) {
      for (const scheme of ['light', 'dark'] as const) {
        await page.emulateMedia({ colorScheme: scheme });
        await page.setViewportSize({ width, height });
        await openFeed(page);

        await expect(page.getByRole('heading', { level: 1, name: 'Watch' })).toBeVisible();
        await expect(tab(page, /^Needs triage/)).toBeVisible();
        await expect(page.locator('[data-watch-filters]')).toBeVisible();
        await expect(page.getByRole('group', { name: 'Scope' })).toBeVisible();
        // The theme the page really rendered in, not the one we asked for.
        expect(await page.evaluate(() => document.documentElement.classList.contains('dark'))).toBe(scheme === 'dark');
        await noHorizontalScroll(page);
      }
    }
  });

  test.fixme('the Coverage tab lists each source with its last check and its stale marker', async () => {
    // pending: `GET /sources/coverage` still answers 501 not_built. The tab,
    // its states and its tones are built and pinned by
    // SourceCoverageTab.test.tsx; this journey opens once
    // `c5-watch-sources-coverage` builds the registry and the log, and
    // `c5-e2e-watch-journeys-a` owns WAT-S1 itself.
  });

  test.fixme('a change row carries its pills, its So what and its key date', async () => {
    // pending: the seed has no watch rows yet. `c5-seed-watch` adds the
    // sources, runs, changes and cases every chunk 5 journey rests on, and
    // `c5-e2e-watch-journeys-a` owns WAT-S9, the pill-order journey. Until
    // that seed lands this feed can only be proved empty, which the journeys
    // above do; the row itself is pinned by WatchFeedScreen.test.tsx.
  });
});
