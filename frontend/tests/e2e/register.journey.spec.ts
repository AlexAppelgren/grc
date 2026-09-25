import type { Browser, Locator, Page, TestInfo } from '@playwright/test';

import { expect, test, type ApiGuard } from './support/api-guard';
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

  test.fixme("REG-S5: A gap has an owner, severity, target date and remediation", async () => {
    // pending: REG-S5 (REG-03)
  });

  test.fixme("REG-S6: Risk acceptance is behind four eyes with step-up", async () => {
    // pending: REG-S6 (REG-03)
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
