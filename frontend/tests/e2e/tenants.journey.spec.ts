import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, restrictedScreen, signInAs, signOut } from './support/passkeys';

// tenants: the @e2e scenarios from backend/apps/tenants/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('tenants journeys', () => {
  test("TEN-S1: A tenant profile holds timezone, languages and the onboarding checklist", async ({ page, apiGuard }) => {
    // pending: TEN-S1 (TEN-01) -> built in chunk 1. Deadlines do not exist yet, so the
    // Helsinki rendering of a deadline waits for the first screen that shows one.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/organisation');
    await expect(page.getByRole('heading', { level: 1, name: 'Organisation' })).toBeVisible();
    const checklist = page.locator('[data-onboarding]');
    await expect(checklist).toBeVisible();
    // The checklist names footprint, members and vocabularies among its steps; a step not
    // done yet links to the screen that does it. Tenant A is not new: its seeded footprint
    // (chunk 2) ticks that step, and nothing ticks vocabularies yet.
    await expect(checklist.locator('[data-step]')).toHaveCount(5);
    for (const step of ['footprint', 'members', 'vocabularies']) {
      await expect(checklist.locator(`[data-step="${step}"]`)).toHaveCount(1);
    }
    await expect(checklist.locator('[data-step="footprint"][data-done]')).toHaveCount(1);
    const vocabularies = checklist.locator('[data-step="vocabularies"]:not([data-done])');
    await expect(vocabularies.getByRole('link', { name: 'Review the vocabularies' })).toHaveAttribute('href', '/admin/vocabularies');

    try {
      await page.getByLabel('Timezone').fill('Europe/Helsinki');
      // Language labels come from their rows (each in its own language), not the catalog.
      for (const language of [/^Suomi/, /^Svenska/, /^English/]) {
        await page.locator('label', { hasText: language }).getByRole('checkbox').check();
      }
      await page.getByRole('button', { name: 'Save' }).click();
      await expect(page.getByText('Saved.')).toBeVisible();

      await page.reload();
      await expect(page.getByLabel('Timezone')).toHaveValue('Europe/Helsinki');
      await expect(page.locator('label', { hasText: /^Suomi/ }).getByRole('checkbox')).toBeChecked();
      await expect(page.locator('label', { hasText: /^Svenska/ }).getByRole('checkbox')).toBeChecked();
      await expect(page.locator('label', { hasText: /^English/ }).getByRole('checkbox')).toBeChecked();
    } finally {
      // Restore the seeded profile whatever happened above.
      await page.goto('/admin/organisation');
      await page.getByLabel('Timezone').fill('Europe/Stockholm');
      await page.locator('label', { hasText: /^Suomi/ }).getByRole('checkbox').uncheck();
      await page.getByRole('button', { name: 'Save' }).click();
      await expect(page.getByText('Saved.')).toBeVisible();
    }
  });

  test.fixme("TEN-S2: Legal entities and products are scoped like obligations", async () => {
    // pending: TEN-S2 (TEN-02)
  });

  test.fixme("TEN-S4: An out-of-office delegate receives approvals and reminders", async () => {
    // pending: TEN-S4 (TEN-04)
  });

  test.fixme("TEN-S5: Removing a member with open work offers bulk reassignment", async () => {
    // pending: TEN-S5 (TEN-05)
  });

  test.fixme("TEN-S6: A support access grant is visible, time-boxed and logged", async () => {
    // pending: TEN-S6 (TEN-06)
  });

  test("TEN-S7 J-8 @smoke: tenant B cannot see tenant A", async ({ page, apiGuard }) => {
    // pending: TEN-S7 (TEN-06, J-8) -> built in chunk 1 for members; cases, evidence and
    // vocabularies join the journey as their screens land.
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/members\/[^/]+\/sessions$/, 404, "another tenant's member is not there, never forbidden");

    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/members');
    const memberOfA = page.locator('[data-member-id]', { hasText: LOGINS.reader });
    await expect(memberOfA).toBeVisible();
    const memberUrl = await memberOfA.getAttribute('href');
    expect(memberUrl).toMatch(/^\/admin\/members\/.+/);
    await signOut(page);

    await signInAs(page, LOGINS.secondBankAdmin);
    await expect(page.locator('[data-who-panel]')).toContainText('Second Bank A/S');
    await page.goto(memberUrl ?? '/admin/members/none');
    await expect(page.getByRole('heading', { level: 1, name: 'Not found' })).toBeVisible();
    await expect(page.getByText('This page is not available to you')).toHaveCount(0);

    await page.goto('/admin/members');
    const rows = page.locator('[data-member-id]');
    await expect(rows.first()).toBeVisible();
    const emails = await rows.allTextContents();
    expect(emails.length).toBeGreaterThan(0);
    for (const text of emails) {
      expect(text).toContain('second-bank.test');
      expect(text).not.toContain('example-bank.test');
    }
  });

  test("ADM-S1: Tenant admin surfaces are gated by their own permissions", async ({ page, apiGuard }) => {
    // pending: ADM-S1 (ADM-01, ADM-03) -> built in chunk 1. No seeded role holds
    // members.manage alone, so the admin proves what is reachable and the compliance
    // officer (vocab and workflow, no members) proves what is not.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin');
    for (const section of ['admin-organisation', 'admin-members', 'admin-roles', 'admin-api-keys', 'admin-security-log']) {
      await expect(page.locator(`[data-admin-section="${section}"]`)).toBeVisible();
    }
    await signOut(page);

    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/admin');
    await expect(page.locator('[data-admin-section="admin-organisation"]')).toBeVisible();
    await expect(page.locator('[data-admin-section="admin-members"]')).toHaveCount(0);
    await expect(page.locator('[data-admin-section="admin-security-log"]')).toHaveCount(0);
    await page.goto('/admin/members');
    await expect(restrictedScreen(page)).toContainText('Needs members manage');
  });

  test.describe('the member ADM-S2 spends', () => {
    // Re-issue cannot be undone, so a retry would run against a member the first attempt
    // already spent and fail for that, not for the real cause. Like Anna's chain in the
    // identity journeys, it never retries; the first failure is the real one.
    test.describe.configure({ retries: 0 });

    test("ADM-S2: The members screen invites, assigns roles, re-issues enrolment and revokes sessions", async ({ page, apiGuard }) => {
      // pending: ADM-S2 (ADM-01) -> built in chunk 1
      allowFreshContext(apiGuard);
      apiGuard.allow(/\/tenant\/members\/[^/]+$/, 403, 'the role change answers step_up_required first and opens the prompt');
      await signInAs(page, LOGINS.admin);
      await page.goto('/admin/members');

      // Invite with two roles.
      await page.getByRole('button', { name: 'Invite a person' }).click();
      const dialog = page.getByRole('dialog', { name: 'Invite a person' });
      await dialog.getByLabel('Email address', { exact: true }).fill('new.person@example-bank.test');
      await dialog.getByLabel('Title', { exact: true }).fill('Compliance analyst');
      await dialog.locator('label', { hasText: /^Reader/ }).getByRole('checkbox').check();
      await dialog.locator('label', { hasText: /^Auditor/ }).getByRole('checkbox').check();
      const invited = page.waitForResponse((r) => r.url().endsWith('/api/v1/tenant/members') && r.request().method() === 'POST');
      await dialog.getByRole('button', { name: 'Send invitation' }).click();
      // Pinned by the id this run created: a revoked invitation stays listed, so an
      // earlier attempt's row for the same address must not match (playbook 8.3 rule 4).
      const { id: invitationId } = (await (await invited).json()) as { id: string };
      const invitation = page.locator(`[data-invitation-id="${invitationId}"]`);
      try {
        await expect(page.getByText('Invitation sent to new.person@example-bank.test.')).toBeVisible();
        await page.getByRole('tab', { name: 'Invitations' }).click();
        await expect(invitation).toBeVisible();
        await expect(invitation).toContainText('Awaiting enrolment');
        await expect(invitation).toContainText('Compliance analyst');
      } finally {
        // Teardown that runs on failure too: the invitation never outlives the attempt.
        await page.goto('/admin/members');
        await page.getByRole('tab', { name: 'Invitations' }).click();
        await invitation.getByRole('button', { name: 'Revoke' }).click();
        await expect(invitation).toContainText('Revoked');
      }

      // Change the roles later, behind step-up. The member is the login seeded for this
      // journey alone: re-issue retires their passkeys and the UI cannot undo it, so it is
      // never spent on a login another journey signs in as (playbook 8.3 rule 4).
      await page.getByRole('tab', { name: 'Members' }).click();
      await page.locator('[data-member-id]', { hasText: LOGINS.reissue }).click();
      await page.locator('label', { hasText: /^Reader/ }).getByRole('checkbox').check();
      await page.getByRole('button', { name: 'Save' }).click();
      const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
      await expect(prompt).toBeVisible();
      await prompt.getByRole('button', { name: 'Use passkey' }).click();
      await expect(page.getByText('Saved.')).toBeVisible();

      // Revoke every session, then re-issue enrolment (the assertion is still fresh).
      await page.getByRole('button', { name: 'Revoke all sessions' }).click();
      await page.getByRole('button', { name: 'Revoke all sessions' }).click();
      await expect(page.getByText('All sessions revoked.')).toBeVisible();
      await page.getByRole('button', { name: 'Re-issue enrolment' }).click();
      await page.getByRole('button', { name: 'Re-issue enrolment' }).click();
      await expect(page.getByText('Enrolment re-issued. A new invitation is on its way.')).toBeVisible();

      // The member list shows the resulting state.
      await page.goto('/admin/members');
      const row = page.locator('[data-member-id]', { hasText: LOGINS.reissue });
      await expect(row).toContainText('Awaiting enrolment');
      await expect(row).toContainText('Reader');
      await expect(row).toContainText('No passkey');
    });
  });

  test("ADM-S3: User administration and business configuration can sit with different people", async ({ page, apiGuard }) => {
    // pending: ADM-S3 (ADM-03) -> built in chunk 1 for the people side; the vocabulary
    // and workflow screens join when chunk 2 builds them.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/admin/members');
    await expect(restrictedScreen(page)).toContainText('Needs members manage');
    await page.goto('/admin/roles');
    await expect(restrictedScreen(page)).toContainText('Needs roles manage');
    await signOut(page);

    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/members');
    await expect(page.getByRole('heading', { level: 1, name: 'Members' })).toBeVisible();
    await page.goto('/admin/roles');
    await expect(page.getByRole('heading', { level: 1, name: 'Roles' })).toBeVisible();
  });
});

// PRD 0.3: departments with heads and team membership (TEN-02, TEN-03) and
// certificates on a legal entity (TEN-02, AC-TEN1). Each stays test.fixme
// until the task in docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('departments, teams and certificates', () => {
  test.fixme("TEN-S8: A department has a head and teams, and team membership is set on the member row", async () => {
    // pending: TEN-S8 (TEN-02, TEN-03)
  });

  test.fixme("TEN-S10: A legal entity records a certificate it holds", async () => {
    // pending: TEN-S10 (TEN-02, AC-TEN1)
  });
});
