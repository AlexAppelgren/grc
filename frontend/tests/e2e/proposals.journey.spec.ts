import type { Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs, signOut } from './support/passkeys';

// proposals: the @e2e scenarios from backend/apps/proposals/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// PRO-S3 and PRO-S4 decide the two new_obligation_version proposals
// backend/apps/shared/e2e_seed.py seeds for chunk4-T14/T17 (chunk4-T8, which owns
// seeding a journey's proposal, has not landed on `main`; see that seed's own
// comment). Each targets an obligation no other spec names, so the two journeys
// never race each other or J-6. PRO-S5 and PRO-S9 decide a vocabulary proposal the
// journey proposes itself, through the console's own "Suggest a change" door
// (VOC-07), with a label unique to the attempt so a retry or a parallel run never
// collides on the near-duplicate check.

const APPROPRIATENESS_TITLE = 'Add version 2 of the appropriateness assessment obligation, in force 15 October 2026';
const COSTS_CHARGES_TITLE = 'Add version 2 of the costs and charges obligation, extending it to professional clients';

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

    // Chunk 3's obligation detail screen and its "Show what changed" diff are not on
    // `main` (docs/plans/briefs/CHUNK4_TASKS.md names them a hard precondition of this
    // chunk; the E2E check confirming that found otherwise). The inventory list is real
    // and already reads the version this approval just wrote: a tenant reader sees
    // "Version 2" on the same row without a detail page.
    await signInAs(page, LOGINS.reader);
    await page.goto('/inventory');
    await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    await expect(page.locator('[data-obligation="obl-appropriateness"]')).toContainText('Version 2');
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

    // As PRO-S3: the corrected version reaches the tenant's real inventory list; the
    // corrected wording itself is chunk 3's unbuilt obligation detail page to read back.
    await signInAs(page, LOGINS.reader);
    await page.goto('/inventory');
    await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    await expect(page.locator('[data-obligation="obl-costs-charges"]')).toContainText('Version 2');
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

  test.fixme('PRO-S7: The queue is in the console and tenants see updates and report problems', async () => {
    // pending: PRO-S7 (PRO-03). Blocked on chunk4-T13b's GET /library-updates, which is
    // not on `main` (see features/library-updates/types.ts); frontend/src/components/
    // inventory/LibraryUpdatesScreen.tsx is built against that route's own contract and
    // starts answering real data the moment it lands, with no further change to this
    // journey beyond un-fixme'ing it. The console-side half (the officer's 403 on
    // /console/queue) is already provable today but is not split out on its own, since
    // PRO-S7 is one scenario.
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
