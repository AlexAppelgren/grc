import type { Browser, Locator, Page, TestInfo } from '@playwright/test';

import { expect, test, type ApiGuard } from './support/api-guard';
import { allowRegisterEntryPending, openObligation as openPanelObligation, signInElsewhere } from './support/obligation-page';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// register: the @e2e scenarios from backend/apps/register/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

// --- c8-ui-applicability-status (REG-S1, REG-S3, REG-S4, REG-S12) ------------------------
// Library titles are rows, so an obligation is found by its stable key and a legal
// entity by the name the seed gave it (backend/apps/shared/e2e_seed.py). Product
// governance spans Example Bank AB and the insurer, and the seed keeps a status row
// for the bank and the fund company; the ISO/IEC 27001 duty spans all three and no
// seeded bank follows it, so it is reached through "Show outside our scope".
const SPANNING = 'obl-product-governance';
const STANDARD = 'iso-iec-27001-2022-conformance';
const BANK = 'Example Bank AB';
const FONDER = 'Example Fonder AB';
const LIV = 'Example Liv Försäkring AB';
// What the seed wrote, which each journey's teardown puts back.
const SPANNING_REASON = 'We both manufacture and distribute instruments.';
const FONDER_NOTE = 'Negative target markets are not yet set for the two newest funds.';

async function openObligation(page: Page, stableKey: string, outside = false): Promise<void> {
  await page.goto(outside ? '/inventory?regime=ai_ict' : '/inventory');
  await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
  if (outside) await page.getByRole('button', { name: 'Show outside our scope' }).click();
  await page.locator(`[data-obligation="${stableKey}"]`).click();
  await expect(page.locator(`[data-obligation="${stableKey}"] [data-header-pills]`)).toBeVisible();
  await expect(page.locator('[data-applicability-panel]')).toBeVisible();
}

function applicabilityRow(page: Page, entity: string): Locator {
  return page.locator('[data-applicability-panel] [data-applicability-row]').filter({ has: page.getByRole('heading', { name: entity, exact: true }) });
}

function statusRow(page: Page, entity: string): Locator {
  return page.locator('[data-status-panel] [data-status-row]').filter({ has: page.getByRole('heading', { name: entity, exact: true }) });
}

/** Answers for one entity: the form, then the confirmation, then Set applicability. */
async function answer(page: Page, entity: string, value: string, reason: string): Promise<void> {
  await applicabilityRow(page, entity).getByRole('button', { name: /^(Decide|Change)$/ }).click();
  const form = page.getByRole('dialog', { name: `Does it apply to ${entity}?` });
  await form.getByLabel('Decision').selectOption({ label: value });
  await form.getByLabel('Reason').fill(reason);
  await form.getByRole('button', { name: 'Continue' }).click();
  const confirm = page.getByRole('dialog', { name: `Set "${value}" for ${entity}?` });
  await confirm.getByRole('button', { name: 'Set applicability' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByText(`Saved: ${value}.`)).toBeVisible();
}

/** Edits one entity's standing: each field by its label, then Save. */
async function editStanding(page: Page, entity: string, fields: { status?: string; rationale?: string; note?: string }): Promise<Locator> {
  await statusRow(page, entity).getByRole('button', { name: 'Edit' }).click();
  const dialog = page.getByRole('dialog', { name: `Where we stand at ${entity}` });
  await expect(dialog.getByLabel('Compliance status')).toBeVisible();
  if (fields.status !== undefined) await dialog.getByLabel('Compliance status').selectOption({ label: fields.status });
  if (fields.rationale !== undefined) await dialog.getByLabel('How you assessed it').fill(fields.rationale);
  if (fields.note !== undefined) await dialog.getByLabel('Status note').fill(fields.note);
  return dialog;
}

async function saveStanding(page: Page, entity: string, fields: { status?: string; rationale?: string; note?: string }): Promise<void> {
  const dialog = await editStanding(page, entity, fields);
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
}

/** A second person in their own browser, held to the same API guard. */
async function secondPerson(browser: Browser, apiGuard: ApiGuard, testInfo: TestInfo, login: string): Promise<Page> {
  const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
  const other = await context.newPage();
  apiGuard.watch(other);
  await signInAs(other, login);
  return other;
}

/** A word no seeded row holds, so a step reads its own write and nobody else's. */
function runMark(testInfo: TestInfo): string {
  return `run ${testInfo.workerIndex}-${testInfo.retry}-${Date.now().toString(36)}`;
}
// --- end c8-ui-applicability-status ------------------------------------------------------

// c8-ui-gaps-risk: the obligations REG-S5 and REG-S6 record their gaps on, each
// found in the inventory under its instrument (apps/library/fixtures). Both
// apply to tenant A: the ESMA warnings with status Gap, costs and charges partly.
const ESMA = 'obl-esma-warnings';
const ESMA_INSTRUMENT = 'esma-35-43-3006';
const COSTS = 'obl-costs-charges';
const COSTS_INSTRUMENT = 'fffs-2017-2';

/** The inventory under one instrument, then one card by stable key: the row's link carries the id. */
async function openGapObligation(page: Page, instrument: string, stableKey: string): Promise<void> {
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

test.describe('register journeys', () => {
  test("REG-S1: One compliance person sets applicability after confirming it", async ({ page, apiGuard }, testInfo) => {
    // REG-01, D-75: one person holding applicability.approve answers for the insurer,
    // which product governance spans and nobody answered in the seed. Nothing is sent
    // before the confirmation's own button; there is no request, approver or passkey.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, SPANNING);
    const writes: string[] = [];
    page.on('request', (request) => {
      if (request.method() === 'PUT' && request.url().includes('/applicability')) writes.push(request.url());
    });
    const reason = `The insurer distributes no instruments of its own (${runMark(testInfo)}).`;
    const liv = applicabilityRow(page, LIV);
    try {
      await liv.getByRole('button', { name: /^(Decide|Change)$/ }).click();
      const form = page.getByRole('dialog', { name: `Does it apply to ${LIV}?` });
      await form.getByLabel('Decision').selectOption({ label: 'Does not apply' });
      await form.getByLabel('Reason').fill(reason);
      await form.getByRole('button', { name: 'Continue' }).click();
      const confirm = page.getByRole('dialog', { name: `Set "Does not apply" for ${LIV}?` });
      await expect(confirm).toContainText('It is stored at once in your name, with your reason, and kept in the audit log.');
      await confirm.getByRole('button', { name: 'Cancel' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(liv.getByText(reason)).toHaveCount(0);
      expect(writes).toEqual([]);

      await answer(page, LIV, 'Does not apply', reason);
      expect(writes).toHaveLength(1);
      await expect(liv.locator('[data-pill]')).toHaveText(['Does not apply']);
      await expect(liv.getByText(reason)).toBeVisible();
      await expect(page.getByText('Waiting for approval')).toHaveCount(0);
      await page.reload();
      await expect(applicabilityRow(page, LIV).getByText(reason)).toBeVisible();
    } finally {
      // The seed leaves the insurer unanswered; "Not assessed" is that answer again.
      await openObligation(page, SPANNING);
      await answer(page, LIV, 'Not assessed', `Reset after REG-S1 (${runMark(testInfo)}).`);
    }
  });

  test("REG-S3: Compliance status and its details are kept per legal entity", async ({ page, browser, apiGuard }, testInfo) => {
    // REG-02, with REG-S4's journey half: the bank and the fund company each keep their
    // own status and details, the header shows the worse and names it, a concurrent
    // save is refused and merges nothing, and "does not apply" hides no status.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, SPANNING);
    const header = page.locator('[data-status-header]');
    const mark = runMark(testInfo);
    try {
      await expect(statusRow(page, BANK).locator('[data-pill]')).toHaveText(['Compliant']);
      await expect(statusRow(page, FONDER).locator('[data-pill]')).toHaveText(['Partly compliant']);
      await expect(header.locator('[data-pill]')).toHaveText(['Partly compliant']);
      await expect(header).toContainText(`at ${FONDER}, the weakest legal entity`);

      // Each entity keeps its own: a note on the fund company leaves the bank's row alone.
      const note = `Negative target markets set for one of the two funds (${mark}).`;
      await saveStanding(page, FONDER, { note });
      await expect(statusRow(page, FONDER).getByText(note)).toBeVisible();
      await expect(statusRow(page, BANK).getByText(note)).toHaveCount(0);

      // The worse of the two moves with the bank's own status.
      await saveStanding(page, BANK, { status: 'Gap', rationale: `Second-line sample found no target market review (${mark}).` });
      await expect(header.locator('[data-pill]')).toHaveText(['Gap']);
      await expect(header).toContainText(`at ${BANK}, the weakest legal entity`);
      await saveStanding(page, BANK, { status: 'Compliant', rationale: `Review recorded (${mark}).` });
      await expect(header).toContainText(`at ${FONDER}, the weakest legal entity`);

      // A colleague saves the fund company first: this save is refused and merges nothing.
      const dialog = await editStanding(page, FONDER, { note: `Mine (${mark}).` });
      const colleague = await secondPerson(browser, apiGuard, testInfo, LOGINS.owner);
      const theirs = `Theirs (${mark}).`;
      await openObligation(colleague, SPANNING);
      await saveStanding(colleague, FONDER, { note: theirs });
      await colleague.context().close();
      apiGuard.allow(/\/register\/entities\//, 409, 'the colleague saved the fund company first');
      await dialog.getByRole('button', { name: 'Save' }).click();
      await expect(dialog.getByText('Someone changed this entry while you were editing. Reload to see their version, then make your change again.')).toBeVisible();
      await dialog.getByRole('button', { name: 'Reload' }).click();
      await expect(statusRow(page, FONDER).getByText(theirs)).toBeVisible();

      // REG-S4: "does not apply" for the bank takes its row off the status panel and
      // deletes nothing; "applies" again brings back the status it had.
      await answer(page, BANK, 'Does not apply', `The bank stopped manufacturing (${mark}).`);
      await expect(statusRow(page, BANK)).toHaveCount(0);
      await expect(header.locator('[data-pill]')).toHaveText(['Partly compliant']);
      await answer(page, BANK, 'Applies', SPANNING_REASON);
      await expect(statusRow(page, BANK).locator('[data-pill]')).toHaveText(['Compliant']);
    } finally {
      await openObligation(page, SPANNING);
      if ((await applicabilityRow(page, BANK).locator('[data-pill]').textContent()) !== 'Applies') await answer(page, BANK, 'Applies', SPANNING_REASON);
      await saveStanding(page, BANK, { status: 'Compliant' });
      await saveStanding(page, FONDER, { note: FONDER_NOTE });
    }
  });

  // c8-ui-gaps-risk: REG-S5 and REG-S6 on the obligation page's Gaps panel,
  // each on a gap it records itself, so a re-run and the seeded gaps never meet.
  test("REG-S5: A gap has an owner, severity, target date and remediation", async ({ page, apiGuard }, testInfo) => {
    // REG-S5 (REG-03): the owner records a high gap on an obligation whose
    // status is Gap, sees Open and High in the negative tone with its source,
    // and starts remediation, which reads Remediating as warning. The roadmap's
    // "Our deadline" line is c8-ui-home-register's step.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.owner);
    await openGapObligation(page, ESMA_INSTRUMENT, ESMA);
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
    } finally {
      // On a failure too: the recorded gap leaves no open work behind.
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
    await openGapObligation(page, COSTS_INSTRUMENT, COSTS);
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
      await openGapObligation(approver, COSTS_INSTRUMENT, COSTS);
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

  // c8-ui-links-history-participants: the obligation the seed assessed twice over a year and
  // read in two versions (HISTORY_OBLIGATION in apps/shared/e2e_seed.py).
  test("REG-S7: Assessment history and \"How we read this rule\" are kept per obligation", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    allowRegisterEntryPending(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openPanelObligation(page, 'obl-appropriateness');
    const panel = page.locator('[data-history-panel]');

    // The current reading, with its author and date.
    const current = panel.locator('[data-reading-current]');
    await expect(current).toHaveAttribute('data-reading-current', '2');
    await expect(current.locator('[data-reading-by]')).toHaveText(/^Version 2, written by Sara Lindqvist, \d{1,2} \w{3} \d{4}$/);

    // Each earlier assessment, unchanged, with who and when; newest first.
    const rows = panel.locator('[data-history] [data-assessment-id]');
    await expect(rows.first()).toContainText('Sara Lindqvist');
    await expect(rows.first()).toContainText('Second-line review');
    const older = rows.filter({ hasText: 'Johan Berg' }).filter({ hasText: 'Self-assessment' });
    await expect(older).toHaveCount(1);
    await expect(older.locator('p')).not.toBeEmpty();

    // The earlier reading stays readable.
    await panel.getByRole('button', { name: /^Earlier versions? of how we read this rule, 1$/ }).click();
    await expect(panel.locator('[data-reading-version="1"]')).toContainText('Johan Berg');

    // A new version is written under If-Match and the one before stays readable.
    await panel.getByRole('button', { name: 'Write a new version' }).click();
    const editor = page.getByRole('dialog', { name: 'How we read this rule' });
    const reading = editor.getByLabel('Our reading');
    const seeded = await reading.inputValue();
    let wrote = false;
    try {
      await reading.fill(`${seeded} Structured deposits count as complex too.`);
      const saved = page.waitForResponse((r) => r.url().endsWith('/interpretation') && r.request().method() === 'PUT');
      await editor.getByRole('button', { name: 'Save version' }).click();
      const put = await saved;
      expect(put.status()).toBe(200);
      wrote = true;
      expect(put.request().headers()['if-match']).toBe('"2"');
      await expect(editor).toBeHidden();
      await expect(current).toHaveAttribute('data-reading-current', '3');
      await expect(current.locator('[data-reading-by]')).toContainText('Sara Lindqvist');
      // The earlier versions stay open, now two of them, the one just replaced among them.
      await expect(panel.getByRole('button', { name: /^Earlier versions? of how we read this rule, 2$/ })).toHaveAttribute('aria-expanded', 'true');
      await expect(panel.locator('[data-reading-version="2"]')).toContainText(seeded);
    } finally {
      // Nothing is overwritten, so the seeded reading comes back as the next version.
      if (wrote) {
        await panel.getByRole('button', { name: 'Write a new version' }).click();
        await editor.getByLabel('Our reading').fill(seeded);
        await editor.getByRole('button', { name: 'Save version' }).click();
        await expect(editor).toBeHidden();
      }
    }
  });

  // c8-ui-links-history-participants: the policy and the control the seed leaves unlinked for
  // this journey, picked on the client assets duty, and one item created from the dialog.
  test("REG-S8: Linked internal items carry external references", async ({ page, apiGuard, browser }, testInfo) => {
    allowFreshContext(apiGuard);
    allowRegisterEntryPending(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openPanelObligation(page, 'obl-client-assets');
    const panel = page.locator('[data-links-panel]');
    await expect(panel.locator('[data-links-empty]').or(panel.locator('[data-link-id]')).first()).toBeVisible();
    const dialog = page.getByRole('dialog', { name: /^(Link an internal item|Create and link an item)$/ });
    const linked: string[] = [];

    async function pick(reference: string, name: RegExp): Promise<string> {
      await panel.getByRole('button', { name: 'Link an item' }).click();
      await dialog.getByRole('searchbox', { name: 'Find an item' }).fill(reference);
      await dialog.getByRole('radio', { name }).click();
      const added = page.waitForResponse((r) => r.url().endsWith('/internal-links') && r.request().method() === 'POST');
      await dialog.getByRole('button', { name: 'Link' }).click();
      const response = await added;
      expect(response.status()).toBe(201);
      await expect(dialog).toBeHidden();
      return ((await response.json()) as { id: string }).id;
    }

    try {
      linked.push(await pick('POL-014', /Client asset policy/));
      linked.push(await pick('CTL-203', /Daily reconciliation/));
      // Both listed with their kind label and external reference.
      const policy = panel.locator(`[data-link-id="${linked[0]}"]`);
      await expect(policy.locator('[data-link-kind]')).toHaveText('Policy');
      await expect(policy.locator('[data-link-ref]')).toHaveText('POL-014');
      const control = panel.locator(`[data-link-id="${linked[1]}"]`);
      await expect(control.locator('[data-link-kind]')).toHaveText('Control');
      await expect(control.locator('[data-link-ref]')).toHaveText('CTL-203');

      // A second link of the same item is refused by its code.
      apiGuard.allow(/\/internal-links$/, 409, 'REG-S8 links the policy a second time on purpose');
      await panel.getByRole('button', { name: 'Link an item' }).click();
      await dialog.getByRole('searchbox', { name: 'Find an item' }).fill('POL-014');
      await dialog.getByRole('radio', { name: /Client asset policy/ }).click();
      await dialog.getByRole('button', { name: 'Link' }).click();
      await expect(dialog.getByText('That item is already linked to this obligation.')).toBeVisible();
      await dialog.getByRole('button', { name: 'Cancel' }).click();

      // An item created from the dialog: one item and one link in one call.
      const name = `Custody break log review ${Date.now()}`;
      await panel.getByRole('button', { name: 'Link an item' }).click();
      await dialog.getByRole('button', { name: 'Create a new item instead' }).click();
      await dialog.getByLabel('Kind').selectOption({ label: 'Control' });
      await dialog.getByLabel('Name').fill(name);
      await dialog.getByLabel('Your reference').fill('CTL-777');
      const created = page.waitForResponse((r) => r.url().endsWith('/internal-links') && r.request().method() === 'POST');
      await dialog.getByRole('button', { name: 'Create and link' }).click();
      const createdResponse = await created;
      expect(createdResponse.status()).toBe(201);
      const link = (await createdResponse.json()) as { id: string; internalItemId: string };
      linked.push(link.id);
      await expect(dialog).toBeHidden();
      await expect(panel.locator(`[data-link-id="${link.id}"] [data-link-ref]`)).toHaveText('CTL-777');

      // The API exposes the links, with the item each points at, so an outside GRC system can read them.
      const reader = await signInElsewhere(browser, testInfo.project.use.baseURL, apiGuard, LOGINS.reader);
      const readerLinks = reader.waitForResponse((r) => r.url().includes('/internal-links') && r.request().method() === 'GET');
      await openPanelObligation(reader, 'obl-client-assets');
      const listed = (await (await readerLinks).json()) as { items: { id: string; externalRef: string | null; kind: { key: string }; internalItemId: string }[] };
      expect(listed.items.find((row) => row.id === linked[0])).toMatchObject({ externalRef: 'POL-014', kind: { key: 'policy' } });
      expect(listed.items.find((row) => row.id === linked[1])).toMatchObject({ externalRef: 'CTL-203', kind: { key: 'control' } });
      expect(listed.items.find((row) => row.id === link.id)).toMatchObject({ internalItemId: link.internalItemId });
      // A reader sees the list and no control.
      const readerPanel = reader.locator('[data-links-panel]');
      await expect(readerPanel.locator(`[data-link-id="${linked[0]}"]`)).toBeVisible();
      await expect(readerPanel.getByRole('button', { name: 'Link an item' })).toHaveCount(0);
      await expect(readerPanel.getByRole('button', { name: 'Remove' })).toHaveCount(0);
      await reader.context().close();
    } finally {
      // Remove every link this journey made; each item stays, as a removal keeps it.
      for (const id of linked) {
        const row = panel.locator(`[data-link-id="${id}"]`);
        if ((await row.count()) === 0) continue;
        await row.getByRole('button', { name: 'Remove' }).click();
        const confirm = page.getByRole('dialog', { name: /^Remove the link to / });
        await expect(confirm.getByText('The item itself stays, with its other links.')).toBeVisible();
        await confirm.getByRole('button', { name: 'Remove link' }).click();
        await expect(row).toHaveCount(0);
      }
    }
  });

  test.fixme("REG-S9: Yearly attestation and waivers", async () => {
    // pending: REG-S9 (REG-06)
  });
});

// PRD 0.3: a legal entity follows a standard and lists its units (REG-01,
// REG-08, J-10). Each stays test.fixme until the task in
// docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('standards per legal entity', () => {
  test("REG-S12: A legal entity follows a standard when its applicability is set to \"Applies\"", async ({ page, apiGuard }, testInfo) => {
    // REG-01, REG-02, D-42: the conformance duty offers every legal entity before any row
    // exists; the bank follows the standard ("Applies", "Certified"), the insurer does
    // not, and the header reads the worst of the entities it applies to.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, STANDARD, true);
    const mark = runMark(testInfo);
    try {
      await expect(page.locator('[data-applicability-panel] [data-applicability-row] h3')).toHaveText([BANK, FONDER, LIV]);
      await answer(page, BANK, 'Applies', 'Certified');
      await answer(page, LIV, 'Does not apply', `The insurer is outside the certificate's scope (${mark}).`);

      const bank = applicabilityRow(page, BANK);
      await expect(bank.locator('[data-pill]')).toHaveText(['Applies']);
      await expect(bank.getByText('Certified', { exact: true })).toBeVisible();
      await expect(bank.getByText(/^Set by /)).toBeVisible();
      await expect(applicabilityRow(page, LIV).locator('[data-pill]')).toHaveText(['Does not apply']);
      await expect(applicabilityRow(page, FONDER).locator('[data-pill]')).toHaveText(['Not assessed']);

      // The bank alone follows it, so its status is the header's.
      const status = await statusRow(page, BANK).locator('[data-pill]').textContent();
      await expect(page.locator('[data-status-header] [data-pill]')).toHaveText([status ?? '']);
      await expect(statusRow(page, LIV)).toHaveCount(0);
    } finally {
      await openObligation(page, STANDARD, true);
      for (const entity of [BANK, LIV]) {
        if ((await applicabilityRow(page, entity).locator('[data-pill]').textContent()) !== 'Not assessed') {
          await answer(page, entity, 'Not assessed', `Reset after REG-S12 (${mark}).`);
        }
      }
    }
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
