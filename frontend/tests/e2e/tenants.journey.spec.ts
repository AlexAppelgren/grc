import { expect, test } from './support/api-guard';
import type { Page } from '@playwright/test';

import { allowFreshContext, BACKEND_URL, LOGINS, mailOutbox, mailsTo, restrictedScreen, signInAs, signOut } from './support/passkeys';

// tenants: the @e2e scenarios from backend/apps/tenants/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

// TEN-S7's tenant-A rows (backend/apps/shared/e2e_seed.py, EXPECTED_TENANT_A_ONLY and
// EXPECTED_FOOTPRINTS): a custom role, a tenant tag, terms A holds and B does not, and the
// compliance officer who files A's pending scope request.
const A_ONLY_ROLE = 'sanctions_lead';
const A_ONLY_TAG_LIST = 'tenant_tag';
const A_ONLY_TAG = 'whistleblowing';
const A_ONLY_TERMS: ReadonlyArray<readonly [string, string]> = [
  ['regime', 'insurance'],
  ['account_type', 'isk'],
  ['legal_entity', 'insurer'],
  ['service_type', 'advice'],
];
const A_REQUESTER = 'Sara Lindqvist';

// TEN-S6's people (backend/apps/shared/e2e_logins.py): tenant A by its organisation name,
// its administrator, whose name the console must never show, and the platform admin.
const BANK = 'Example Bank AB';
const BANK_ADMIN = 'Erik Holm';
const PLATFORM_PERSON = 'Per Ström';

/** The signed-in session's own bearer: its refresh cookie, turned into an access token as the client does. */
async function bearerOf(page: Page): Promise<Record<string, string>> {
  const refreshed = await page.request.post(`${BACKEND_URL}/api/v1/auth/refresh`);
  expect(refreshed.status(), 'the session the UI opened refreshes').toBe(200);
  return { Authorization: `Bearer ${((await refreshed.json()) as { accessToken: string }).accessToken}` };
}

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
    // pending: TEN-S2 (TEN-02, chunk 8)
  });

  test.fixme("TEN-S4: An out-of-office delegate receives approvals and reminders", async () => {
    // pending: TEN-S4 (TEN-04, chunk 8)
  });

  test.fixme("TEN-S5: Removing a member with open work offers bulk reassignment", async () => {
    // pending: TEN-S5 (TEN-05, chunk 8)
  });

  test("TEN-S6: Support access is requested by the platform, approved by the bank and time-boxed", async ({ page, browser, apiGuard }, testInfo) => {
    // TEN-S6 (TEN-06, D-49): the platform admin asks through the console, the bank's admin
    // approves with a passkey, the platform admin enters with a passkey and reads, and the
    // bank revokes. The reads under the grant are the support session's own requests, made
    // with the session the Enter button opened; the window passing and a declined or
    // lapsed request are proven in test_ten_s6, because no journey may move the clock.
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/support-access\/[^/]+\/approve$/, 403, 'approving answers step_up_required first and opens the prompt');
    apiGuard.allow(/\/console\/support-access\/[^/]+\/enter$/, 403, 'entering answers step_up_required first and opens the prompt');
    const purpose = `The watch feed shows two changes twice (run ${Date.now()}).`;
    const ticket = `SUP-${Date.now()}`;

    const bankContext = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
    const bank = await bankContext.newPage();
    apiGuard.watch(bank);
    let grantId: string | null = null;
    try {
      // Given a platform admin without any grant, the bank answers 404.
      await signInAs(page, LOGINS.platform);
      expect((await page.request.get(`${BACKEND_URL}/api/v1/tenant/support-access`, { headers: await bearerOf(page) })).status()).toBe(404);

      // They ask for two hours with a purpose, from the console.
      await page.goto('/console/support-access');
      await expect(page.getByRole('heading', { level: 1, name: 'Support access' })).toBeVisible();
      await page.getByRole('button', { name: 'Ask for access' }).click();
      const form = page.getByRole('dialog', { name: 'Ask for access' });
      await form.getByLabel('Bank').selectOption({ label: BANK });
      await form.getByLabel('Purpose').fill(purpose);
      await form.getByLabel('Ticket').fill(ticket);
      await form.getByLabel('How long, in hours').fill('2');
      const asked = page.waitForResponse((r) => /\/console\/tenants\/[^/]+\/support-access$/.test(r.url()) && r.request().method() === 'POST' && r.status() === 201);
      await form.getByRole('button', { name: 'Ask for access' }).click();
      grantId = ((await (await asked).json()) as { id: string }).id;
      await expect(page.getByText(`Asked. ${BANK}'s administrators have been emailed.`)).toBeVisible();
      const request = page.locator(`[data-grant-id="${grantId}"]`);
      await expect(request).toHaveAttribute('data-grant-state', 'pending');
      await expect(request.getByText('Waiting for approval')).toBeVisible();
      await expect(request.getByRole('button', { name: 'Enter' })).toHaveCount(0);

      // Nothing is granted: the bank still answers 404, and its security.manage holders are told.
      expect((await page.request.get(`${BACKEND_URL}/api/v1/tenant/support-access`, { headers: await bearerOf(page) })).status()).toBe(404);
      await expect
        .poll(async () => mailsTo(await mailOutbox(page.request), LOGINS.admin).some((mail) => mail.body.includes(purpose)), { timeout: 15_000 })
        .toBe(true);

      // A tenant admin approves with a fresh step-up; the panel shows the purpose, the person and the end.
      await signInAs(bank, LOGINS.admin);
      await bank.goto('/admin/support-access');
      const pending = bank.locator(`[data-support-section="pending"] [data-grant-id="${grantId}"]`);
      await expect(pending).toContainText(purpose);
      const approved = bank.waitForResponse((r) => r.url().endsWith(`/tenant/support-access/${grantId}/approve`) && r.ok());
      await pending.getByRole('button', { name: 'Approve' }).click();
      const prompt = bank.getByRole('dialog', { name: 'Confirm with your passkey' });
      await expect(prompt).toBeVisible();
      await prompt.getByRole('button', { name: 'Use passkey' }).click();
      const approval = (await (await approved).json()) as { decidedAt: string; endsAt: string };
      // The window is the two hours asked for, from the moment of approval.
      expect(Date.parse(approval.endsAt) - Date.parse(approval.decidedAt)).toBe(2 * 60 * 60 * 1000);
      const live = bank.locator(`[data-support-section="active"] [data-grant-id="${grantId}"]`);
      await expect(live).toContainText(purpose);
      await expect(live).toContainText(`${PLATFORM_PERSON}, bleqq support`);
      await expect(live.getByText('Until')).toBeVisible();

      // The console shows it live, the approval as a time and nobody at the bank by name.
      await page.reload();
      const grant = page.locator(`[data-grant-id="${grantId}"]`);
      await expect(grant).toHaveAttribute('data-grant-state', 'active');
      await expect(grant).toContainText(ticket);
      await expect(page.locator('main')).not.toContainText(BANK_ADMIN);

      // The platform admin enters with a fresh step-up; the console session becomes the support session.
      const entered = page.waitForResponse((r) => r.url().endsWith(`/console/support-access/${grantId}/enter`) && r.ok());
      await grant.getByRole('button', { name: 'Enter' }).click();
      const enterPrompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
      await expect(enterPrompt).toBeVisible();
      await enterPrompt.getByRole('button', { name: 'Use passkey' }).click();
      await entered;
      await expect(page.locator('[data-support-banner]')).toContainText(`Support access to ${BANK}.`);
      await expect(page.locator('main')).not.toContainText(BANK_ADMIN);

      // Every read under it is in the bank's audit log as support_access.read, with the route
      // and the platform person; a write answers 403 support_read_only.
      const support = await bearerOf(page);
      expect((await page.request.get(`${BACKEND_URL}/api/v1/changes`, { headers: support })).status()).toBe(200);
      const write = await page.request.patch(`${BACKEND_URL}/api/v1/tenant/workflow`, { headers: support, data: { escalateAfterDays: 7 } });
      expect([write.status(), ((await write.json()) as { code: string }).code]).toEqual([403, 'support_read_only']);
      await bank.goto('/admin/audit-log');
      await bank.getByLabel('Record kind').selectOption('support_access');
      const reads = bank.locator(`[data-audit-row][data-subject-id="${grantId}"][data-action="support_access.read"]`);
      await expect(reads.first()).toBeVisible();
      await expect(reads.first()).toContainText(`By ${PLATFORM_PERSON}`);
      await expect(reads.filter({ hasText: '/changes' }).first()).toBeVisible();

      // The tenant admin revokes it: the next request answers 401 support_access_ended.
      await bank.goto('/admin/support-access');
      await bank.locator(`[data-support-section="active"] [data-grant-id="${grantId}"]`).getByRole('button', { name: 'Revoke' }).click();
      await expect(bank.locator(`[data-support-section="history"] [data-grant-id="${grantId}"]`)).toHaveAttribute('data-grant-state', 'revoked');
      const ended = await page.request.get(`${BACKEND_URL}/api/v1/changes`, { headers: support });
      expect([ended.status(), ((await ended.json()) as { code: string }).code]).toEqual([401, 'support_access_ended']);

      // And the ones after that are the platform admin's next console session: 404 again.
      await signInAs(page, LOGINS.platform);
      expect((await page.request.get(`${BACKEND_URL}/api/v1/tenant/support-access`, { headers: await bearerOf(page) })).status()).toBe(404);
      await page.goto('/console/support-access');
      await expect(page.locator(`[data-grant-id="${grantId}"]`)).toHaveAttribute('data-grant-state', 'revoked');
      await expect(page.locator('main')).not.toContainText(BANK_ADMIN);
      grantId = null;
    } finally {
      // Whatever happened above, no request or grant of this run stays open in the bank.
      if (grantId !== null) {
        const headers = await bearerOf(bank);
        for (const verb of ['decline', 'revoke']) await bank.request.post(`${BACKEND_URL}/api/v1/tenant/support-access/${grantId}/${verb}`, { headers });
      }
      await bankContext.close();
    }
  });

  test("TEN-S7 J-8 @smoke: tenant B cannot see tenant A", async ({ page, apiGuard }) => {
    // TEN-S7 (TEN-06, J-8): members, the regulatory scope with its markets and pending
    // request, roles and vocabulary rows. Cases, evidence, comments and participants join
    // the journey with chunks 9 and 10 (tenants/app.md, the note under TEN-S7).
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/members\/[^/]+\/sessions$/, 404, "another tenant's member is not there, never forbidden");

    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/members');
    const memberOfA = page.locator('[data-member-id]', { hasText: LOGINS.reader });
    await expect(memberOfA).toBeVisible();
    const memberUrl = await memberOfA.getAttribute('href');
    expect(memberUrl).toMatch(/^\/admin\/members\/.+/);
    // Tenant A's own role and tag exist, so their absence in B below is not vacuous.
    await page.goto('/admin/roles');
    await expect(page.locator(`[data-role-key="${A_ONLY_ROLE}"]`)).toBeVisible();
    await page.goto(`/admin/vocabularies/${A_ONLY_TAG_LIST}`);
    await expect(page.locator(`[data-value-key="${A_ONLY_TAG}"]`)).toBeVisible();
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

    // B's regulatory scope: Denmark, which A watches, is not watched here (FP-S8 may be
    // operating it in B right now, so only "watching" is ruled out); none of A's terms is
    // held; A's pending request and A's people appear nowhere on the page.
    await page.goto('/admin/footprint');
    await expect(page.locator('[data-footprint-dimensions]')).toBeVisible();
    const denmark = page.locator('[data-markets] [data-market="dk"]');
    await expect(denmark).toBeVisible();
    await expect(denmark.getByRole('button', { pressed: true })).toHaveCount(0);
    for (const [dimension, term] of A_ONLY_TERMS) {
      await expect(page.locator(`[data-dimension="${dimension}"] [data-term="${term}"]`)).toContainText('Not in our scope');
    }
    await expect(page.locator('[data-footprint-history]')).toBeVisible();
    await expect(page.locator('main')).not.toContainText(A_REQUESTER);
    await expect(page.locator('[data-pending-request]').filter({ hasText: 'Remove Advice' })).toHaveCount(0);

    // B's roles and vocabulary rows are B's own.
    await page.goto('/admin/roles');
    await expect(page.locator('[data-role-key="admin"]')).toBeVisible();
    await expect(page.locator(`[data-role-key="${A_ONLY_ROLE}"]`)).toHaveCount(0);
    await page.goto(`/admin/vocabularies/${A_ONLY_TAG_LIST}`);
    await expect(page.locator(`[data-vocabulary-values="${A_ONLY_TAG_LIST}"]`).or(page.locator('[data-empty-state]')).first()).toBeVisible();
    await expect(page.locator(`[data-value-key="${A_ONLY_TAG}"]`)).toHaveCount(0);
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
