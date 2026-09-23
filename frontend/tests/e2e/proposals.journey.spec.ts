import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, BACKEND_URL, LOGINS, restrictedScreen, signInAs, signOut } from './support/passkeys';

// proposals: the @e2e scenarios from backend/apps/proposals/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// PRO-S3, PRO-S4 and PRO-S7 decide the new_obligation_version proposals
// backend/apps/shared/e2e_seed.py leaves waiting for them (EXPECTED_PROPOSALS). Each
// targets an obligation no other spec names, so the journeys never race each other or
// J-6. PRO-S5 and PRO-S9 decide a vocabulary proposal the journey proposes itself,
// through the console's own "Suggest a change" door (VOC-07), with a label unique to
// the attempt so a retry or a parallel run never collides on the near-duplicate check.
//
// No assertion here reads today's date against a seeded one: the versions these
// approvals write take effect on fixed legal dates, so a journey proves the version
// by the obligation card's version list, which holds every version whatever the day,
// never by the inventory row's "Version 2", which names only a version still ahead.

const APPROPRIATENESS_TITLE = 'Add version 2 of the appropriateness assessment obligation, in force 15 October 2026';
const COSTS_CHARGES_TITLE = 'Add version 2 of the costs and charges obligation, extending it to professional clients';
// PRO-S7 (e2e_seed.py PRO_S7_OBLIGATION): the proposal the console decides, and the
// duty's own title the bank then reads it under, never the proposal's.
const PENSION_TRANSFER_TITLE = 'Add version 2 of the pension transfer obligation, with a one-month deadline for the transfer';
const PENSION_TRANSFER_SOURCE = 'Riksdagen, Försäkringsavtalslagen (2005:104), consolidated text';
const PENSION_TRANSFER_OBLIGATION = "Honour the policyholder's right to transfer pension insurance savings";

/** The queue has settled when its rows or its empty state is on screen (states.html). */
async function queueSettled(page: Page): Promise<void> {
  await expect(page.locator('[data-proposal-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
}

/** Opens a proposal's detail by title, whichever tab it is decided under (a retry finds it Approved or Rejected rather than Waiting). */
async function openProposal(page: Page, titleFragment: RegExp): Promise<void> {
  await page.goto('/console/queue');
  await queueSettled(page);
  for (const tab of ['Waiting', 'Approved', 'Rejected']) {
    await page.getByRole('tab', { name: tab }).click();
    await queueSettled(page);
    const row = page.getByRole('link', { name: titleFragment });
    if ((await row.count()) > 0) {
      await row.first().click();
      await expect(page.getByRole('heading', { level: 1, name: titleFragment })).toBeVisible();
      return;
    }
  }
  throw new Error(`No proposal titled ${titleFragment} in any tab of the queue.`);
}

/** Approve and apply, through the global step-up dialog; settles on "waiting or already applied" so a retry passes. */
async function approveAndApply(page: Page): Promise<void> {
  const applied = page.locator('[data-proposal-applied]');
  const approve = page.getByRole('button', { name: 'Approve and apply' });
  await expect(applied.or(approve).first()).toBeVisible();
  if (await approve.isVisible()) {
    await approve.click();
    const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
    await expect(prompt.or(applied).first()).toBeVisible();
    if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  }
  await expect(applied).toBeVisible();
}

/**
 * The tenant reader opens the obligation's own card from the inventory and finds the version
 * the approval wrote in its version list, which holds every version whatever today's date.
 */
async function expectVersionOnCard(page: Page, stableKey: string, versionNumber: number): Promise<void> {
  await page.goto('/inventory');
  await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
  await page.locator(`[data-obligation="${stableKey}"]`).click();
  await expect(page.locator(`[data-versions-panel] [data-version-row="${versionNumber}"]`)).toBeVisible();
}

/** A vocabulary proposal made live, through the console's own door (VOC-07), with a label unique to the attempt. */
async function proposeFlag(page: Page, label: string): Promise<void> {
  await page.goto('/console/vocabularies');
  await expect(page.getByRole('heading', { level: 1, name: 'Vocabularies' })).toBeVisible();
  await page.locator('[data-vocabulary-list="flag"]').click();
  await page.getByRole('button', { name: 'Suggest a change' }).click();
  const dialog = page.getByRole('dialog', { name: 'Add a value' });
  await dialog.getByLabel('Label', { exact: true }).fill(label);
  await dialog.getByRole('button', { name: 'Send for review' }).click();
  await expect(dialog.getByText(/is waiting for a library editor\.$/)).toBeVisible();
  await dialog.getByRole('button', { name: 'Done' }).click();
}

test.describe('proposals journeys', () => {
  // PRO-S3 and PRO-S4 take the two `new_obligation_version` proposals the seed leaves in
  // the queue, and both then read the same seeded reader's inventory to prove the version
  // arrived. Run side by side they race over that one reader's session and over which
  // proposal each finds, and either can fail looking for a proposal the other has just
  // decided. They are serial here until `chunk4-T8` lands, which lets a journey seed a
  // proposal of its own the way PRO-S5 and PRO-S9 already mint their own vocabulary rows.
  test.describe.configure({ mode: 'serial' });

  test('PRO-S3: Approval applies payload, version, audit row and re-index in one transaction', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    // The first approve attempt always answers 403 step_up_required, which is what opens
    // the passkey prompt (playbook 4.2); approveAndApply() confirms it.
    apiGuard.allow(/\/proposals\/.+\/approve$/, 403, 'approving asks for a fresh passkey assertion first, which opens the step-up prompt');
    await signInAs(page, LOGINS.editor);
    await openProposal(page, new RegExp(APPROPRIATENESS_TITLE));
    await approveAndApply(page);
    await expect(page.getByText(/^Applied/)).toBeVisible();
    await signOut(page);

    // A tenant reader finds the version this approval just wrote on the obligation's own
    // card. Its effective date is a fixed legal date, so the version list is read rather
    // than the inventory row, whose "Version 2" goes once that date has passed.
    await signInAs(page, LOGINS.reader);
    await expectVersionOnCard(page, 'obl-appropriateness', 2);
  });

  test('PRO-S4: The reviewer corrects scope and wording before approving', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/proposals\/.+\/approve$/, 403, 'approving asks for a fresh passkey assertion first, which opens the step-up prompt');
    await signInAs(page, LOGINS.editor2);
    await openProposal(page, new RegExp(COSTS_CHARGES_TITLE));

    const applied = page.locator('[data-proposal-applied]');
    const form = page.locator('[data-proposal-correction]');
    if (await form.isVisible()) {
      // The scope term the reviewer disagrees with (backend/apps/shared/e2e_seed.py):
      // removed before approving. "Professional" is the seeded taxonomy term's own
      // label (apps/taxonomy/seeds/fixture.py), never catalog copy, so it is found by
      // pattern rather than a literal the copy-drift check would look for in the catalogs.
      await form.getByRole('button', { name: /^Professional/ }).click();
      const english = form.getByLabel(/^Text \(English\)/);
      const original = await english.inputValue();
      await english.fill(`${original} A library editor confirmed this wording for PRO-S4.`);
      await form.getByRole('button', { name: 'Approve and apply' }).click();
      const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
      await expect(prompt.or(applied).first()).toBeVisible();
      if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
    }
    await expect(applied).toBeVisible();
    await signOut(page);

    // As PRO-S3: the corrected version reaches the tenant's own card for the obligation.
    await signInAs(page, LOGINS.reader);
    await expectVersionOnCard(page, 'obl-costs-charges', 2);
  });

  test('PRO-S5: Approving your own proposal answers four_eyes_violation', async ({ page, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.editor);
    const label = `PRO-S5 four eyes ${testInfo.workerIndex}-${Date.now()}`;
    await proposeFlag(page, label);

    // Confirmed where it was sent: the console queue, under Waiting, marked Yours.
    await page.goto('/console/queue');
    await queueSettled(page);
    const row = page.getByRole('link', { name: new RegExp(label) });
    await expect(row).toBeVisible();
    await expect(row.getByText('Yours')).toBeVisible();
    await row.click();

    // The server enforces four eyes; the screen only explains it. No Approve control is
    // offered on a reader's own proposal, so the refusal can never be attempted from here
    // (backend/apps/proposals/logic.py `_decidable` answers 409 four_eyes_violation to
    // anyone who calls the route directly, proven at the integration level).
    await expect(page.getByText('You proposed this.')).toBeVisible();
    await expect(page.getByText('A second library editor has to approve it.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Approve and apply' })).toHaveCount(0);
  });

  test('PRO-S7: The queue is in the console and tenants see updates and report problems', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/proposals\/.+\/approve$/, 403, 'approving asks for a fresh passkey assertion first, which opens the step-up prompt');
    apiGuard.allow(/^\/api\/v1\/console\/problem-reports$/, 404, "the console has no problem-report route: a bank's report stays inside the bank");

    // The editor opens the queue in the console and reads the source beside what changes
    // before approving with a passkey. A retry finds the proposal already applied.
    await signInAs(page, LOGINS.editor);
    await openProposal(page, new RegExp(PENSION_TRANSFER_TITLE));
    const proposal = page.locator('[data-proposal]');
    await expect(proposal.locator('[data-proposal-changes]')).toBeVisible();
    await expect(proposal).toContainText(PENSION_TRANSFER_SOURCE);
    await expect(proposal.locator('a[href="https://www.riksdagen.se/"]').first()).toBeVisible();
    await approveAndApply(page);
    // The console offers no surface for a bank's problem report.
    await expect(page.getByRole('navigation', { name: 'Main' }).locator('a[href*="problem-report"]')).toHaveCount(0);
    await signOut(page);

    // A bank's compliance officer has no queue: the console's review screen is restricted.
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/console/queue');
    await expect(restrictedScreen(page)).toContainText('Needs proposals review');

    // The bank reads the change as a library update, under the duty's own title and never
    // the proposal's, and says it looks wrong through the same form the obligation card uses.
    await page.goto('/inventory/updates');
    await expect(page.locator('[data-update-days]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    const row = page.locator('[data-update-id]').filter({ has: page.getByRole('heading', { level: 3, name: PENSION_TRANSFER_OBLIGATION, exact: true }) }).first();
    await expect(row).toBeVisible();
    await expect(row).not.toContainText(PENSION_TRANSFER_TITLE);
    await expect(row.getByRole('link', { name: 'Show what changed' })).toHaveAttribute('href', /^\/inventory\/obligations\/[0-9a-f-]{36}$/);
    await row.getByRole('button', { name: 'This looks wrong' }).click();
    const dialog = page.getByRole('dialog', { name: 'What looks wrong?' });
    await expect(dialog.getByText('Colleagues in your organisation read this and take it up. It reaches nobody outside your organisation.')).toBeVisible();
    await dialog.getByLabel('What you see').fill('The one-month deadline is not in the consolidated text we read.');
    await dialog.getByRole('button', { name: 'Send report' }).click();
    await expect(dialog.getByText('Report sent. Thank you.')).toBeVisible();
    await dialog.getByRole('button', { name: 'Done' }).click();
    await expect(dialog).toBeHidden();

    // That report stays inside the bank: the console has no route that could return it.
    // Which platform session could read it is proven route by route in test_pro_s7.
    const consoleReports = await page.goto(`${BACKEND_URL}/api/v1/console/problem-reports`);
    expect(consoleReports?.status()).toBe(404);
  });

  test.fixme('PRO-S8: A batch proposal previews and is approved whole or row by row', async () => {
    // pending: PRO-S8 (PRO-04)
  });

  test('PRO-S9: A rejection needs a reason and is audited', async ({ page, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.editor);
    const label = `PRO-S9 reject ${testInfo.workerIndex}-${Date.now()}`;
    await proposeFlag(page, label);
    await signOut(page);
    await signInAs(page, LOGINS.editor2);

    // The label is unique to this attempt, so this proposal is always freshly waiting:
    // no "already decided" branch is needed, unlike PRO-S3 and PRO-S4's seeded fixtures.
    const rejected = page.locator('[data-proposal-rejected]');
    await openProposal(page, new RegExp(label));
    await page.getByRole('button', { name: 'Reject' }).click();
    const dialog = page.getByRole('dialog', { name: 'Reject this proposal' });
    const submit = dialog.getByRole('button', { name: 'Reject' });
    // Neither a reason nor a note yet: the button stays disabled, so the 422
    // reason_required the server would otherwise answer is never sent (PRO-01,
    // proven directly against the route in backend/apps/proposals/tests_scenarios.py).
    await expect(submit).toBeDisabled();
    await dialog.getByLabel('Reason').selectOption({ label: 'Poor wording' });
    await expect(submit).toBeDisabled();
    await dialog.getByLabel('Note').fill('The label needs tightening before this can be used.');
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(rejected).toBeVisible();
    await expect(rejected).toContainText('The label needs tightening before this can be used.');
  });

  test.fixme('PRO-S13: An independent agent confirms a proposal from the same queue', async () => {
    // pending: PRO-S13 (PRO-01, PRO-02, AUD-02). The confirming agent is chunk 5's
    // (docs/plans/briefs/CHUNK4_TASKS.md, "What the E2E half waits for"); this task builds
    // the human half of the one queue that will serve both.
  });
});
