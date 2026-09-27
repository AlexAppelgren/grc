import { execFileSync } from 'node:child_process';
import path from 'node:path';

import type { APIRequestContext, Page } from '@playwright/test';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, mailOutbox, mailsTo, signInAs, signOut } from './support/passkeys';
import { signInAsSv } from './support/watch-coverage';

// collab: the @e2e scenarios from backend/apps/collab/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

// The seeded cases each journey spends (backend/apps/shared/e2e_seed.py,
// `EXPECTED_CASE_JOURNEYS`): data, not catalog copy.
const COL_S1 = { stableKey: 'chg-e2e-case-comment', title: 'FI amends the custody rules for client assets', mention: 'Oskar Lund' };
const COL_S2 = { title: 'FI amends the rules on pension transfers' };

/** A worked case's change page, from the feed's In progress tab, searched by its title. */
async function openCaseChange(page: Page, stableKey: string, title: string): Promise<void> {
  await page.goto('/watch?scope=all');
  await page.getByRole('tab', { name: 'In progress' }).click();
  await page.getByRole('searchbox', { name: 'Search these changes' }).fill(title);
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.locator(`[data-change-rows] [data-change="${stableKey}"]`).click();
  await expect(page).toHaveURL(/\/watch\/[0-9a-f-]{36}$/);
  await expect(page.locator(`[data-change="${stableKey}"]`)).toBeVisible();
}

// `manage.py e2e_collab_jobs`: tenant A's reminders, escalations and digests now, as the
// worker's hourly beat runs them at the bank's send hours. The mails leave through the
// real worker, so the journey polls the mock outbox for them.
function runCollabJobs(): void {
  // Forward slashes: bash opens the script by this path, and a Windows checkout hands path.join backslashes.
  const script = path.join(test.info().project.testDir, 'support', 'start-backend.sh').split(path.sep).join('/');
  execFileSync('bash', [script, 'manage', 'e2e_collab_jobs'], { encoding: 'utf8' });
}

async function subjectsTo(request: APIRequestContext, address: string): Promise<string[]> {
  return mailsTo(await mailOutbox(request), address).map((m) => m.subject);
}

test.describe('collab journeys', () => {
  test("COL-S1: A comment with a mention notifies the mentioned person", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    // Given a case and a contributor with comments.write
    await signInAs(page, LOGINS.contributor);
    await openCaseChange(page, COL_S1.stableKey, COL_S1.title);
    const panel = page.locator('[data-comments-panel="change_case"]');
    await expect(panel).toBeVisible();

    // When they comment "@Oskar can you check the custody angle?", picking Oskar from the list
    const box = panel.getByLabel('Add a comment');
    await box.click();
    await box.pressSequentially('@Osk');
    await page.getByRole('listbox', { name: 'People to mention' }).getByRole('option', { name: new RegExp(`^${COL_S1.mention}`) }).click();
    await box.press('End');
    await box.pressSequentially('can you check the custody angle?');
    const posted = page.waitForResponse((r) => r.url().endsWith('/api/v1/comments') && r.request().method() === 'POST');
    await panel.getByRole('button', { name: 'Comment', exact: true }).click();
    const response = await posted;
    expect(response.status()).toBe(201);
    const created = (await response.json()) as { id: string; undeliveredMentions: unknown[] };
    expect(created.undeliveredMentions).toEqual([]);

    // Then the comment is stored against the case and shows in its thread
    await expect(panel.locator('[data-comment-list] li').filter({ hasText: `${COL_S1.mention} can you check the custody angle?` }).first()).toBeVisible();

    // And Oskar receives a notification naming the case
    await signOut(page);
    await signInAs(page, LOGINS.reader);
    await page.goto('/notifications');
    await expect(page.getByRole('heading', { level: 1, name: 'Notifications' })).toBeVisible();
    const told = page.locator('[data-notification-id]').filter({ hasText: COL_S1.title }).first();
    await expect(told).toBeVisible();
    await expect(told).toContainText('Mention');
  });

  test("COL-S2: Reminders, escalation and the digest reach people in their language", async ({ page, request, apiGuard }) => {
    allowFreshContext(apiGuard);
    // Given an action due in three days and one five days overdue, both owned by the
    // Swedish-speaking member, and the bank's lead of three days and threshold of five
    // When the reminder, escalation and digest jobs run
    runCollabJobs();

    // Then she receives the reminder, the escalation and her digest, each in sv
    await expect
      .poll(() => subjectsTo(request, LOGINS.svMember), { timeout: 30_000 })
      .toEqual(
        expect.arrayContaining([
          expect.stringMatching(new RegExp(`^Förfaller \\d{4}-\\d{2}-\\d{2}: ${COL_S2.title}$`)),
          `Eskalerad till dig: ${COL_S2.title}`,
          expect.stringMatching(/^Dina öppna uppgifter, veckan från \d{4}-\d{2}-\d{2}: \d+$/),
        ]),
      );
    // And the head of the department of her team and the compliance officer are escalated to, in en
    for (const person of [LOGINS.departmentHead, LOGINS.complianceOfficer]) {
      await expect.poll(() => subjectsTo(request, person), { timeout: 30_000 }).toContain(`Escalated to you: ${COL_S2.title}`);
    }

    // And her own inbox, in Swedish, lists the reminder and the escalation on the case
    await signInAsSv(page, LOGINS.svMember);
    await page.goto('/notifications');
    await expect(page.getByRole('heading', { level: 1, name: 'Aviseringar' })).toBeVisible();
    const rows = page.locator('[data-notification-id]').filter({ hasText: COL_S2.title });
    await expect(rows.filter({ hasText: 'Förfaller snart' }).first()).toBeVisible();
    await expect(rows.filter({ hasText: 'Eskalerad' }).first()).toBeVisible();
  });

  test.fixme("COL-S4: A user follows a record and hears about changes", async () => {
    // pending: COL-S4 (COL-03)
  });
});

// PRD 0.3: participants on register entries and cases (COL-04) and the
// comments and mentions panel on My work (COL-01, HOM-05). Each stays
// test.fixme until the task in docs/plans/briefs/FEATURES_0_3_TASKS.md lands.
test.describe('participants, comments and mentions', () => {
  test.fixme("COL-S6: A person or a team is added to a register entry, audited, and gains no access", async () => {
    // pending: COL-S6 (COL-04, AC-COL1)
  });

  test.fixme("COL-S7: A participant leaves a register entry on their own", async () => {
    // pending: COL-S7 (COL-04)
  });

  test.fixme("COL-S9: Case participants are managed by those who contribute, and refused across tenants", async () => {
    // pending: COL-S9 (COL-04, AC-COL1, NFR-01)
  });

  test.fixme("COL-S12: My comments and mentions are found on My work, limited to what I can read, and never logged", async () => {
    // pending: COL-S12 (COL-01, HOM-05)
  });
});
