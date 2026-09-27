import { execFileSync } from 'node:child_process';
import path from 'node:path';

import type { Browser, Locator, Page, TestInfo } from '@playwright/test';

import { expect, test, type ApiGuard } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';
import { lockTenantAScope, unlockTenantAScope } from './support/tenant-scope';

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

// --- c8-ui-soa-j10 (REG-S13 to REG-S16) --------------------------------------------------
// Units are the bank's own words, so each run pastes invented references no other run
// holds. The footprint steps are FP-S16's (taxonomy.journey.spec.ts): the seeded standard's
// term, which no seeded bank follows, and the same door in and out of the scope.
const CERTIFIED = 'Certified';

function unitsPanel(page: Page): Locator {
  return page.locator('[data-units-panel]');
}

function unitRow(page: Page, reference: string): Locator {
  return unitsPanel(page).locator('[data-unit-id]').filter({ has: page.getByText(reference, { exact: true }) });
}

/** A reference stem no seeded row and no other run holds. */
function unitPrefix(testInfo: TestInfo): string {
  return `T${testInfo.workerIndex}${testInfo.retry}${Date.now().toString(36).toUpperCase()}`;
}

/** Example Bank AB follows the standard with the reason "Certified", as every units journey needs. */
async function bankFollowsTheStandard(page: Page): Promise<void> {
  const row = applicabilityRow(page, BANK);
  await expect(row.locator('[data-pill]')).toBeVisible();
  const follows = (await row.locator('[data-pill]').textContent()) === 'Applies' && (await row.getByText(CERTIFIED, { exact: true }).count()) > 0;
  if (!follows) await answer(page, BANK, 'Applies', CERTIFIED);
  await expect(unitsPanel(page).getByLabel('Legal entity')).toBeVisible();
}

/** The bank's answer back to "Not assessed", as the seed left it; its units stay, unlisted. */
async function bankLeavesTheStandard(page: Page, mark: string): Promise<void> {
  await openObligation(page, STANDARD, true);
  const pill = applicabilityRow(page, BANK).locator('[data-pill]');
  await expect(pill).toBeVisible();
  if ((await pill.textContent()) !== 'Not assessed') await answer(page, BANK, 'Not assessed', `Reset after the units journeys (${mark}).`);
}

/** Pastes the lines for the bank and waits for the dry run, which stores nothing. */
async function pasteUnits(page: Page, lines: readonly string[]): Promise<Locator> {
  await unitsPanel(page).getByRole('button', { name: 'Paste units' }).click();
  const dialog = page.getByRole('dialog', { name: `Paste units for ${BANK}` });
  await dialog.getByLabel('One unit per line').fill(lines.join('\n'));
  await dialog.getByRole('button', { name: 'Check the lines' }).click();
  const dry = page.getByRole('dialog', { name: 'Check before you create' });
  await expect(dry.locator('[data-paste-dry-run]')).toBeVisible();
  return dry;
}

/** The paste commits and bulk decision calls the page sends, so "one call" is proved on the wire. */
function unitWrites(page: Page): { commits: string[]; decisionCalls: string[] } {
  const writes = { commits: [] as string[], decisionCalls: [] as string[] };
  page.on('request', (request) => {
    if (request.method() !== 'POST') return;
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/units/paste') && (request.postDataJSON() as { dryRun?: boolean }).dryRun === false) writes.commits.push(path);
    if (path === '/api/v1/applicability') writes.decisionCalls.push(path);
  });
  return writes;
}

/** The Statement of Applicability tab of the bank's units. */
async function openStatement(page: Page): Promise<Locator> {
  await unitsPanel(page).getByRole('tab', { name: 'Statement of Applicability' }).click();
  const soa = unitsPanel(page).locator('[data-soa]');
  await expect(soa.locator('[data-soa-conformance]')).toBeVisible();
  return soa;
}

/** Tenant A's today plus `days`, as a plain ISO date (the tenant is in Stockholm). */
function dayFromToday(days: number): string {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const date = new Date(`${today}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** A plain date as the screens render it. */
function shownDay(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${iso}T00:00:00Z`));
}

function todayShown(): string {
  return shownDay(dayFromToday(0));
}

/** Tenant A starts or stops following the standard, as WAT-S10 does (`manage.py e2e_follow_standard`). */
function followTheStandard(state: 'on' | 'off'): void {
  // Forward slashes: bash opens the script by this path, and a Windows checkout hands path.join backslashes.
  const script = path.join(test.info().project.testDir, 'support', 'start-backend.sh').split(path.sep).join('/');
  execFileSync('bash', [script, 'manage', 'e2e_follow_standard', state], { encoding: 'utf8' });
}

function standardTerm(page: Page): Locator {
  return page.locator('[data-dimension="standard"] [data-term="iso_iec_27001"]');
}

/** Opens the scope as the officer, withdrawing a request of theirs that is still waiting. */
async function officerStartsClean(page: Page): Promise<void> {
  await page.goto('/admin/footprint');
  const mine = page.locator('[data-pending-request]').filter({ hasText: /You requested this on/ });
  await expect(mine.or(page.locator('[data-footprint-dimensions]')).first()).toBeVisible();
  if ((await mine.count()) > 0) {
    await mine.getByRole('button', { name: 'Withdraw' }).click();
    await expect(page.getByText('Withdrawn.', { exact: true })).toBeFocused();
    await expect(page.locator('[data-pending-request]')).toHaveCount(0);
  }
}

/** Sends the drafted scope change once its counted preview has loaded. */
async function sendDraft(page: Page, heading: string): Promise<void> {
  const draft = page.locator('[data-draft-preview]');
  await expect(draft.getByRole('heading', { name: heading })).toBeVisible();
  await expect(draft.getByText('Loading…')).toHaveCount(0);
  await draft.getByRole('button', { name: 'Request approval' }).click();
  await expect(page.getByText('Sent for approval.', { exact: true })).toBeFocused();
}

/** The second person approves the waiting scope change with a passkey step-up. */
async function approveWithPasskey(approver: Page): Promise<void> {
  await approver.goto('/admin/footprint');
  await approver.locator('[data-pending-request]').getByRole('button', { name: 'Approve' }).click();
  await approver.getByRole('dialog', { name: /^Approve ".+"\?$/ }).getByRole('button', { name: 'Approve with passkey' }).click();
  // Step-up: settle on the prompt or the outcome, since a sign-in moments ago may still count.
  const prompt = approver.getByRole('dialog', { name: 'Confirm with your passkey' });
  const done = approver.getByText('Approved. The regulatory scope has changed.');
  await expect(prompt.or(done).first()).toBeVisible();
  if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  await expect(done).toBeVisible();
  await expect(approver.locator('[data-pending-request]')).toHaveCount(0);
}
// --- end c8-ui-soa-j10 -------------------------------------------------------------------

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
  // Every journey here answers for Example Bank AB on the one seeded standard, and REG-S12
  // takes that answer back, so they run in order in one worker (c8-ui-soa-j10). They reach
  // the standard through the outside view, and REG-S15 and J-10 put it in tenant A's scope,
  // so each takes its turn with the scope's other journeys (support/tenant-scope.ts).
  test.describe.configure({ mode: 'default' });
  test.beforeEach(lockTenantAScope);
  test.afterEach(unlockTenantAScope);

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

  test("REG-S13: A tenant lists its clauses and controls as units in its own words", async ({ page, apiGuard }, testInfo) => {
    // REG-08: only a legal entity that follows the standard is offered, the form asks for
    // the bank's own words, the dry run stores nothing and names each refused line, and a
    // unit with no history is renamed or removed. The audit event per unit, the 422s for an
    // entity that does not follow the standard and a duty that is not one, and the 409 on a
    // unit with history are proved by the backend's REG-S13 test.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, STANDARD, true);
    const mark = runMark(testInfo);
    const prefix = unitPrefix(testInfo);
    try {
      await bankFollowsTheStandard(page);
      const panel = unitsPanel(page);
      await expect(panel.getByLabel('Legal entity').locator('option')).toHaveText([BANK]);
      // The insurer said it does not follow the standard: named in the hint, never offered.
      await expect(panel.getByText(new RegExp(`Not listed: .*${LIV}`))).toBeVisible();

      // The form has two fields, both the bank's own, and no field for the standard's text.
      await panel.getByRole('button', { name: 'Add a unit' }).click();
      const form = page.getByRole('dialog', { name: `Add a unit for ${BANK}` });
      await expect(form.getByRole('textbox')).toHaveCount(2);
      await expect(form.getByText("In your own words, as your own list has it. Do not copy the standard's text.")).toBeVisible();
      await form.getByRole('button', { name: 'Cancel' }).click();

      // Twelve lines, one repeated and one too long: the dry run says so and stores nothing.
      const lines = Array.from({ length: 12 }, (_, index) => `${prefix}-${String(index + 1).padStart(2, '0')}\tOur own control ${index + 1}`);
      const dry = await pasteUnits(page, [...lines, lines[0] ?? '', `${prefix}-99\t${'An invented title far too long '.repeat(10)}`]);
      await expect(dry.getByRole('heading', { name: '12 units to create' })).toBeVisible();
      await expect(dry.getByRole('heading', { name: '2 lines refused and left out' })).toBeVisible();
      await expect(dry.getByText('An earlier line already uses this reference.')).toBeVisible();
      await expect(dry.getByText('The title is too long.')).toBeVisible();
      await expect(unitRow(page, `${prefix}-01`)).toHaveCount(0);
      await dry.getByRole('button', { name: 'Create 12 units' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(panel.getByText('12 units created.')).toBeVisible();
      await expect(unitRow(page, `${prefix}-12`)).toBeVisible();

      // A unit with no history yet: renamed with its version, then another removed.
      const renamed = unitRow(page, `${prefix}-12`);
      await renamed.getByRole('button', { name: 'Rename' }).click();
      const rename = page.getByRole('dialog', { name: `Rename ${prefix}-12` });
      await rename.getByLabel('Your title').fill(`Our own control 12, reworded (${mark})`);
      await rename.getByRole('button', { name: 'Save' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(renamed.getByRole('heading', { name: `Our own control 12, reworded (${mark})` })).toBeVisible();

      await unitRow(page, `${prefix}-11`).getByRole('button', { name: 'Remove' }).click();
      await page.getByRole('dialog', { name: `Remove ${prefix}-11?` }).getByRole('button', { name: 'Remove' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(unitRow(page, `${prefix}-11`)).toHaveCount(0);
      await expect(unitRow(page, `${prefix}-10`)).toBeVisible();
    } finally {
      await bankLeavesTheStandard(page, mark);
    }
  });

  test("REG-S14: Unit decisions are set from the paste in one confirmed call", async ({ page, apiGuard }, testInfo) => {
    // REG-01, REG-08, AC-REG1: a paste that carries decisions lists them all in one
    // dialog, stores nothing before its confirmation, and then stores the units and every
    // decision in one call, each in the officer's name with its reason. The cap above which
    // nothing is stored is proved by the backend's REG-S14 test.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, STANDARD, true);
    const mark = runMark(testInfo);
    const prefix = unitPrefix(testInfo);
    const writes = unitWrites(page);
    try {
      await bankFollowsTheStandard(page);
      const decisions = [
        { reference: `${prefix}-01`, title: 'Our board approves the security policy', word: 'applies', pill: 'Applies', reason: 'The board owns it' },
        { reference: `${prefix}-02`, title: 'Our clean desk rule in the branches', word: 'does not apply', pill: 'Does not apply', reason: 'We have no branches' },
        { reference: `${prefix}-03`, title: 'Our yearly restore test of backups', word: 'applies', pill: 'Applies', reason: 'Our certificate covers it' },
      ];
      const dry = await pasteUnits(page, decisions.map((unit) => [unit.reference, unit.title, unit.word, unit.reason].join('\t')));
      await dry.getByRole('button', { name: 'Create 3 units' }).click();

      const confirm = page.getByRole('dialog', { name: `Set 3 decisions for ${BANK}?` });
      for (const unit of decisions) await expect(confirm.getByText(unit.reason)).toBeVisible();
      expect(writes.commits).toEqual([]);
      await confirm.getByRole('button', { name: 'Set 3 decisions' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(unitsPanel(page).getByText('3 units created.')).toBeVisible();
      expect(writes.commits).toHaveLength(1);
      expect(writes.decisionCalls).toEqual([]);

      // Each unit carries its own decision, reason and who set it, and is fixed from now on.
      for (const unit of decisions) {
        const row = unitRow(page, unit.reference);
        await expect(row.locator('[data-pill]').first()).toHaveText(unit.pill);
        await expect(row.getByText(unit.reason, { exact: true })).toBeVisible();
        await expect(row.getByText('Set by Sara Lindqvist')).toBeVisible();
        await expect(row.getByText('Reference and title are fixed: this unit has history.')).toBeVisible();
      }
      await expect(page.getByText('Waiting for approval')).toHaveCount(0);
    } finally {
      await bankLeavesTheStandard(page, mark);
    }
  });

  test("REG-S15: The register filtered by standard and entity is the Statement of Applicability", async ({ page, apiGuard }, testInfo) => {
    // REG-08: the statement of one entity shows each unit's reference, the bank's title,
    // its decision, reason, status, who set it and when, and its history; the conformance
    // row keeps the status assessed on the obligation. Today's count of the standard as one
    // obligation is proved by the backend's REG-S15 test.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, STANDARD, true);
    const mark = runMark(testInfo);
    const prefix = unitPrefix(testInfo);
    // The statement is read only for a standard inside the regulatory scope (a standard
    // outside it answers 404), so tenant A follows it for this run, as WAT-S10 does.
    followTheStandard('on');
    try {
      await bankFollowsTheStandard(page);
      const dry = await pasteUnits(page, [`${prefix}-01\tOur access reviews every quarter\tapplies\tPayments staff change often`, `${prefix}-02\tOur branch alarm checks\tdoes not apply\tWe have no branches`]);
      await dry.getByRole('button', { name: 'Create 2 units' }).click();
      await page.getByRole('dialog', { name: `Set 2 decisions for ${BANK}?` }).getByRole('button', { name: 'Set 2 decisions' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);

      const soa = await openStatement(page);
      const conformance = soa.locator('[data-soa-conformance]');
      await expect(conformance.getByRole('heading', { name: `Conformance for ${BANK}` })).toBeVisible();
      await expect(conformance.locator('[data-pill]').first()).toHaveText('Applies');
      await expect(conformance.getByText(CERTIFIED, { exact: true })).toBeVisible();
      // Its own assessed status, as the status panel holds it: never computed from the units.
      const own = (await statusRow(page, BANK).locator('[data-pill]').textContent()) ?? '';
      await expect(conformance.locator('[data-pill]').nth(1)).toHaveText(own);
      await expect(conformance.getByText('This is the status assessed on the obligation for the entity. The units below do not change it.')).toBeVisible();

      const decided = soa.locator(`[data-soa-unit="${prefix}-01"]`);
      await expect(decided).toContainText('Our access reviews every quarter');
      await expect(decided.locator('[data-pill]').first()).toHaveText('Applies');
      // Its status pill beside its applicability (the history's pills sit folded away).
      await expect(decided.locator('[data-pill]').nth(1)).toBeVisible();
      await expect(decided).toContainText('Payments staff change often');
      await expect(decided).toContainText('Sara Lindqvist');
      await expect(decided.getByText(todayShown(), { exact: true })).toBeVisible();
      await expect(soa.locator(`[data-soa-unit="${prefix}-02"] [data-pill]`).first()).toHaveText('Does not apply');

      // The unit's history: its one decision, with who and when.
      const history = decided.locator('[data-soa-history]');
      await history.getByText('1 decision', { exact: true }).click();
      await expect(history.getByRole('listitem')).toHaveCount(1);
      await expect(history.getByRole('listitem')).toContainText('Payments staff change often');
      await expect(history.getByText(`Set by Sara Lindqvist, ${todayShown()}`)).toBeVisible();
    } finally {
      await bankLeavesTheStandard(page, mark);
      followTheStandard('off');
    }
  });

  test("REG-S16 J-10 @smoke: a legal entity follows a standard from regulatory scope to Statement of Applicability", async ({ page, browser, apiGuard }, testInfo) => {
    // J-10 (FP-02, TEN-02, REG-01, REG-08): the standard enters the regulatory scope with
    // four eyes and a passkey, the bank records its certificate, follows the standard, lists
    // three units with their decisions in one confirmed call, reads them in its Statement of
    // Applicability, and sees the certificate's next audit on the roadmap as its own deadline.
    // Like FP-S16 it changes tenant A's scope, and it takes every step back afterwards.
    // Two people, two scope changes and eight screens: three times the default timeout.
    test.slow();
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/api\/v1\/tenant\/footprint\/requests\/[^/]+\/approve$/, 403, 'the first attempt answers step_up_required and opens the prompt');
    await signInAs(page, LOGINS.complianceOfficer);
    const approver = await secondPerson(browser, apiGuard, testInfo, LOGINS.approver);
    const mark = runMark(testInfo);
    const prefix = unitPrefix(testInfo);
    const number = `EC-J10-${Date.now()}-${testInfo.retry}`;
    const nextAudit = dayFromToday(47);
    const writes = unitWrites(page);
    try {
      // 1. The officer adds the standard to the regulatory scope; the approver approves with a passkey.
      await officerStartsClean(page);
      await expect(standardTerm(page)).toHaveCount(0);
      await page.getByRole('button', { name: 'Propose a change' }).click();
      await page.locator('[data-dimension="standard"]').getByRole('checkbox', { name: /^ISO\/IEC 27001$/ }).check();
      await sendDraft(page, 'Your change: Add ISO/IEC 27001');
      await approveWithPasskey(approver);
      await page.goto('/admin/footprint');
      await expect(standardTerm(page)).toHaveText(/^ISO\/IEC 27001 In our scope$/);

      // 2. The officer records the certificate on Example Bank AB, with its next audit.
      await page.goto('/admin/organisation');
      const licences = page.locator(`[data-licences-of="${BANK}"]`);
      await licences.getByRole('button', { name: `Add a licence or certificate to ${BANK}` }).click();
      const dialog = page.getByRole('dialog', { name: `Add a licence or certificate to ${BANK}` });
      await dialog.getByLabel('Kind').selectOption('certificate');
      await dialog.getByLabel('Type').selectOption('iso_iec_27001');
      await dialog.getByLabel('Issuer').fill('Example Certification AB');
      await dialog.getByLabel('Certificate number').fill(number);
      await dialog.getByLabel('Scope statement').fill('The information security management system for the bank');
      await dialog.getByLabel('Issued').fill(dayFromToday(-200));
      await dialog.getByLabel('Valid until').fill(dayFromToday(900));
      await dialog.getByLabel('Next audit').fill(nextAudit);
      await dialog.getByLabel('Owner').selectOption({ label: 'Sara Lindqvist' });
      await dialog.getByRole('button', { name: 'Save' }).click();
      await expect(dialog).toBeHidden();
      await expect(licences.locator('[data-licence]').filter({ hasText: number })).toBeVisible();

      // 3. Now inside the scope, the officer sets "Applies" for the bank, confirming it.
      await openObligation(page, STANDARD);
      await expect(page.locator(`[data-obligation="${STANDARD}"]`)).not.toHaveAttribute('data-outside-footprint');
      await answer(page, BANK, 'Applies', CERTIFIED);

      // 4. Three invented units with their decisions, confirmed in one call.
      const units = [
        { reference: `${prefix}-01`, title: 'Our security policy has an owner', word: 'applies', reason: 'Certified scope' },
        { reference: `${prefix}-02`, title: 'Our branch safes are checked', word: 'does not apply', reason: 'We have no branches' },
        { reference: `${prefix}-03`, title: 'Our suppliers sign a security annex', word: 'applies', reason: 'Certified scope' },
      ];
      const dry = await pasteUnits(page, units.map((unit) => [unit.reference, unit.title, unit.word, unit.reason].join('\t')));
      await dry.getByRole('button', { name: 'Create 3 units' }).click();
      await page.getByRole('dialog', { name: `Set 3 decisions for ${BANK}?` }).getByRole('button', { name: 'Set 3 decisions' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      expect(writes.commits).toHaveLength(1);
      expect(writes.decisionCalls).toEqual([]);

      // 5. The register filtered by the standard and the bank shows the three decisions.
      const soa = await openStatement(page);
      await expect(soa.locator('[data-soa-conformance]').getByText(CERTIFIED, { exact: true })).toBeVisible();
      for (const [unit, pill] of [[units[0], 'Applies'], [units[1], 'Does not apply'], [units[2], 'Applies']] as const) {
        const row = soa.locator(`[data-soa-unit="${unit?.reference ?? ''}"]`);
        await expect(row.locator('[data-pill]').first()).toHaveText(pill);
        await expect(row).toContainText(unit?.reason ?? '');
        await expect(row).toContainText('Sara Lindqvist');
      }

      // 6. The roadmap shows the certificate's next audit as our own deadline.
      await page.goto('/roadmap?kind=internal');
      const audit = page.locator('[data-roadmap-card^="certificate_audit:"]').filter({ hasText: shownDay(nextAudit) });
      await expect(audit.first()).toBeVisible();
      await expect(audit.first()).toContainText('Our deadline');
    } finally {
      // Every step back, on failure too: the certificate withdrawn, the answer taken back,
      // and the standard out of the scope through the same door.
      await page.goto('/admin/organisation');
      const certificate = page.locator(`[data-licences-of="${BANK}"] [data-licence]`).filter({ hasText: number });
      await expect(page.locator(`[data-licences-of="${BANK}"] [data-licence]`).first()).toBeVisible();
      if ((await certificate.count()) > 0) {
        await certificate.getByRole('button', { name: /^Edit / }).click();
        const edit = page.getByRole('dialog');
        await edit.getByLabel('Withdrawn').fill(dayFromToday(0));
        await edit.getByRole('button', { name: 'Save' }).click();
        await expect(edit).toBeHidden();
      }
      await bankLeavesTheStandard(page, mark);
      await officerStartsClean(page);
      if ((await standardTerm(page).count()) > 0) {
        await page.getByRole('button', { name: 'Propose a change' }).click();
        await page.locator('[data-dimension="standard"]').getByRole('checkbox', { name: /^ISO\/IEC 27001$/ }).uncheck();
        await sendDraft(page, 'Your change: Remove ISO/IEC 27001');
        await approveWithPasskey(approver);
      }
      await approver.context().close();
    }
  });
});
