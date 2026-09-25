import type { Browser, Locator, Page, TestInfo } from '@playwright/test';

import { expect, test, type ApiGuard } from './support/api-guard';
import { LOGINS, allowFreshContext, signInAs } from './support/passkeys';

// register: the @e2e scenarios from backend/apps/register/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

// c8-ui-gaps-risk: the obligations REG-S5 and REG-S6 record their gaps on, each
// found in the inventory under its instrument (apps/library/fixtures). Both
// apply to tenant A: the ESMA warnings with status Gap, costs and charges partly.
const ESMA = 'obl-esma-warnings';
const ESMA_INSTRUMENT = 'esma-35-43-3006';
const COSTS = 'obl-costs-charges';
const COSTS_INSTRUMENT = 'fffs-2017-2';

/** The inventory under one instrument, then one card by stable key: the row's link carries the id. */
async function openObligation(page: Page, instrument: string, stableKey: string): Promise<void> {
  await page.goto(`/inventory?instrument=${instrument}`);
  await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
  await page.locator(`[data-obligation="${stableKey}"]`).click();
  await expect(page.locator('[data-gaps-panel]')).toBeVisible();
}

/** A plain date `days` from today where tenant A is (Europe/Stockholm), as a date input takes it. */
function localDate(days: number): string {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const at = new Date(`${today}T12:00:00Z`);
  at.setUTCDate(at.getUTCDate() + days);
  return at.toISOString().slice(0, 10);
}

async function recordGap(page: Page, gap: { title: string; severity: string; target: string; plan: string }): Promise<void> {
  await page.locator('[data-gaps-panel]').getByRole('button', { name: 'Record a gap' }).click();
  const form = page.getByRole('dialog', { name: 'Record a gap' });
  await form.getByLabel('Title').fill(gap.title);
  await form.getByLabel('Severity').selectOption({ label: gap.severity });
  await form.getByLabel('Target date').fill(gap.target);
  await form.getByLabel('Remediation plan').fill(gap.plan);
  await form.getByRole('button', { name: 'Record gap' }).click();
  await expect(form).toHaveCount(0);
}

/** One gap on the obligation's panel, by its title. */
function gapRow(page: Page, title: string): Locator {
  return page.locator('[data-gaps-panel] [data-gap]').filter({ has: page.getByRole('button', { name: title, exact: true }) });
}

function pill(scope: Locator, label: string): Locator {
  return scope.locator('[data-pill]').filter({ hasText: new RegExp(`^${label}$`) }).first();
}

/** Closes a gap still open or under way, from its record; anything else is left as it is. */
async function closeGap(gap: Locator): Promise<void> {
  const page = gap.page();
  if ((await gap.count()) === 0) return;
  const way = gap.locator('[data-gap-way-out]');
  if ((await way.count()) === 0) await gap.locator('[data-gap-toggle]').click();
  const start = way.getByRole('button', { name: 'Start remediation' });
  if (await start.isVisible()) {
    await start.click();
    await expect(pill(gap, 'Remediating')).toBeVisible();
  }
  const close = way.getByRole('button', { name: 'Close gap' });
  if (!(await close.isVisible())) return;
  await close.click();
  await page.getByRole('dialog', { name: 'Close this gap?' }).getByRole('button', { name: 'Close gap' }).click();
  await expect(pill(gap, 'Closed')).toHaveAttribute('data-pill', 'positive');
}

async function secondPerson(browser: Browser, apiGuard: ApiGuard, testInfo: TestInfo, login: string): Promise<Page> {
  const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
  const page = await context.newPage();
  apiGuard.watch(page);
  await signInAs(page, login);
  return page;
}

test.describe('register journeys', () => {
  test.fixme("REG-S1: One compliance person sets applicability after confirming it", async () => {
    // pending: REG-S1 (REG-01)
  });

  test.fixme("REG-S3: Compliance status and its details are kept per legal entity", async () => {
    // pending: REG-S3 (REG-02)
  });

  // c8-ui-gaps-risk: REG-S5 and REG-S6 on the obligation page's Gaps panel,
  // each on a gap it records itself, so a re-run and the seeded gaps never meet.
  test("REG-S5: A gap has an owner, severity, target date and remediation", async ({ page, apiGuard }, testInfo) => {
    // REG-S5 (REG-03): the owner records a high gap on an obligation whose
    // status is Gap, sees Open and High in the negative tone with its source,
    // and starts remediation, which reads Remediating as warning. The roadmap
    // lists its target as "Our deadline" (c8-ui-home-register).
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.owner);
    await openObligation(page, ESMA_INSTRUMENT, ESMA);
    const title = `The warning choice is not kept with the order, attempt ${testInfo.retry}`;
    await recordGap(page, { title, severity: 'High', target: localDate(60), plan: 'Store the client\'s choice with the order.' });

    const gap = gapRow(page, title);
    try {
      await expect(pill(gap, 'Open')).toHaveAttribute('data-pill', 'negative');
      await expect(pill(gap, 'High')).toHaveAttribute('data-pill', 'negative');
      await expect(gap.locator('[data-pill]')).toHaveCount(3);
      await expect(gap.getByText('Johan Berg', { exact: true }).first()).toBeVisible();
      await expect(gap.locator('[data-target-line]')).toHaveText(/^Target .+, in \d+ days$/);
      await expect(gap.locator('[data-gap-plan]')).toHaveText("Store the client's choice with the order.");

      await gap.getByRole('button', { name: 'Start remediation' }).click();
      await expect(gap.getByText('Remediation started.')).toBeVisible();
      await expect(pill(gap, 'Remediating')).toHaveAttribute('data-pill', 'warning');

      await page.goto('/roadmap?kind=internal');
      const target = page.locator('[data-roadmap-card^="gap_target:"]').filter({ hasText: title });
      await expect(target).toContainText('Our deadline · Gap target date · Johan Berg');
      await target.click();
      const detail = page.locator('[data-roadmap-detail]');
      await expect(detail.locator('[data-pill="brand"]')).toHaveText('Our deadline');
      await detail.getByRole('link', { name: 'Open obligation' }).click();
      await expect(page.locator('[data-gaps-panel]')).toBeVisible();
    } finally {
      // On a failure too: the recorded gap leaves no open work behind, from its obligation's page.
      if ((await page.locator('[data-gaps-panel]').count()) === 0) await openObligation(page, ESMA_INSTRUMENT, ESMA);
      await closeGap(gap);
    }
  });

  test("REG-S6: Risk acceptance is behind four eyes with step-up", async ({ page, browser, apiGuard }, testInfo) => {
    // REG-S6 (REG-03): a compliance officer asks to accept the risk of an
    // open gap with a reason from the bank's list; the gap waits and its status
    // does not move. The officer is offered no approval of their own request
    // (the server's 409 four_eyes_violation, and the CHECK behind it, are
    // REG-S6's @integration test). A different holder of risk.accept.approve
    // approves with a passkey step-up, and the gap reads Risk accepted in the
    // information tone with both names, and Reopen.
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/api\/v1\/gaps\/[^/]+\/accept-risk\/approve$/, 403, 'the first attempt answers step_up_required and opens the prompt');
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, COSTS_INSTRUMENT, COSTS);
    const title = `Exchange cost is left out of the ex post report, attempt ${testInfo.retry}`;
    await recordGap(page, { title, severity: 'Medium', target: localDate(90), plan: 'Add the exchange cost to the yearly report.' });

    const gap = gapRow(page, title);
    await gap.getByRole('button', { name: 'Accept the risk' }).click();
    const ask = page.getByRole('dialog', { name: 'Ask to accept the risk' });
    await ask.getByLabel('Reason').selectOption({ label: 'Compensating control' });
    await ask.getByRole('button', { name: 'Ask for approval' }).click();
    await expect(gap.getByText('Asked for approval.')).toBeVisible();
    const way = gap.locator('[data-gap-way-out]');
    await expect(pill(way, 'Waiting for approval')).toHaveAttribute('data-pill', 'warning');
    await expect(pill(gap, 'Open')).toHaveAttribute('data-pill', 'negative');
    await expect(way.getByText('You asked for this, so someone else has to approve it.')).toBeVisible();
    await expect(way.getByRole('button', { name: 'Approve with passkey' })).toHaveCount(0);

    const approver = await secondPerson(browser, apiGuard, testInfo, LOGINS.approver);
    try {
      await openObligation(approver, COSTS_INSTRUMENT, COSTS);
      const theirs = gapRow(approver, title);
      await theirs.locator('[data-gap-toggle]').click();
      const theirWay = theirs.locator('[data-gap-way-out]');
      await expect(theirWay.getByText(/^Sara Lindqvist asks to accept the risk, /)).toBeVisible();
      await expect(theirWay.getByText('Compensating control')).toBeVisible();
      await theirWay.getByRole('button', { name: 'Approve with passkey' }).click();
      await approver.getByRole('dialog', { name: `Accept the risk of "${title}"?` }).getByRole('button', { name: 'Approve with passkey' }).click();
      // Step-up: settle on the prompt or the outcome, since a sign-in moments ago may still count.
      const prompt = approver.getByRole('dialog', { name: 'Confirm with your passkey' });
      const done = theirs.getByText('Risk accepted.');
      await expect(prompt.or(done).first()).toBeVisible();
      if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
      await expect(done).toBeVisible();
      await expect(pill(theirs, 'Risk accepted')).toHaveAttribute('data-pill', 'information');
      await expect(theirWay.getByText(/^Risk accepted by Maria .+ on .+, asked by Sara Lindqvist\.$/)).toBeVisible();
      // Reopening is gaps.edit's, which the approver does not hold and the officer does.
      await expect(theirWay.getByRole('button', { name: 'Reopen' })).toHaveCount(0);
    } finally {
      await approver.context().close();
    }
    await page.reload();
    await gapRow(page, title).locator('[data-gap-toggle]').click();
    await expect(pill(gapRow(page, title), 'Risk accepted')).toHaveAttribute('data-pill', 'information');
    await expect(way.getByRole('button', { name: 'Reopen' })).toBeVisible();
  });

  test.fixme("REG-S7: Assessment history and \"How we read this rule\" are kept per obligation", async () => {
    // pending: REG-S7 (REG-04)
  });

  test.fixme("REG-S8: Linked internal items carry external references", async () => {
    // pending: REG-S8 (REG-05)
  });

  test.fixme("REG-S9: Yearly attestation and waivers", async () => {
    // pending: REG-S9 (REG-06)
  });
});

// PRD 0.3: a legal entity follows a standard and lists its units (REG-01,
// REG-08, J-10). Each stays test.fixme until the task in
// docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('standards per legal entity', () => {
  test.fixme("REG-S12: A legal entity follows a standard when its applicability is set to \"Applies\"", async () => {
    // pending: REG-S12 (REG-01, REG-02)
  });

  test.fixme("REG-S13: A tenant lists its clauses and controls as units in its own words", async () => {
    // pending: REG-S13 (REG-08)
  });

  test.fixme("REG-S14: Unit decisions are set from the paste in one confirmed call", async () => {
    // pending: REG-S14 (REG-01, REG-08, AC-REG1)
  });

  test.fixme("REG-S15: The register filtered by standard and entity is the Statement of Applicability", async () => {
    // pending: REG-S15 (REG-08)
  });

  test.fixme("REG-S16 J-10 @smoke: a legal entity follows a standard from regulatory scope to Statement of Applicability", async () => {
    // pending: REG-S16 (FP-02, TEN-02, REG-01, REG-08, J-10)
  });
});
