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
// c8-seed-org-register and c8-ui-home-register: the remediating gap on the ESMA warnings,
// its target 60 days ahead and Johan its owner, and the certificate of Example Bank AB, its
// next audit 163 days ahead and its expiry 790, Sara its owner (apps/shared/e2e_seed.py).
const SEEDED_GAP = 'The warning can be dismissed with one tap and the choice is not logged';
const GAP_TARGET_OFFSET = 60;
const CERTIFICATE = 'ISO/IEC 27001';
const AUDIT_OFFSET = 163;
const EXPIRY_OFFSET = 790;

test.describe('home journeys', () => {
  test("HOM-S1: Today shows the next dates, the lead item, what needs a decision and source health", async ({ page, apiGuard }) => {
    // "A reader without watch.read gets no lead and no source panel", and one without
    // register.read no standing, are proved at the backend (apps/home/tests_home.py) and in
    // TodayScreen.test.tsx: every seeded system role holds both, so no E2E login can drive them.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);

    await expect(page.getByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeVisible();

    // What the panel must show, by name and in date order, rather than by how many
    // rows it holds: the seed grows as later chunks add their own reforms, and a
    // count assertion turns every such addition into a false failure here (the
    // chunk 5 watch seed did exactly that, 2026-09-21). What this journey owns is
    // that its lead case is present, the list is in date order, and the
    // out-of-scope one is not. The +120-day reform is the roadmap's to show
    // (HOM-S4): the register's own nearer dates, reviews and gap targets, fill
    // the short list ahead of it since the roadmap carries them (c8-ui-home-register).
    const comingUp = page.locator('[data-coming-up]');
    const items = comingUp.locator('[data-roadmap-item]');
    await expect(items.filter({ hasText: 'FI adopts amended rules on paying for investment research' })).toHaveCount(1);
    // Every row stated to the day, compared by its day: a quarter or a month prints no day.
    const days = (await items.allInnerTexts()).map((text) => Date.parse(`${text.split('\n')[0]} UTC`)).filter((at) => !Number.isNaN(at));
    expect(days.length).toBeGreaterThan(1);
    expect(days).toEqual([...days].sort((a, b) => a - b));
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
    // R2's decisions (x-decide-now-counts): the officer holds risk.accept.approve, and neither
    // cases.signoff nor security.manage, so only the risk line is theirs.
    await expect(decide.getByRole('link', { name: /\d+ risk acceptances? to approve\./ })).toHaveAttribute('href', '/gaps');
    await expect(decide.getByText(/waiting for your sign-off/)).toHaveCount(0);
    await expect(decide.getByText(/support access requests? to decide/)).toHaveCount(0);
    await expect(decide.getByText(/tenant reach requests? to decide/)).toHaveCount(0);

    const sources = page.locator('[data-source-health]');
    // The panel counts the sources the seed holds, and chunk 5 added three more, so the
    // sentence is asserted by shape and the failed source this journey seeded by name.
    await expect(sources).toContainText(/Sources: \d+ of \d+ checked\./);
    await expect(sources).toContainText('EBA news feed (E2E) failed.');

    // Where we stand (c8-ui-home-register): a number per line, not the number, because other
    // journeys record statuses and gaps as they run. Each line leads to the list it counts.
    const standing = page.locator('[data-standing]');
    await expect(standing.getByRole('heading', { name: 'Where we stand' })).toBeVisible();
    await expect(standing.getByRole('link', { name: /^\d+ obligations? appl(y|ies) to us\.$/ })).toHaveAttribute('href', '/inventory?applicability=applies');
    for (const [name, key] of [
      ['Compliant', 'compliant'],
      ['Partly compliant', 'partly_compliant'],
      ['Gap', 'gap'],
      ['Not assessed', 'not_assessed'],
    ] as const) {
      await expect(standing.getByRole('link', { name, exact: true })).toHaveAttribute('href', `/inventory?applicability=applies&complianceStatus=${key}`);
    }
    await expect(standing.locator('[data-standing-line="partly"]')).toContainText(/Partly compliant\s*[1-9]\d*/);
    await expect(standing.getByText(/^\d+ gaps? open or in remediation$/)).toBeVisible();

    await standing.getByRole('link', { name: 'Partly compliant', exact: true }).click();
    await expect(page).toHaveURL(/\/inventory\?applicability=applies&complianceStatus=partly_compliant$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Inventory' })).toBeVisible();
    await page.goBack();
    await page.locator('[data-standing]').getByRole('link', { name: 'See the gaps' }).click();
    await expect(page).toHaveURL(/\/gaps$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Gaps' })).toBeVisible();
  });

  // What needs a decision is counted per person: each line is one the reader's permissions
  // unlock, and each leads to where that decision is made. A number, not the number: other
  // journeys add and decide these requests as they run.
  test('HOM-S1: Decide now shows an approver the sign-offs and risk acceptances they may decide', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.approver);

    const decide = page.locator('[data-decide-now]');
    await expect(decide.getByRole('link', { name: /\d+ cases? waiting for your sign-off\./ })).toHaveAttribute('href', '/watch?tab=inProgress');
    await expect(decide.getByRole('link', { name: /\d+ risk acceptances? to approve\./ })).toHaveAttribute('href', '/gaps');
    await expect(decide.getByText(/support access requests? to decide/)).toHaveCount(0);
    await expect(decide.getByText(/needs? triage/)).toHaveCount(0);
  });

  test('HOM-S1: Decide now shows an admin the support access and tenant reach requests to decide', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);

    const decide = page.locator('[data-decide-now]');
    await expect(decide.getByRole('link', { name: /\d+ support access requests? to decide\./ })).toHaveAttribute('href', '/admin/support-access');
    await expect(decide.getByRole('link', { name: /\d+ tenant reach requests? to decide\./ })).toHaveAttribute('href', '/admin/security');
    await expect(decide.getByText(/waiting for your sign-off/)).toHaveCount(0);
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
    // The regulatory branch, then the bank's own deadlines beside it (c8-ui-home-register):
    // the seeded gap's target, named with what it is and its owner, opening its obligation.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/roadmap');

    await expect(page.getByRole('heading', { level: 1, name: 'Roadmap' })).toBeVisible();
    const roster = page.locator('[data-roadmap-roster]');
    // By heading: a card whose date was stated as a quarter prints the same words.
    await expect(roster.getByRole('heading', { name: seededQuarterText(NEAR_OFFSET), exact: true })).toBeVisible();
    await expect(roster.getByRole('heading', { name: seededQuarterText(FAR_OFFSET), exact: true })).toBeVisible();
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

    await page.goto('/roadmap');
    await page.getByRole('button', { name: 'Our deadlines' }).click();
    await expect(page).toHaveURL(/\/roadmap\?kind=internal$/);
    const target = page.locator('[data-roadmap-card^="gap_target:"]').filter({ hasText: SEEDED_GAP });
    await expect(target).toContainText('Our deadline · Gap target date · Johan Berg');
    await expect(target).toContainText(seededDateText(GAP_TARGET_OFFSET));
    // Only our own: no regulatory date under this chip.
    await expect(page.locator('[data-roadmap-card^="change_date:"]')).toHaveCount(0);
    await target.click();
    const ours = page.locator('[data-roadmap-detail]');
    await expect(ours.getByRole('heading', { name: SEEDED_GAP })).toBeVisible();
    await expect(ours.locator('[data-our-deadline]')).toContainText('Johan Berg');
    await ours.getByRole('link', { name: 'Open obligation' }).click();
    await expect(page).toHaveURL(/\/inventory\/obligations\//);
  });

  test('HOM-S5: Upcoming changes are public facts and the calendar feed is revocable', async ({ page, apiGuard }) => {
    // The agent half (a key with upcoming:read reads /upcoming and finds library
    // facts and nothing of any bank's) is proved at the backend
    // (apps/home/tests_scenarios.py::test_hom_s5), not repeated here. This
    // journey drives the half a person does: subscribe from the roadmap, prove
    // the address serves the roadmap as a calendar of public facts, revoke it,
    // and prove the same address is refused from the next fetch on.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/roadmap');
    await page.getByRole('link', { name: 'Subscribe to calendar feed' }).click();
    await expect(page).toHaveURL(/\/me\/calendar-feeds$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Calendar feeds' })).toBeVisible();

    // Pinned by the id this run created: a revoked feed stays listed, so an
    // earlier attempt's row must not match (playbook 8.3 rule 4).
    const answered = page.waitForResponse((r) => r.url().endsWith('/api/v1/calendar-feeds') && r.request().method() === 'POST' && r.ok());
    await page.getByRole('button', { name: 'New feed' }).click();
    const { feed } = (await (await answered).json()) as { feed: { id: string } };
    const row = page.locator(`[data-feed-id="${feed.id}"]`);
    const revokeRow = async () => {
      await row.getByRole('button', { name: /^Revoke the feed created / }).click();
      const confirm = page.getByRole('dialog', { name: /^Revoke the feed created .+\?$/ });
      await confirm.getByRole('button', { name: 'Revoke', exact: true }).click();
      await expect(confirm).toBeHidden();
      await expect(row.getByText('Revoked', { exact: true })).toBeVisible();
    };
    try {
      const shown = page.getByRole('dialog', { name: 'Copy this address into your calendar' });
      await expect(shown).toBeVisible();
      const address = (await shown.locator('[data-feed-address]').innerText()).trim();
      const token = new URL(address).searchParams.get('token') ?? '';
      expect(new URL(address).pathname).toBe('/api/v1/calendar/feed.ics');
      expect(token).toMatch(/^[^.]+\.[^.]+$/);
      expect(page.url()).not.toContain(token);

      // A calendar client's own fetch: the address alone, no session and no key.
      const served = await page.request.get(address);
      expect(served.status()).toBe(200);
      expect(served.headers()['content-type']).toContain('text/calendar');
      // RFC 5545 folds a line longer than 75 octets onto the next, which starts
      // with a space; a calendar client reads it as one line, so this does too.
      const ics = (await served.text()).replace(/\r\n[ \t]/g, '');
      expect(ics).toContain('BEGIN:VCALENDAR');
      expect(ics).toContain('SUMMARY:In force: FI adopts amended rules on paying for investment research\r\n');
      // Public facts only: the bank's own "So what?" never travels in a
      // calendar, and nothing outside the regulatory scope is in it.
      expect(ics).not.toContain('Confirm the annual assessment criteria');
      expect(ics).not.toContain('Insurance distribution guidance outside our scope');

      await shown.getByRole('button', { name: 'Done' }).click();
      await expect(shown).toBeHidden();
      // Shown once: neither the list nor a reload shows the address again.
      await page.reload();
      await expect(row.getByText('Active', { exact: true })).toBeVisible();
      await expect(page.getByText(token)).toHaveCount(0);

      await revokeRow();
      // Asserted on the answer itself: page.request bypasses the page's
      // response listener, so the guard never sees this 404. The allow still
      // declares it where it happens, should the fetch ever move to the page.
      apiGuard.allow(/\/calendar\/feed\.ics/, 404, 'the address was revoked, so it is refused from the next fetch on (HOM-S5)');
      const refused = await page.request.get(address);
      expect(refused.status()).toBe(404);
      expect(await refused.text()).not.toContain('BEGIN:VCALENDAR');
    } finally {
      // Teardown that runs on failure too: a live address never outlives the attempt.
      await page.goto('/me/calendar-feeds');
      await expect(row).toBeVisible();
      if ((await row.getByRole('button', { name: /^Revoke the feed created / }).count()) > 0) await revokeRow();
    }
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

    // One of our own deadlines wears "Our deadline" in the brand tone instead of an urgency.
    await page.locator('[data-roadmap-card^="gap_target:"]').filter({ hasText: SEEDED_GAP }).click();
    const ours = page.locator('[data-roadmap-detail]');
    await expect(ours.locator('[data-pill="brand"]')).toHaveText('Our deadline');
    await expect(ours.locator('[data-pill]')).toHaveCount(1);
    await expect(ours).toContainText(seededDateText(GAP_TARGET_OFFSET));
    await expect(ours).toContainText(/in \d+ days/);
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

  test.fixme("HOM-S13 J-9 @smoke: Monday morning", async () => {
    // pending: HOM-S13 (HOM-05, COL-04, TEN-03, J-9)
  });

  test("HOM-S15: A certificate's expiry and next audit are our deadlines, never in the calendar feed", async ({ page, apiGuard }) => {
    // HOM-S15 (HOM-03, HOM-04, TEN-02, AC-TEN1): the seeded certificate's next audit and its
    // expiry are on the roadmap as our deadlines, with the owner, the certificate and its
    // legal entity, and a calendar feed carries neither. "When the licence is withdrawn,
    // neither date appears" is proved at the backend (apps/home/tests_scenarios.py
    // ::test_hom_s15): no screen withdraws a certificate yet (the organisation screen's
    // licences are c8-ui-organisation's), and a journey never writes around the UI.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/roadmap?kind=internal');

    const audit = page.locator('[data-roadmap-card^="certificate_audit:"]').filter({ hasText: CERTIFICATE });
    const expiry = page.locator('[data-roadmap-card^="certificate_expiry:"]').filter({ hasText: CERTIFICATE });
    await expect(audit).toContainText('Our deadline · Certificate audit · Sara Lindqvist');
    await expect(audit).toContainText(seededDateText(AUDIT_OFFSET));
    await expect(page.getByRole('heading', { name: seededQuarterText(AUDIT_OFFSET), exact: true })).toBeVisible();
    await expect(expiry).toContainText('Our deadline · Certificate expires · Sara Lindqvist');
    await expect(expiry).toContainText(seededDateText(EXPIRY_OFFSET));
    await expect(page.getByRole('heading', { name: seededQuarterText(EXPIRY_OFFSET), exact: true })).toBeVisible();

    await audit.click();
    const detail = page.locator('[data-roadmap-detail]');
    await expect(detail.locator('[data-pill="brand"]')).toHaveText('Our deadline');
    const facts = detail.locator('[data-our-deadline]');
    await expect(facts).toContainText('Certificate audit');
    await expect(facts).toContainText('Sara Lindqvist');
    await expect(facts).toContainText('Example Bank AB');

    // Never in the calendar feed: a feed made now carries the regulatory dates and neither of these.
    await page.getByRole('link', { name: 'Subscribe to calendar feed' }).click();
    await expect(page).toHaveURL(/\/me\/calendar-feeds$/);
    const answered = page.waitForResponse((r) => r.url().endsWith('/api/v1/calendar-feeds') && r.request().method() === 'POST' && r.ok());
    await page.getByRole('button', { name: 'New feed' }).click();
    const { feed } = (await (await answered).json()) as { feed: { id: string } };
    const row = page.locator(`[data-feed-id="${feed.id}"]`);
    try {
      const shown = page.getByRole('dialog', { name: 'Copy this address into your calendar' });
      const address = (await shown.locator('[data-feed-address]').innerText()).trim();
      const served = await page.request.get(address);
      expect(served.status()).toBe(200);
      const ics = (await served.text()).replace(/\r\n[ \t]/g, '');
      expect(ics).toContain('SUMMARY:In force: FI adopts amended rules on paying for investment research\r\n');
      const compact = (offset: number) => seededDay(offset).toISOString().slice(0, 10).replaceAll('-', '');
      for (const absent of [CERTIFICATE, 'Sara Lindqvist', compact(AUDIT_OFFSET), compact(EXPIRY_OFFSET)]) expect(ics).not.toContain(absent);
      await shown.getByRole('button', { name: 'Done' }).click();
      await expect(shown).toBeHidden();
    } finally {
      // Teardown that runs on failure too: a live address never outlives the attempt.
      await page.goto('/me/calendar-feeds');
      await expect(row).toBeVisible();
      if ((await row.getByRole('button', { name: /^Revoke the feed created / }).count()) > 0) {
        await row.getByRole('button', { name: /^Revoke the feed created / }).click();
        const confirm = page.getByRole('dialog', { name: /^Revoke the feed created .+\?$/ });
        await confirm.getByRole('button', { name: 'Revoke', exact: true }).click();
        await expect(row.getByText('Revoked', { exact: true })).toBeVisible();
      }
    }
  });
});
