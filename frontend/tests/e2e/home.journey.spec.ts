import { expect, test } from './support/api-guard';
import { LOGINS, allowFreshContext, signInAs } from './support/passkeys';

// home: the @e2e scenarios from backend/apps/home/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

// c6-e2e-seed anchors its dates to the tenant-local today (Europe/Stockholm)
// plus fixed day offsets, never a literal date (CLAUDE.md §11): the "near"
// item (the lead) is +20 days and the "far" one (the later date) is +120.
// This journey derives the same days the same way, so it passes whatever
// real day it runs on.
function seededDay(offsetDays: number): Date {
  const todayInStockholm = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const [year, month, day] = todayInStockholm.split('-').map(Number);
  return new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, (day ?? 1) + offsetDays));
}

/** As the screen's own `formatDate` renders a plain date: "D MMM YYYY", UTC. */
function seededDateText(offsetDays: number): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(seededDay(offsetDays));
}

/** As the roadmap's own `quarter_of()` computes it: "Qn YYYY". */
function seededQuarterText(offsetDays: number): string {
  const day = seededDay(offsetDays);
  return `Q${Math.floor(day.getUTCMonth() / 3) + 1} ${day.getUTCFullYear()}`;
}

const NEAR_OFFSET = 20;
const FAR_OFFSET = 120;

test.describe('home journeys', () => {
  test("HOM-S1: Today shows the next dates, the lead item, what needs a decision and source health", async ({ page, apiGuard }) => {
    // The reworded scenario (chunk 6 ruling 2): standing is chunk 8's, so it is
    // not asserted here. "A reader without watch.read gets no lead and no
    // source panel" is proved at the backend (apps/home/tests_home.py): every
    // seeded system role holds watch.read, so no E2E login can drive that step.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);

    await expect(page.getByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeVisible();

    // What the panel must show, by name and in date order, rather than by how many
    // rows it holds: the seed grows as later chunks add their own reforms, and a
    // count assertion turns every such addition into a false failure here (the
    // chunk 5 watch seed did exactly that, 2026-09-21). What this journey owns is
    // that its own cases are present, ordered, and that the out-of-scope one is not.
    const comingUp = page.locator('[data-coming-up]');
    const items = comingUp.locator('[data-roadmap-item]');
    await expect(items.filter({ hasText: 'FI adopts amended rules on paying for investment research' })).toHaveCount(1);
    await expect(items.filter({ hasText: 'Amended reporting of securities financing transactions' })).toHaveCount(1);
    await expect(items.first()).toContainText('FI adopts amended rules on paying for investment research');
    await expect(comingUp.getByText('Insurance distribution guidance outside our scope')).toHaveCount(0);
    await expect(comingUp.getByText(/\d+ dated items ahead/)).toBeVisible();

    const lead = page.locator('[data-lead-card]');
    await expect(lead.getByText('Lead', { exact: true })).toBeVisible();
    await expect(lead.getByRole('heading', { name: 'FI adopts amended rules on paying for investment research' })).toBeVisible();
    await expect(lead.getByText('Confirm the annual assessment criteria before the rules take effect.')).toBeVisible();
    // Seeded with a confirmed "So what?" (c6-e2e-seed): no AI-draft label.
    await expect(lead.getByText('Drafted by AI, not yet confirmed by a person')).toHaveCount(0);

    // Every case the seed writes starts in `new` (needs triage): the lead, the
    // later date, the out-of-scope case and last week's already-briefed one.
    const decide = page.locator('[data-decide-now]');
    // A number, not the number: the seed grows as later chunks add reforms, and what this
    // journey owns is that the panel counts triage at all (2026-09-21).
    await expect(decide.getByText(/\d+ changes? needs? triage\./)).toBeVisible();
    await expect(decide.getByText(/proposal.*pending review/)).toBeVisible();

    const sources = page.locator('[data-source-health]');
    // The panel counts the sources the seed holds, and chunk 5 added three more, so the
    // sentence is asserted by shape and the failed source this journey seeded by name.
    await expect(sources).toContainText(/Sources: \d+ of \d+ checked\./);
    await expect(sources).toContainText('EBA news feed (E2E) failed.');
  });

  test('HOM-S2: The same short list appears on a phone', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    const idsAt = async (width: number, height: number): Promise<(string | null)[]> => {
      await page.setViewportSize({ width, height });
      await page.reload();
      await expect(page.locator('[data-coming-up]')).toBeVisible();
      return page.locator('[data-coming-up] [data-roadmap-item]').evaluateAll((rows) => rows.map((row) => row.getAttribute('data-roadmap-item')));
    };

    const desktop = await idsAt(1280, 900);
    const phone = await idsAt(375, 812);

    expect(phone.length).toBeGreaterThan(0);
    expect(phone).toEqual(desktop);

    // Two action buttons share one row on a phone, the primary on the right
    // (playbook 6.8): the "Open the roadmap" link is Coming up's only action here.
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test('HOM-S3: The weekly briefing is reachable from home and snapshotted when emailed', async ({ page, apiGuard }) => {
    // The weekly job already ran for last week when the seed was written
    // (c6-e2e-seed, ruling 17: it calls the real production task), so this
    // journey opens a snapshot without waiting for the beat. "A later change
    // does not alter the snapshot" is proved at the backend
    // (apps/home/tests_scenarios.py::test_hom_s3), which an E2E journey has
    // no way to drive: nothing here can register a new change mid-run.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);

    const lead = page.locator('[data-lead-card]');
    await expect(lead.getByRole('link', { name: 'Read the briefing' })).toBeVisible();
    await expect(lead.getByText(/\d+ more items? this week/)).toBeVisible();
    await lead.getByRole('link', { name: 'Read the briefing' }).click();

    await expect(page).toHaveURL(/\/briefing$/);
    await expect(page.getByRole('heading', { level: 1, name: 'This week in brief' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'FI adopts amended rules on paying for investment research' })).toBeVisible();
    // Last week's change is not this running week's: it is absent from the
    // lead and from "Also this week", even though it may still be dated
    // ahead on "Coming up" (the same roadmap every week shares).
    await expect(page.locator('[data-lead-card]').getByText('FI starts mapping how financial firms use AI')).toHaveCount(0);
    await expect(page.locator('[data-also-this-week]').getByText('FI starts mapping how financial firms use AI')).toHaveCount(0);
    await expect(page.getByText(/^Sent /)).toHaveCount(0);

    await page.getByRole('link', { name: 'Previous week' }).click();
    await expect(page).toHaveURL(/\/briefing\/\d{4}-\d{2}-\d{2}$/);
    await expect(page.getByText(/^Sent /)).toBeVisible();
    await expect(page.getByRole('heading', { name: 'FI starts mapping how financial firms use AI' })).toBeVisible();

    await page.getByRole('link', { name: 'See this week' }).click();
    await expect(page).toHaveURL(/\/briefing$/);
  });

  test('HOM-S4: The roadmap shows the quarters ahead with their regulatory dates', async ({ page, apiGuard }) => {
    // Reworded (chunk 6 ruling 3): the internal branches ("Our deadline") have
    // no R1 producer, so only the regulatory branch is proved here.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/roadmap');

    await expect(page.getByRole('heading', { level: 1, name: 'Roadmap' })).toBeVisible();
    const roster = page.locator('[data-roadmap-roster]');
    await expect(roster.getByText(seededQuarterText(NEAR_OFFSET))).toBeVisible();
    await expect(roster.getByText(seededQuarterText(FAR_OFFSET))).toBeVisible();
    await expect(roster.getByText('FI adopts amended rules on paying for investment research')).toBeVisible();
    await expect(roster.getByText('Amended reporting of securities financing transactions')).toBeVisible();
    // Outside the regulatory scope: absent from the roadmap entirely.
    await expect(page.getByText('Insurance distribution guidance outside our scope')).toHaveCount(0);

    // Tapping a card expands it in place, without navigating.
    await page.getByRole('button', { name: /FI adopts amended rules/ }).click();
    await expect(page).toHaveURL(/\/roadmap$/);
    const detail = page.locator('[data-roadmap-detail]');
    await expect(detail.getByRole('heading', { name: 'FI adopts amended rules on paying for investment research' })).toBeVisible();

    await detail.getByRole('link', { name: 'Open change' }).click();
    await expect(page).toHaveURL(/\/watch\//);
  });

  test('HOM-S5: Upcoming changes are public facts and the calendar feed is revocable', async ({ page, apiGuard }) => {
    // The agent-key half — a key with `upcoming:read` reads `/upcoming` and
    // finds library facts, no case and no footprint of any bank's — is proved
    // at the backend (apps/home/tests_scenarios.py::test_hom_s5): an E2E
    // journey has no way to mint an agent key, and the scenario's own docstring
    // says what each half rests on. This journey drives the half a person
    // does: mint an address, prove it serves the roadmap as a calendar, revoke
    // it, and prove the same address is refused from the next fetch on.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/me/calendar-feeds');

    await expect(page.getByRole('heading', { level: 1, name: 'My calendar feeds' })).toBeVisible();
    await page.getByRole('button', { name: 'Subscribe to calendar feed' }).click();

    const address = await page.locator('[data-feed-address]').innerText();
    expect(address).toContain('/api/v1/calendar/feed.ics?token=');

    // A calendar client's own fetch: no session, no key, the address alone.
    const first = await page.evaluate(async (url) => {
      const response = await fetch(url);
      return { status: response.status, contentType: response.headers.get('content-type'), body: await response.text() };
    }, address);
    expect(first.status).toBe(200);
    expect(first.contentType ?? '').toContain('text/calendar');
    expect(first.body).toContain('BEGIN:VCALENDAR');
    expect(first.body).toContain('BEGIN:VEVENT');

    await page.getByRole('button', { name: 'Done' }).click();

    const row = page.locator('[data-feed-id]').filter({ has: page.getByRole('button', { name: 'Revoke' }) });
    await expect(row).toHaveCount(1);
    await row.getByRole('button', { name: 'Revoke' }).click();
    const dialog = page.getByRole('dialog', { name: 'Revoke this calendar feed?' });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Revoke the feed' }).click();
    await expect(dialog).toBeHidden();
    await expect(row.getByText('Revoked', { exact: true })).toBeVisible();

    apiGuard.allow(/\/calendar\/feed\.ics/, 404, 'the address was revoked and must be refused from the next fetch on (HOM-S5)');
    const second = await page.evaluate(async (url) => {
      const response = await fetch(url);
      return { status: response.status };
    }, address);
    expect(second.status).toBe(404);
  });

  test('HOM-S6: A regulatory date on the roadmap wears its urgency as a pill', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/roadmap');

    await page.getByRole('button', { name: /Amended reporting of securities financing transactions/ }).click();
    const detail = page.locator('[data-roadmap-detail]');
    await expect(detail.getByText('6+ months', { exact: true })).toBeVisible();
    // The date and the days left follow the pill as plain text, not a second pill.
    await expect(detail).toContainText(seededDateText(FAR_OFFSET));
  });
});

// PRD 0.3: My work (HOM-05, J-9) and a certificate's dates on the roadmap
// (HOM-03, TEN-02). Each stays test.fixme until the task in
// docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('my work and certificate deadlines', () => {
  test.fixme("HOM-S7: My work lists what I'm responsible for or take part in, most urgent first", async () => {
    // pending: HOM-S7 (HOM-05, AC-HOM1)
  });

  test.fixme("HOM-S9: A department head sees the department's work, naming who is responsible", async () => {
    // pending: HOM-S9 (HOM-05, TEN-02, TEN-03)
  });

  test.fixme("HOM-S13: J-9: Monday morning", async () => {
    // pending: HOM-S13 (HOM-05, COL-04, TEN-03, J-9)
  });

  test.fixme("HOM-S15: A certificate's expiry and next audit are our deadlines, never in the calendar feed", async () => {
    // pending: HOM-S15 (HOM-03, HOM-04, TEN-02, AC-TEN1)
  });
});
