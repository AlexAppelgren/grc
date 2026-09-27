import type { Locator, Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowRegisterEntryPending, openObligation, signInElsewhere } from './support/obligation-page';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';

// collab: the @e2e scenarios from backend/apps/collab/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('collab journeys', () => {
  test.fixme("COL-S1: A comment with a mention notifies the mentioned person", async () => {
    // pending: COL-S1 (COL-01)
  });

  test.fixme("COL-S2: Reminders, escalation and the digest reach people in their language", async () => {
    // pending: COL-S2 (COL-02)
  });

  test.fixme("COL-S4: A user follows a record and hears about changes", async () => {
    // pending: COL-S4 (COL-03)
  });
});

// c8-ui-links-history-participants: the obligations of COL-S6 and COL-S7, as the seed names them.
const NO_ENTRY_OBLIGATION = 'obl-idd-demands-needs';
const PARTICIPATION_OBLIGATION = 'obl-costs-charges';
// c8-ui-mywork: the obligation the seeded comments are on (apps/shared/e2e_seed.py).
const DORA_REGISTER = 'Keep a register of information on ICT third-party arrangements';

/** Adds one person or team through the picker and returns the new participant's id. */
async function addParticipant(page: Page, panel: Locator, search: string, name: RegExp): Promise<string> {
  await panel.getByRole('button', { name: 'Add a participant' }).click();
  const dialog = page.getByRole('dialog', { name: 'Add a participant' });
  await dialog.getByRole('searchbox', { name: 'Person or team' }).fill(search);
  await dialog.getByRole('radio', { name }).click();
  const added = page.waitForResponse((r) => r.url().endsWith('/participants') && r.request().method() === 'POST');
  await dialog.getByRole('button', { name: 'Add' }).click();
  const response = await added;
  expect(response.status()).toBe(201);
  await expect(dialog).toBeHidden();
  return ((await response.json()) as { id: string }).id;
}

// PRD 0.3: participants on register entries and cases (COL-04) and the
// comments and mentions panel on My work (COL-01, HOM-05). Each stays
// test.fixme until the task in docs/plans/briefs/FEATURES_0_3_TASKS.md lands.
test.describe('participants, comments and mentions', () => {
  // c8-ui-links-history-participants: the compliance officer adds Erik Holm, an administrator
  // without register.edit, and the team Legal to an obligation the bank has no register
  // entry for yet (NO_ENTRY_OBLIGATION in apps/shared/e2e_seed.py).
  test("COL-S6: A person or a team is added to a register entry, audited, and gains no access", async ({ page, apiGuard, browser }, testInfo) => {
    allowFreshContext(apiGuard);
    allowRegisterEntryPending(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openObligation(page, NO_ENTRY_OBLIGATION);
    const panel = page.locator('[data-participants-panel]');
    await expect(panel.locator('[data-participants-empty]').or(panel.locator('[data-participant-id]')).first()).toBeVisible();
    const added: string[] = [];

    try {
      added.push(await addParticipant(page, panel, 'Erik', /^Erik Holm/));
      added.push(await addParticipant(page, panel, 'Legal', /^Legal/));
      const erik = panel.locator(`[data-participant-id="${added[0]}"]`);
      await expect(erik).toContainText('Erik Holm');
      await expect(erik).toContainText(/Added .+ by Sara Lindqvist/);
      const legal = panel.locator(`[data-participant-id="${added[1]}"]`);
      await expect(legal.getByText('Team', { exact: true })).toBeVisible();
      await expect(legal).toContainText(/Added .+ by Sara Lindqvist/);

      // Adding Erik again is refused by its code, in place.
      apiGuard.allow(/\/participants$/, 409, 'COL-S6 adds Erik a second time on purpose');
      await panel.getByRole('button', { name: 'Add a participant' }).click();
      const dialog = page.getByRole('dialog', { name: 'Add a participant' });
      await dialog.getByRole('searchbox', { name: 'Person or team' }).fill('Erik');
      await dialog.getByRole('radio', { name: /^Erik Holm/ }).click();
      await dialog.getByRole('button', { name: 'Add' }).click();
      await expect(dialog.getByText('Erik Holm already takes part in this obligation.')).toBeVisible();
      await dialog.getByRole('button', { name: 'Cancel' }).click();

      // Taking part granted Erik nothing: he may leave his own row, and still cannot add,
      // remove anyone else or write how the bank reads the rule.
      const erikPage = await signInElsewhere(browser, testInfo.project.use.baseURL, apiGuard, LOGINS.admin);
      await openObligation(erikPage, NO_ENTRY_OBLIGATION);
      const hisPanel = erikPage.locator('[data-participants-panel]');
      const own = hisPanel.locator(`[data-participant-id="${added[0]}"]`);
      await expect(own.getByText('You', { exact: true })).toBeVisible();
      await expect(own.getByRole('button', { name: 'Leave' })).toBeVisible();
      await expect(hisPanel.locator(`[data-participant-id="${added[1]}"]`).getByRole('button')).toHaveCount(0);
      await expect(hisPanel.getByRole('button', { name: 'Add a participant' })).toHaveCount(0);
      await expect(erikPage.locator('[data-history-panel] [data-reading]')).toBeVisible();
      await expect(erikPage.locator('[data-history-panel]').getByRole('button', { name: 'Write how we read it' })).toHaveCount(0);
      await erikPage.context().close();
    } finally {
      for (const id of added) {
        const row = panel.locator(`[data-participant-id="${id}"]`);
        if ((await row.count()) === 0) continue;
        await row.getByRole('button', { name: 'Remove' }).click();
        await expect(row).toHaveCount(0);
      }
    }
  });

  // c8-ui-links-history-participants: the Reader the seed made a participant of the costs and
  // charges duty (PARTICIPANT and PARTICIPATION_OBLIGATION in apps/shared/e2e_seed.py).
  test("COL-S7: A participant leaves a register entry on their own", async ({ page, apiGuard, browser }, testInfo) => {
    allowFreshContext(apiGuard);
    allowRegisterEntryPending(apiGuard);
    await signInAs(page, LOGINS.reader);
    await openObligation(page, PARTICIPATION_OBLIGATION);
    const panel = page.locator('[data-participants-panel]');
    const own = panel.locator('[data-participant-id]').filter({ hasText: 'Oskar Lund' });
    let left = false;

    try {
      await expect(own).toHaveCount(1);
      await expect(own.getByText('You', { exact: true })).toBeVisible();
      await expect(own).toContainText(/Added .+ by Sara Lindqvist/);
      // A Reader cannot add, and is offered nothing on anyone else's row.
      await expect(panel.getByRole('button', { name: 'Add a participant' })).toHaveCount(0);
      await expect(panel.getByRole('button', { name: 'Remove' })).toHaveCount(0);

      const leaving = page.waitForResponse((r) => r.url().includes('/participants/') && r.request().method() === 'DELETE');
      await own.getByRole('button', { name: 'Leave' }).click();
      expect((await leaving).status()).toBe(204);
      left = true;
      await expect(own).toHaveCount(0);
      await page.reload();
      await expect(panel.locator('[data-participants-empty]').or(panel.locator('[data-participant-id]')).first()).toBeVisible();
      await expect(own).toHaveCount(0);
    } finally {
      // The compliance officer puts the Reader back, as the seed had it.
      if (left) {
        const officer = await signInElsewhere(browser, testInfo.project.use.baseURL, apiGuard, LOGINS.complianceOfficer);
        await openObligation(officer, PARTICIPATION_OBLIGATION);
        await addParticipant(officer, officer.locator('[data-participants-panel]'), 'Oskar', /^Oskar Lund/);
        await officer.context().close();
      }
    }
  });

  test.fixme("COL-S9: Case participants are managed by those who contribute, and refused across tenants", async () => {
    // pending: COL-S9 (COL-04, AC-COL1, NFR-01)
  });

  // c8-ui-mywork. The scenario's Anna is the seeded Reader, Oskar Lund, mentioned on a case by
  // Sara Lindqvist and on the DORA register by Karin Nyström; the author of My comments is the
  // owner, Johan Berg, whose case comment stands and whose other was deleted; Johan-without-
  // cases.read is the library-only login, Axel Norén, mentioned on the same case
  // (EXPECTED_COMMENTS in apps/shared/e2e_seed.py). That the log, the audit row and the outbox
  // never hold the text is proved in apps/collab/tests_scenarios.py.
  test("COL-S12: My comments and mentions are found on My work, limited to what I can read, and never logged", async ({ page, apiGuard, browser }, testInfo) => {
    allowFreshContext(apiGuard);
    allowRegisterEntryPending(apiGuard);
    await signInAs(page, LOGINS.reader);
    await page.goto('/work');
    const panel = page.locator('[data-my-comments-panel]');
    await expect(panel.getByRole('tab', { name: 'Mentions' })).toHaveAttribute('aria-selected', 'true');
    const onCase = panel.locator('[data-my-comment]').filter({ hasText: 'Sara Lindqvist mentioned you' });
    await expect(onCase).toHaveCount(1);
    await expect(panel.locator('[data-my-comment]').filter({ hasText: 'Karin Nyström mentioned you' }).getByRole('link', { name: DORA_REGISTER })).toBeVisible();

    // The mention links to the case, where the comment was written and where a reply is.
    await onCase.getByRole('link').click();
    await expect(page).toHaveURL(/\/watch\/[^/?]+$/);
    const thread = page.locator('[data-comments-panel="change_case"]');
    await expect(thread.getByText('Everyone in your organisation can read comments.')).toBeVisible();

    // My comments: the owner's own, newest first; the one he deleted is gone.
    const johan = await signInElsewhere(browser, testInfo.project.use.baseURL, apiGuard, LOGINS.owner);
    await johan.goto('/work');
    const his = johan.locator('[data-my-comments-panel]');
    await his.getByRole('tab', { name: 'My comments' }).click();
    await expect(his.getByRole('tab', { name: 'My comments' })).toHaveAttribute('aria-selected', 'true');
    await expect(his.locator('[data-my-comment]').first()).toBeVisible();
    await expect(his.locator('[data-my-comment]').filter({ hasText: DORA_REGISTER })).toHaveCount(0);
    await johan.context().close();

    // A role without cases.read gets no case comment, and is told cases are held back.
    const axel = await signInElsewhere(browser, testInfo.project.use.baseURL, apiGuard, LOGINS.libraryOnly);
    await axel.goto('/work');
    const limited = axel.locator('[data-my-comments-panel]');
    await expect(limited.getByText('Cases are not shown here, because your role cannot open them')).toBeVisible();
    await expect(limited.locator('[data-my-comment]').filter({ hasText: 'Sara Lindqvist mentioned you' })).toHaveCount(0);
    await expect(axel.getByText('Changes are not shown here, and are left out of the counts, because your role cannot open them.')).toBeVisible();
    await axel.context().close();
  });
});
