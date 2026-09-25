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
// c9-fe-case-participants: COL-S9's case, as the seed names it (CASE_PARTICIPATION_CHANGE).
const CASE_PARTICIPATION_CHANGE = 'chg-e2e-sft-reporting';
const CASE_PARTICIPATION_TITLE = 'Amended reporting of securities financing transactions';

/**
 * Opens COL-S9's case from its card on the roadmap and returns the change's id. The feed's
 * in-progress tab lists `assigned` cases only until chunk 9 widens it, so a case being
 * assessed is reached from its regulatory date instead.
 */
async function openCase(page: Page): Promise<string> {
  await page.goto('/roadmap');
  await page.getByRole('button', { name: new RegExp(CASE_PARTICIPATION_TITLE) }).click();
  await page.locator('[data-roadmap-detail]').getByRole('link', { name: 'Open change' }).click();
  await expect(page).toHaveURL(/\/watch\/[0-9a-f-]{36}$/);
  await expect(page.locator(`[data-change="${CASE_PARTICIPATION_CHANGE}"] [data-participants-panel]`)).toBeVisible();
  return new URL(page.url()).pathname.split('/').at(-1) ?? '';
}

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

  // c9-fe-case-participants: tenant A's case for the securities financing change, being
  // assessed, with the team Legal, Johan Berg and the Reader taking part, each added by the
  // compliance officer (CASE_PARTICIPATION_* in apps/shared/e2e_seed.py). The contributor holds
  // cases.contribute but not register.edit. Another bank's reach is proven by the scenario's
  // integration test (apps/collab/tests_case_participants.py); here, tenant B's page for the
  // same change shows none of tenant A's people.
  test("COL-S9: Case participants are managed by those who contribute, and refused across tenants", async ({ page, apiGuard, browser }, testInfo) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.contributor);
    const changeId = await openCase(page);
    const panel = page.locator('[data-participants-panel]');
    const named = (name: string) => panel.locator('[data-participant-id]').filter({ has: page.getByRole('heading', { name, exact: true }) });
    const writes: string[] = [];
    page.on('request', (r) => {
      if (/\/changes\/[^/]+\/participants/.test(r.url()) && r.method() !== 'GET') writes.push(r.method());
    });
    let added: string | null = null;
    let johanRemoved = false;
    let readerLeft = false;
    let teamAdded = false;

    try {
      // The owner sits read-only above the list; each row names who added it.
      await expect(panel.locator('[data-participant-owners]')).toContainText('Sara Lindqvist');
      await expect(panel.locator('[data-participant-owners]').getByRole('button')).toHaveCount(0);
      await expect(named('Legal').getByText('Team', { exact: true })).toBeVisible();
      await expect(named('Legal')).toContainText(/Added .+ by Sara Lindqvist/);

      // When the contributor adds Maria Ek, the answer is 201.
      added = await addParticipant(page, panel, 'Maria', /^Maria Ek/);
      await expect(panel.locator(`[data-participant-id="${added}"]`)).toContainText(/Added .+ by Karin Nyström/);

      // When they remove Johan Berg, the answer is 204.
      const removing = page.waitForResponse((r) => r.url().includes('/participants/') && r.request().method() === 'DELETE');
      await named('Johan Berg').getByRole('button', { name: 'Remove' }).click();
      expect((await removing).status()).toBe(204);
      johanRemoved = true;
      await expect(named('Johan Berg')).toHaveCount(0);

      // The assessment's contributor teams are the team participants, one call per change.
      const teams = page.locator('[data-contributor-teams]');
      await expect(teams.getByText('Legal', { exact: true })).toBeVisible();
      writes.length = 0;
      await teams.getByRole('button', { name: 'Add a team' }).click();
      const dialog = page.getByRole('dialog', { name: 'Add a contributor team' });
      await dialog.getByRole('radio', { name: /^Retail compliance/ }).click();
      const teamAdd = page.waitForResponse((r) => r.url().endsWith('/participants') && r.request().method() === 'POST');
      await dialog.getByRole('button', { name: 'Add' }).click();
      expect((await teamAdd).status()).toBe(201);
      teamAdded = true;
      await expect(dialog).toBeHidden();
      await expect(named('Retail compliance')).toHaveCount(1);
      const teamRemove = page.waitForResponse((r) => r.url().includes('/participants/') && r.request().method() === 'DELETE');
      await teams.getByRole('button', { name: 'Remove Retail compliance' }).click();
      expect((await teamRemove).status()).toBe(204);
      teamAdded = false;
      await expect(named('Retail compliance')).toHaveCount(0);
      expect(writes).toEqual(['POST', 'DELETE']);

      // A Reader who takes part may only leave their own row.
      const reader = await signInElsewhere(browser, testInfo.project.use.baseURL, apiGuard, LOGINS.reader);
        await reader.goto(`/watch/${changeId}`);
      const theirs = reader.locator('[data-participants-panel]');
      const own = theirs.locator('[data-participant-id]').filter({ has: reader.getByRole('heading', { name: 'Oskar Lund', exact: true }) });
      await expect(own.getByText('You', { exact: true })).toBeVisible();
      await expect(theirs.getByRole('button', { name: 'Add a participant' })).toHaveCount(0);
      await expect(theirs.getByRole('button', { name: 'Remove' })).toHaveCount(0);
      const leaving = reader.waitForResponse((r) => r.url().includes('/participants/') && r.request().method() === 'DELETE');
      await own.getByRole('button', { name: 'Leave' }).click();
      expect((await leaving).status()).toBe(204);
      readerLeft = true;
      await expect(own).toHaveCount(0);
      await reader.context().close();

      // Tenant B's page for the same change shows none of tenant A's people.
      const other = await signInElsewhere(browser, testInfo.project.use.baseURL, apiGuard, LOGINS.secondBankAdmin);
      apiGuard.allow(new RegExp(`/api/v1/changes/${changeId}$`), 404, 'tenant B cannot open a change outside its own scope');
      await other.goto(`/watch/${changeId}`);
      await expect(other.locator('[data-change-classification]').or(other.locator('[data-empty-state]')).or(other.getByRole('alert')).first()).toBeVisible();
      await expect(other.getByText('Sara Lindqvist')).toHaveCount(0);
      await expect(other.getByText('Maria Ek')).toHaveCount(0);
      await other.context().close();
    } finally {
      // The compliance officer puts the case's participants back, as the seed had them.
      if (added !== null || johanRemoved || readerLeft || teamAdded) {
        const officer = await signInElsewhere(browser, testInfo.project.use.baseURL, apiGuard, LOGINS.complianceOfficer);
            await officer.goto(`/watch/${changeId}`);
        const theirs = officer.locator('[data-participants-panel]');
        await expect(theirs.locator('[data-participant-id]').first()).toBeVisible();
        for (const name of ['Maria Ek', 'Retail compliance']) {
          const row = theirs.locator('[data-participant-id]').filter({ has: officer.getByRole('heading', { name, exact: true }) });
          if ((await row.count()) === 0) continue;
          await row.getByRole('button', { name: 'Remove' }).click();
          await expect(row).toHaveCount(0);
        }
        if (johanRemoved) await addParticipant(officer, theirs, 'Johan', /^Johan Berg/);
        if (readerLeft) await addParticipant(officer, theirs, 'Oskar', /^Oskar Lund/);
        await officer.context().close();
      }
    }
  });

  test.fixme("COL-S12: My comments and mentions are found on My work, limited to what I can read, and never logged", async () => {
    // pending: COL-S12 (COL-01, HOM-05)
  });
});
