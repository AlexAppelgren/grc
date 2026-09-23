import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs, signOut } from './support/passkeys';
import { CHUNK5_WATCH, consoleSourceRow, openChangeByStableKey, openWatchFeed, signInAsSv } from './support/watch-coverage';
import { openChangeFromFeed } from './support/watch-facts';

// watch: the @e2e scenarios from backend/apps/watch/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// No step here reads a date relative to today. The dates asserted are the
// source's own, seeded fixed (WAT-S2's March 2026, 15 June 2026 and Q1 2027),
// and a confirmation's date is matched by its shape, so no answer changes as
// the calendar moves past a seeded date such as 1 October 2026.

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
    await expect(timelineSv.getByText('kv. 1 2027', { exact: true })).toBeVisible();
  });

  test.fixme("WAT-S4: Types, flags and scope come from vocabularies and stay suggestions until confirmed", async () => {
    // pending: WAT-S4 (WAT-03). The library-editor confirmation this scenario needs is
    // `c5-watch-curation-confirm`, held for Alex's answer to `q-editor-confirm`
    // (docs/plans/briefs/CHUNK5_TASKS.md, "The one question left for Alex"): until then a
    // library editor's session gets `not_built` from `PATCH /changes/{changeId}`, so there
    // is no confirm control on Change facts to drive. c5-e2e-watch-journeys-b owns this
    // scenario and leaves it fixme, naming the held task.
  });

  // Both journeys below spend the seeded state they drive: a confirmed "So what?" and a
  // decided link cannot be put back to undecided through any route, by design. A retry
  // would run against what the first attempt already decided and fail for that, not for the
  // real cause, so, like the member ADM-S2 spends, they never retry: the first failure is
  // the real one. They share one change and touch different parts of this bank's case, so
  // they may run side by side. What they write is tenant A's alone; tenant B only reads.
  test.describe('what this bank decides on its own case', () => {
    test.describe.configure({ retries: 0 });

    test("WAT-S6: Links to affected obligations carry a confidence, and the library and the bank decide separately", async ({ page, apiGuard }) => {
      // The bank's half. The library editor's half (confirming the first link for every
      // bank) is the curation confirmation, which a later task adds to this journey; the
      // seed stands in for it with one link a library editor already confirmed and one still
      // an agent's suggestion (`c5-seed-watch`, backend/apps/shared/e2e_seed.py). That both
      // decisions are audited is asserted by the @integration half
      // (apps/watch/tests_scenarios.py::test_wat_s6): the audit log's record-kind filter
      // offers no case kind yet, and an unfiltered log is shared with every parallel journey.
      allowFreshContext(apiGuard);
      await signInAs(page, LOGINS.complianceOfficer);
      const changeId = await openChangeFromFeed(page, CHUNK5_WATCH.obligationsChange);

      // Each link is found by what it is, never by its title: titles are library rows.
      const panel = page.locator('[data-change-obligations]');
      const libraryConfirmed = panel.locator('[data-obligation]').filter({ has: page.getByText('Confirmed by a library editor', { exact: true }) });
      const suggestion = panel.locator('[data-obligation]').filter({ has: page.getByText(/^Suggested, \d+% match$/) });
      await expect(libraryConfirmed).toHaveCount(1);
      await expect(suggestion).toHaveCount(1);
      const first = (await libraryConfirmed.getAttribute('data-obligation')) ?? '';
      const second = (await suggestion.getAttribute('data-obligation')) ?? '';
      const link = (obligationId: string) => panel.locator(`[data-obligation="${obligationId}"]`);
      // Nothing is decided for this bank yet, so both offer the bank's own two answers.
      await expect(link(first).getByRole('button', { name: 'Confirm link' })).toBeVisible();
      await expect(link(second).getByRole('button', { name: 'Not related' })).toBeVisible();

      // When a compliance officer accepts the first on their own bank's case
      await link(first).getByRole('button', { name: 'Confirm link' }).click();
      await expect(link(first)).toHaveAttribute('data-case-decision', 'accepted');
      await expect(link(first).getByText(/^Confirmed for us, .+ \d{4}$/)).toBeVisible();
      await expect(link(first).getByRole('button')).toHaveCount(0);

      // And removes the second: it is hidden from this bank's change page
      await link(second).getByRole('button', { name: 'Not related' }).click();
      await expect(link(second)).toHaveCount(0);

      // Both are stored on the case, not only drawn: a fresh read says the same.
      await page.reload();
      await expect(link(first)).toHaveAttribute('data-case-decision', 'accepted');
      await expect(link(second)).toHaveCount(0);

      // "The obligation shows 1 open change" is not walked here: no screen mounts the
      // obligation's related-changes panel yet (the obligation page still shows its "later
      // release" placeholder), so there is nothing to open. The @integration half reads the
      // count from `GET /obligations/{obligationId}/changes`; the step joins this journey
      // when the panel is mounted (watch/app.md, the note under WAT-S6).

      // And no library row changed: another bank still sees both links, the first as the
      // library editor confirmed it, the second still a suggestion, and neither decided.
      await signOut(page);
      await signInAs(page, LOGINS.secondBankAdmin);
      await page.goto(`/watch/${changeId}`);
      const theirs = page.locator('[data-change-obligations]');
      await expect(theirs.locator(`[data-obligation="${first}"]`).getByText('Confirmed by a library editor', { exact: true })).toBeVisible();
      await expect(theirs.locator(`[data-obligation="${second}"]`).getByText(/^Suggested, \d+% match$/)).toBeVisible();
      await expect(theirs.locator('[data-case-decision]')).toHaveCount(0);
      // An administrator holds no cases.work, so the bank's two answers are not offered.
      await expect(theirs.getByRole('button')).toHaveCount(0);
    });

    test("WAT-S7: The \"So what?\" is AI-drafted until a person confirms or rewrites it per tenant", async ({ page, apiGuard }) => {
      allowFreshContext(apiGuard);
      await signInAs(page, LOGINS.complianceOfficer);
      const changeId = await openChangeFromFeed(page, CHUNK5_WATCH.obligationsChange);

      // Given a change whose registering run filed a drafted "So what?" with it: this
      // bank's copy carries the AI label and names the agent that drafted it.
      const soWhat = page.locator('[data-so-what]');
      await expect(soWhat.getByText('Drafted by AI, not yet confirmed by a person')).toBeVisible();
      await expect(soWhat.getByText(/^Drafted by .+, which read this change$/)).toBeVisible();
      await expect(soWhat).not.toHaveAttribute('data-so-what-confirmed');
      const draft = await soWhat.locator('[data-so-what-text]').innerText();

      // When the compliance officer chooses "Confirm wording"
      await soWhat.getByRole('button', { name: 'Confirm wording' }).click();
      // Then this bank's copy is confirmed with its time, and the words stay the draft's
      await expect(soWhat).toHaveAttribute('data-so-what-confirmed', '');
      await expect(soWhat.getByText('Drafted by AI, not yet confirmed by a person')).toHaveCount(0);
      await expect(soWhat.getByText(/^Confirmed .+ \d{4}$/)).toBeVisible();
      await expect(soWhat.locator('[data-so-what-text]')).toHaveText(draft);
      await expect(soWhat.getByRole('button', { name: 'Confirm wording' })).toHaveCount(0);

      // Or rewrites and chooses "Save and confirm": the bank's own words replace the draft
      const ours = 'Check the ICT register against every third-party arrangement before the standards apply.';
      await soWhat.getByRole('button', { name: 'Rewrite' }).click();
      const box = page.getByRole('textbox', { name: 'So what?' });
      await expect(box).toHaveValue(draft);
      await box.fill(ours);
      await page.getByRole('button', { name: 'Save and confirm' }).click();
      await expect(page.locator('[data-so-what] [data-so-what-text]')).toHaveText(ours);
      await expect(page.locator('[data-so-what]')).toHaveAttribute('data-so-what-confirmed', '');

      // Stored, not only drawn: a fresh read says the same.
      await page.reload();
      await expect(page.locator('[data-so-what] [data-so-what-text]')).toHaveText(ours);
      await expect(page.locator('[data-so-what]').getByText('Drafted by AI, not yet confirmed by a person')).toHaveCount(0);

      // And another tenant's copy is still the draft, with its label, and never our words
      await signOut(page);
      await signInAs(page, LOGINS.secondBankAdmin);
      await page.goto(`/watch/${changeId}`);
      const theirs = page.locator('[data-so-what]');
      await expect(theirs.getByText('Drafted by AI, not yet confirmed by a person')).toBeVisible();
      await expect(theirs).not.toHaveAttribute('data-so-what-confirmed');
      await expect(theirs.locator('[data-so-what-text]')).toHaveText(draft);
      // An administrator holds no cases.work: the label and no buttons.
      await expect(theirs.getByRole('button')).toHaveCount(0);
    });
  });

  test.fixme("WAT-S8: A tenant requests a source and private sources stay private", async () => {
    // pending: WAT-S8 (WAT-06, chunk 13)
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

  // "The Coverage tab lists each source with its last check and its stale marker" was
  // retired here on 2026-09-23 rather than un-fixme'd: WAT-S1 above drives exactly that
  // tab against the real registry (the healthy source checked, the failing one stale with
  // its error named), so a second journey would only repeat it at the cost of a sign-in.

  test('a change row carries its pills, its So what and its key date', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openFeed(page);

    // The timeline change: this bank confirmed its "So what?" in the seed and no journey
    // writes it, so the row carries the bank's settled wording without the AI label.
    const row = page.locator(`[data-change="${CHUNK5_WATCH.timelineChange}"]`);
    await expect(row.locator('[data-pill]').first()).toHaveAttribute('data-pill', 'notice');
    await expect(row.getByText('So what?', { exact: true })).toBeVisible();
    await expect(row.getByText('Drafted by AI, not yet confirmed by a person')).toHaveCount(0);
    // The key date at the precision the source stated, a quarter and never a day. The
    // label and the quarter are seeded data, so they are matched by pattern.
    await expect(row.getByText(/^In force Q1 2027$/)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// The change page (chunk 5, /watch/[changeId]): the address itself, and the
// page whole against `c5-seed-watch`'s timeline change, which no journey
// writes. What a bank decides on its own case is WAT-S6 and WAT-S7 above.
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

  test('a change page carries its header, timeline, documents and obligations', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openChangeFromFeed(page, CHUNK5_WATCH.timelineChange);

    // The header: the type first, as a notice, and the case's status as information.
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.locator('[data-pill]').first()).toHaveAttribute('data-pill', 'notice');
    await expect(page.getByText('Needs triage', { exact: true })).toHaveAttribute('data-pill', 'information');

    // This bank confirmed the wording, so it carries no AI label; a person with
    // cases.work may still rewrite it, and is never asked to confirm it twice.
    const soWhat = page.locator('[data-so-what]');
    await expect(soWhat).toHaveAttribute('data-so-what-confirmed', '');
    await expect(soWhat.getByRole('button', { name: 'Rewrite' })).toBeVisible();
    await expect(soWhat.getByRole('button', { name: 'Confirm wording' })).toHaveCount(0);

    // The timeline, the page it was found on (opened safely, as text), the obligations it
    // affects (none are linked to this one) and the record's own stable key.
    await expect(page.locator('[data-change-timeline]')).toBeVisible();
    const document = page.locator('[data-change-documents] [data-document]').first().getByRole('link');
    await expect(document).toHaveAttribute('rel', 'noopener noreferrer');
    await expect(document).toHaveAttribute('target', '_blank');
    await expect(page.getByText('No obligation is linked yet')).toBeVisible();
    await expect(page.locator('code', { hasText: CHUNK5_WATCH.timelineChange })).toBeVisible();
  });

  // "The So what reads as a draft until this bank confirms it" was retired here on
  // 2026-09-23 rather than un-fixme'd: WAT-S7 above drives that path end to end, a draft
  // with its label, confirmed and rewritten by one bank, and still the draft for the other.
});

// ---------------------------------------------------------------------------
// J-5's footprint half ("an approved footprint change flips a case, and the feed reflects
// it without a notification or a triage") was a fixme block here until 2026-09-23, and was
// retired rather than un-fixme'd, for three reasons:
// - The recompute it waited for landed (`apps/cases/matching.py`, 6fe3929) and is proved
//   where it runs: `apps/cases/tests_matching.py` approves a footprint change and asserts
//   that only the cases it should flip do, that nothing else on them moves and that each
//   bank gets one audit row; `apps/taxonomy/tests_scenarios.py::test_fp_s4` proves the
//   roadmap and the briefing, the two surfaces that read the cached verdict, follow it.
// - The feed cannot show the recompute: it decides the footprint per request from the
//   change's scope terms (`apps/watch/reading.py`, `taxonomy_in_footprint`) and never reads
//   the cached `footprint_match`, so a feed walk would pass with or without it.
// - Driving it here would switch tenant A's footprint while every journey in this file
//   reads that footprint in parallel, so it would race them.
// The screen walk across the surfaces after a footprint change is FP-S4's own journey in
// taxonomy.journey.spec.ts, which is still test.fixme and owned there.
// ---------------------------------------------------------------------------
