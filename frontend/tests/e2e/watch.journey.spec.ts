import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs, signOut } from './support/passkeys';
import { CHUNK5_WATCH, consoleSourceRow, openChangeByStableKey, openWatchFeed, signInAsSv } from './support/watch-coverage';

// watch: the @e2e scenarios from backend/apps/watch/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('watch journeys', () => {
  test('WAT-S1: The source registry and coverage log show what was checked and with what result', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/watch?tab=coverage');
    const coverage = page.locator('[data-source-coverage]');
    await expect(coverage).toBeVisible();

    const healthy = coverage.locator(`[data-source="${CHUNK5_WATCH.healthySource}"]`);
    await expect(healthy).toBeVisible();
    await expect(healthy).not.toHaveAttribute('data-stale', '');
    await expect(healthy.getByText('Checked', { exact: true })).toBeVisible();

    // The later, failing check is what the console's "Source coverage" shows
    // as stale, with the failing check itself named beside it.
    const failing = coverage.locator(`[data-source="${CHUNK5_WATCH.failingSource}"]`);
    await expect(failing).toHaveAttribute('data-stale', '');
    await expect(failing.getByText('Fetch failed', { exact: true })).toBeVisible();
    await expect(failing.locator('[data-last-error]')).toHaveText(CHUNK5_WATCH.failingSourceError);

    await signOut(page);
    await signInAs(page, LOGINS.editor);
    await page.goto('/console/sources');
    await expect(page.getByRole('heading', { level: 1, name: 'Sources' })).toBeVisible();
    const failingRow = consoleSourceRow(page, CHUNK5_WATCH.failingSource);
    await expect(failingRow.getByText('Stale', { exact: true })).toBeVisible();
    await expect(failingRow.getByText(CHUNK5_WATCH.failingSourceError)).toBeVisible();
  });

  test('WAT-S2: One record per reform carries a timeline with partial dates', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openChangeByStableKey(page, CHUNK5_WATCH.timelineChange);

    const timeline = page.locator('[data-change-timeline]');
    await expect(timeline.getByText('March 2026', { exact: true })).toBeVisible();
    await expect(timeline.getByText('15 Jun 2026', { exact: true })).toBeVisible();
    await expect(timeline.getByText('Q1 2027', { exact: true })).toBeVisible();
    await signOut(page);

    // Again in sv: the same three dates, at the precision the source stated,
    // in the reader's own language (LOGINS.readerSv is the one seeded login
    // whose own `locale` is Swedish).
    await signInAsSv(page, LOGINS.readerSv);
    await openChangeByStableKey(page, CHUNK5_WATCH.timelineChange);
    const timelineSv = page.locator('[data-change-timeline]');
    await expect(timelineSv.getByText('mars 2026', { exact: true })).toBeVisible();
    await expect(timelineSv.getByText('15 juni 2026', { exact: true })).toBeVisible();
    await expect(timelineSv.getByText('Kv1 2027', { exact: true })).toBeVisible();
  });

  test.fixme("WAT-S4: Types, flags and scope come from vocabularies and stay suggestions until confirmed", async () => {
    // pending: WAT-S4 (WAT-03). The library-editor confirmation this scenario needs is
    // `c5-watch-curation-confirm`, held for Alex's answer to `q-editor-confirm`
    // (docs/plans/briefs/CHUNK5_TASKS.md, "The one question left for Alex"): until then a
    // library editor's session gets `not_built` from `PATCH /changes/{changeId}`, so there
    // is no confirm control on Change facts to drive. c5-e2e-watch-journeys-b owns this
    // scenario and leaves it fixme, naming the held task.
  });

  test.fixme("WAT-S6: Links to affected obligations carry a confidence and are confirmed by a person", async () => {
    // pending: WAT-S6 (WAT-04). Blocked two ways: the library editor's half needs the same
    // held `c5-watch-curation-confirm` as WAT-S4, and the compliance officer's half needs
    // `c5-cases-so-what-and-links`, which is not on `main` yet — `POST
    // /changes/{changeId}/case/obligation-links` and its `DELETE` still answer `not_built`
    // (backend/apps/cases/links.py), and the change page's "Obligations affected" panel
    // (frontend/src/components/watch/ChangeObligations.tsx) has no accept or remove
    // control yet. c5-e2e-watch-journeys-b owns this scenario and leaves it fixme, naming
    // both blocking tasks.
  });

  test.fixme("WAT-S7: The \"So what?\" is AI-drafted until a person confirms or rewrites it per tenant", async () => {
    // pending: WAT-S7 (WAT-05). `c5-cases-so-what-and-links` is not on `main` yet: `PUT
    // /changes/{changeId}/so-what` and `POST /changes/{changeId}/so-what/confirm` still
    // answer `not_built` (backend/apps/cases/so_what.py), and the panel
    // (frontend/src/components/watch/SoWhatPanel.tsx) shows the draft read-only, with no
    // "Confirm wording" or "Rewrite" control. c5-e2e-watch-journeys-b owns this scenario
    // and leaves it fixme, naming the blocking task.
  });

  test.fixme("WAT-S8: A tenant requests a source and private sources stay private", async () => {
    // pending: WAT-S8 (WAT-06)
  });

  test('WAT-S9: The change row renders its pills in the fixed slot order', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openWatchFeed(page);

    // Seeded with urgency "within_3_months" rather than the card's own "Act
    // now" example: the same rule is proven either way, because the tone
    // comes from the ordinal and never from a string the row carries
    // (NFR-S10). The type and the flag are unconditionally suggestions here
    // (the change's own origin is an agent's), which is the fourth pill.
    const row = page.locator(`[data-change="${CHUNK5_WATCH.timelineChange}"]`);
    await expect(row).toBeVisible();
    const pills = row.locator('[data-pill]');
    await expect(pills).toHaveCount(4);
    await expect(pills.nth(0)).toHaveAttribute('data-pill', 'notice');
    await expect(pills.nth(1)).toHaveAttribute('data-pill', 'warning');
    await expect(pills.nth(2)).toHaveAttribute('data-pill', 'brand');
    await expect(pills.nth(3)).toHaveAttribute('data-pill', 'information');

    // The header adds the workflow status; the row never repeats it as a
    // pill, and the authority and date are plain meta text beside the pills.
    await expect(row.getByText('Needs triage', { exact: true })).toBeVisible();
    await expect(row.locator('[data-pill]').filter({ hasText: 'Needs triage' })).toHaveCount(0);
    // The authority's name is seeded data, not catalog copy, so it is matched
    // by pattern rather than a quoted literal (copy-drift-check.mjs).
    await expect(row.getByText(/Finansinspektionen/)).toBeVisible();
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

// ---------------------------------------------------------------------------
// The change page (chunk 5, /watch/[changeId]). What can be driven against the
// real stack today is the address itself and the read behind it: the seed has
// no watch rows, so there is no change to open. `c5-seed-watch` adds them.
// ---------------------------------------------------------------------------

test.describe('the change page', () => {
  test('an address with no change behind it says so, and offers the way back', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    // The read really answers 404: a change nobody registered and a change
    // another bank owns are the same answer, so no id can be probed for.
    apiGuard.allow(/\/api\/v1\/changes\//, 404, 'no change has this id, which is what this journey drives');
    await signInAs(page, LOGINS.complianceOfficer);

    await page.goto('/watch/00000000-0000-4000-8000-000000000000');
    await expect(page.getByRole('heading', { level: 1, name: 'Not found' })).toBeVisible();
    await expect(page.getByText('There is nothing at this address in your organisation.')).toBeVisible();

    await page.getByRole('link', { name: 'Back to Watch' }).click();
    await expect(page).toHaveURL(/\/watch$/);
    await expect(page.locator('[data-change-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
  });

  test.fixme('a change page carries its header, timeline, documents and obligations', async () => {
    // pending: `c5-seed-watch` has landed and the header, the timeline and
    // the documents are now driven directly by WAT-S2 above; the obligations
    // panel is WAT-S6, which stays fixme in this file's "watch journeys"
    // describe (blocked on `c5-watch-curation-confirm` and
    // `c5-cases-so-what-and-links`, neither on `main`). This broader,
    // non-scenario check is left fixme rather than duplicating WAT-S2's
    // assertions, and is retired once WAT-S6 makes it whole.
  });

  test.fixme('the So what reads as a draft until this bank confirms it', async () => {
    // pending: `c5-seed-watch` seeds one case with its So what confirmed and
    // one left as the library's draft, so the data this test needs exists.
    // What is still missing is `c5-cases-so-what-and-links` (WAT-S7, not on
    // `main`): the panel (SoWhatPanel.tsx) reads both states correctly
    // already, pinned by SoWhatPanel.test.tsx, but carries no confirm or
    // rewrite control yet, and `PUT /changes/{changeId}/so-what` still
    // answers `not_built`. `c5-e2e-watch-journeys-b` owns WAT-S7 itself and
    // leaves it fixme naming the same blocking task.
  });
});

// ---------------------------------------------------------------------------
// J-5's footprint half (chunk 5, c5-e2e-vocab-footprint-feed): an approved
// footprint change recomputing a case's cached `footprint_match`. VOC-S15's
// vocabulary half lives in taxonomy.journey.spec.ts; this block is the
// separate, non-scenario check the task brief names.
// ---------------------------------------------------------------------------

test.describe('the footprint recompute', () => {
  test.fixme('an approved footprint change flips a case, and the feed reflects it without a notification or a triage', async () => {
    // pending: `c5-cases-footprint-hooks` is not on `main`. `schema.sql` says
    // `change_case.footprint_match` is "recomputed when the footprint or the
    // change scope moves", but nothing recomputes it yet: there is no
    // `backend/apps/cases/matching.py`, and grepping the tree for a second
    // writer of the column finds only the one write at creation
    // (`apps/cases/creation.py`), exactly as `taxonomy.journey.spec.ts`'s own
    // FP-S4 already found and left fixme for the same reason. Approving a
    // footprint change today (J-6's own mechanism, already proved by
    // FP-S5) moves nothing on an existing case, so this journey has nothing
    // real to drive yet. Once the hook lands: sign in as the compliance
    // officer, switch a regime this bank's chunk 5 cases are scoped to off
    // through /admin/footprint, have the approver decide it
    // (`secondPerson`, as FP-S5 does), then read /watch: the default `in`
    // view drops the case by id, `footprint=all` still shows it with the
    // outside-scope marker, and no urgency, notification or triage moved
    // for it (asserted directly against the case, never inferred from the
    // screen alone).
  });
});
