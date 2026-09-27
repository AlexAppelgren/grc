import { execFileSync } from 'node:child_process';
import path from 'node:path';

import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, restrictedScreen, signInAs, signOut } from './support/passkeys';

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

  // c8-ui-organisation (TEN-02). An entity and a product carry library terms from the
  // dimensions obligations are scoped with, as brand pills; a member without vocab.manage
  // reads them and gets no Edit or Add. The register line (a status per entity) is the
  // register's to prove (c8-reg-entity-status). Units and products are never deleted, so the
  // journey names its rows by run and deactivates and retires them on the way out.
  test("TEN-S2: Legal entities and products are scoped like obligations", async ({ page, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    const run = `${Date.now()}-${testInfo.retry}`;
    const entityName = `Bank AB ${run}`;
    const productName = `Custody ${run}`;
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/organisation');
    const entities = page.locator('[data-org-section="entities"]');
    await expect(entities.locator('[data-org-unit="Example Bank AB"]')).toBeVisible();

    try {
      await entities.getByRole('button', { name: 'Add a legal entity' }).click();
      let dialog = page.getByRole('dialog');
      await dialog.getByLabel('Name').fill(entityName);
      await dialog.getByLabel('Sits under').selectOption({ label: 'Example Group' });
      await dialog.getByLabel('Country').fill('SE');
      await dialog.getByLabel('Legal-entity term').selectOption('bank');
      await dialog.getByRole('button', { name: 'Save' }).click();
      await expect(dialog).toBeHidden();
      const entity = entities.locator(`[data-org-unit="${entityName}"]`);
      await expect(entity.locator('[data-pill="brand"]')).toHaveCount(1);

      // The licence: its type and its services are terms of the same dimensions.
      const licences = page.locator(`[data-licences-of="${entityName}"]`);
      await expect(licences.getByText('No licences or certificates recorded.')).toBeVisible();
      await licences.getByRole('button', { name: `Add a licence or certificate to ${entityName}` }).click();
      dialog = page.getByRole('dialog');
      await dialog.getByLabel('Type').selectOption('bank');
      await dialog.getByLabel('Reference').fill(`FI ${run}`);
      await dialog.getByLabel('Services').selectOption('custody');
      await dialog.getByRole('button', { name: 'Save' }).click();
      await expect(dialog).toBeHidden();
      const licence = licences.locator('[data-licence="bank"]');
      await expect(licence).toContainText(`FI ${run}`);
      await expect(licence.locator('[data-pill="brand"]')).toHaveCount(1);

      // The product: its entity and its scope terms, all brand pills.
      const products = page.locator('[data-org-section="products"]');
      await products.getByRole('button', { name: 'Add a product' }).click();
      dialog = page.getByRole('dialog');
      await dialog.getByLabel('Name').fill(productName);
      await dialog.getByLabel('Legal entity').selectOption({ label: entityName });
      await dialog.getByLabel('Scope').selectOption('custody');
      await dialog.getByRole('button', { name: 'Save' }).click();
      await expect(dialog).toBeHidden();
      const product = products.locator(`[data-product="${productName}"]`);
      await expect(product.locator('[data-pill="brand"]').first()).toHaveText(entityName);
      await expect(product.locator('[data-pill="brand"]')).toHaveCount(2);
      await expect(product.locator('[data-pill]:not([data-pill="brand"])')).toHaveCount(0);
      await signOut(page);

      // A reader sees the same rows and nothing to change them with.
      await signInAs(page, LOGINS.reader);
      await page.goto('/admin/organisation');
      await expect(page.locator(`[data-product="${productName}"]`)).toBeVisible();
      await expect(page.locator(`[data-org-unit="${entityName}"]`)).toBeVisible();
      await expect(page.getByRole('button', { name: 'Add a legal entity' })).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Add a product' })).toHaveCount(0);
      await expect(page.getByRole('button', { name: `Edit ${productName}` })).toHaveCount(0);
      await signOut(page);
    } finally {
      // Retire the product and deactivate the entity: neither is ever deleted.
      await signInAs(page, LOGINS.admin);
      await page.goto('/admin/organisation');
      const product = page.locator(`[data-product="${productName}"]`);
      if ((await product.count()) > 0) {
        await page.getByRole('button', { name: `Edit ${productName}` }).click();
        await page.getByRole('dialog').getByLabel('Status').selectOption('retired');
        await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
        await expect(page.getByRole('dialog')).toBeHidden();
      }
      const entity = page.locator(`[data-org-unit="${entityName}"]`);
      if ((await entity.count()) > 0) {
        await page.getByRole('button', { name: `Edit ${entityName}` }).click();
        await page.getByRole('dialog').getByLabel('State').selectOption('inactive');
        await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
        await expect(page.getByRole('dialog')).toBeHidden();
        await expect(entity).toContainText('Inactive');
      }
    }
  });

  test.fixme("TEN-S4: An out-of-office delegate receives approvals and reminders", async () => {
    // pending: TEN-S4 (TEN-04, chunk 8)
  });

  // c8-ui-departments-teams-removal (TEN-05). The seeded leaver owns three obligations and a
  // gap (backend/apps/shared/e2e_seed.py, LEAVER); the case kinds join with chunk 9. One
  // transaction with one audit event per item is proven on the server
  // (apps/tenants/tests_reassignment.py); this journey proves the screen, and puts the
  // leaver back afterwards, on failure too.
  test("TEN-S5: Removing a member with open work offers bulk reassignment", async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/members\/[^/]+\/remove$/, 403, 'the first removal answers step_up_required and opens the passkey prompt');
    apiGuard.allow(/\/tenant\/members\/[^/]+\/remove$/, 422, 'confirming with no new owner for a kind is refused with reassignment_required');
    try {
      await signInAs(page, LOGINS.admin);
      await page.goto('/admin/members');
      await page.locator('[data-member-id]', { hasText: LOGINS.leaver }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'Gustav Sjöberg' })).toBeVisible();
      await page.getByRole('button', { name: 'Deactivate' }).click();
      const dialog = page.getByRole('dialog', { name: 'Deactivate Gustav Sjöberg' });
      await expect(dialog.locator('[data-removal-kind="register_entry"]')).toContainText('3 obligations');
      await expect(dialog.locator('[data-removal-kind="gap"]')).toContainText('1 gap');

      // Confirming with no new owner changes nothing, and the refusal names what is still owned.
      await dialog.getByRole('button', { name: 'Deactivate' }).click();
      const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
      const refused = dialog.getByRole('alert');
      await expect(prompt.or(refused).first()).toBeVisible();
      if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
      await expect(refused).toContainText('Gustav Sjöberg still owns open work');
      await expect(refused).toContainText('3 obligations');
      await dialog.getByRole('button', { name: 'Cancel' }).click();
      await expect(dialog).toBeHidden();
      await expect(page.locator('[data-pill]', { hasText: 'Deactivated' })).toHaveCount(0);

      // A new owner per kind: the obligations to a person, everything else to a team.
      await page.getByRole('button', { name: 'Deactivate' }).click();
      await expect(dialog.locator('[data-removal-kind="register_entry"]')).toBeVisible();
      for (const kind of await dialog.locator('[data-removal-kind]').evaluateAll((rows) => rows.map((row) => row.getAttribute('data-removal-kind')))) {
        await dialog.locator(`[data-removal-kind="${kind}"] select`).selectOption({ label: kind === 'register_entry' ? A_REQUESTER : 'Retail compliance' });
      }
      await dialog.getByRole('button', { name: 'Deactivate' }).click();
      await expect(prompt.or(page.getByRole('heading', { level: 1, name: 'Members' })).first()).toBeVisible();
      if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'Members' })).toBeVisible();
      await expect(page.locator('[data-member-id]', { hasText: LOGINS.leaver })).toContainText('Deactivated');
    } finally {
      restoreLeaver();
    }
  });

  test.fixme("TEN-S6: Support access is requested by the platform, approved by the bank and time-boxed", async () => {
    // pending: TEN-S6 (TEN-06, chunk 8)
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
      await page.getByRole('button', { name: 'Save', exact: true }).click();
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
  // c8-ui-departments-teams-removal (TEN-02, TEN-03). Karin heads the new department; a
  // team is added to the bank's team list and the reserved member is put in it on the member
  // row, then taken out again, on failure too. GET /me's departments, one audit event per
  // call, the refusal of another bank's member and the database's composite keys are proven
  // on the server (apps/tenants/tests_scenarios.py). No route yet puts a team in a
  // department, so the seeded Retail compliance shows it.
  test("TEN-S8: A department has a head and teams, and team membership is set on the member row", async ({ page, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    const run = `${Date.now()}-${testInfo.retry}`;
    const department = `Private Banking ${run}`;
    const team = `Private banking compliance ${run}`;
    const memberTeams = page.locator('fieldset', { hasText: 'Teams' });
    const saveTeams = async (checked: boolean) => {
      await page.goto('/admin/members');
      await page.locator('[data-member-id]', { hasText: LOGINS.teamMember }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'Linnea Forsberg' })).toBeVisible();
      await memberTeams.getByRole('checkbox', { name: team, exact: true }).setChecked(checked);
      await page.getByRole('button', { name: 'Save teams' }).click();
      await expect(page.getByText('Teams saved.', { exact: true })).toBeVisible();
    };

    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/organisation');
    const departments = page.locator('[data-org-section="departments"]');
    await expect(departments.locator('[data-department="Retail Banking"]')).toContainText('Head: Karin Ek');
    await departments.getByRole('button', { name: 'Add a department' }).click();
    const addDepartment = page.getByRole('dialog', { name: 'Add a department' });
    await addDepartment.getByLabel('Kind').selectOption('business_area');
    await addDepartment.getByLabel('Name', { exact: true }).fill(department);
    await addDepartment.getByLabel('Sits under').selectOption({ label: 'Example Bank AB' });
    await addDepartment.getByLabel('Head', { exact: true }).selectOption({ label: 'Karin Ek' });
    await addDepartment.getByRole('button', { name: 'Save' }).click();
    await expect(addDepartment).toBeHidden();
    const added = departments.locator(`[data-department="${department}"]`);
    await expect(added).toContainText('Business area');
    await expect(added).toContainText('In Example Bank AB');
    await expect(added).toContainText('Head: Karin Ek');

    const teams = page.locator('[data-org-section="teams"]');
    await expect(teams.locator('[data-team="retail_compliance"]')).toContainText('Retail Banking');
    await teams.getByRole('button', { name: 'Add a team' }).click();
    const addTeam = page.getByRole('dialog', { name: 'Add a team' });
    await addTeam.getByLabel('Name', { exact: true }).fill(team);
    await addTeam.getByRole('button', { name: 'Save' }).click();
    await expect(addTeam).toBeHidden();
    await expect(teams.locator('[data-team]', { hasText: team })).toContainText('0 members');

    try {
      await saveTeams(true);
      await page.goto('/admin/organisation');
      await expect(page.locator('[data-org-section="teams"] [data-team]', { hasText: team })).toContainText('1 member');
    } finally {
      await saveTeams(false);
    }
    await signOut(page);

    // Team membership is members.manage: without it, the member screens are not there.
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/admin/members');
    await expect(restrictedScreen(page)).toContainText('Needs members manage');
  });

  // c8-ui-organisation (TEN-02, AC-TEN1). The certificate is a licence row with a
  // certificate's fields and an owner; its dates are anchored to the tenant-local day. The
  // audit rows before and after and "no obligation, scope row or applicability changes" are
  // proven on the server (apps/tenants/tests_organisation.py); this journey proves the screen.
  test("TEN-S10: A legal entity records a certificate it holds", async ({ page, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    const number = `EC-27001-${Date.now()}-${testInfo.retry}`;
    const day = (days: number) => {
      const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
      const date = new Date(`${today}T00:00:00Z`);
      date.setUTCDate(date.getUTCDate() + days);
      return date.toISOString().slice(0, 10);
    };
    const shown = (iso: string) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${iso}T00:00:00Z`));
    const [issued, validUntil, nextAudit] = [day(-200), day(900), day(165)];

    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/organisation');
    const licences = page.locator('[data-licences-of="Example Bank AB"]');
    await expect(licences.locator('[data-licence]').first()).toBeVisible();

    await licences.getByRole('button', { name: 'Add a licence or certificate to Example Bank AB' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add a licence or certificate to Example Bank AB' });
    await dialog.getByLabel('Kind').selectOption('certificate');
    await dialog.getByLabel('Type').selectOption('iso_iec_27001');
    await dialog.getByLabel('Issuer').fill('Example Certification AB');
    await dialog.getByLabel('Certificate number').fill(number);
    await dialog.getByLabel('Scope statement').fill('The information security management system for retail banking IT operations');
    await dialog.getByLabel('Issued').fill(issued);
    await dialog.getByLabel('Valid until').fill(validUntil);
    await dialog.getByLabel('Next audit').fill(nextAudit);
    await dialog.getByLabel('Owner').selectOption({ label: 'Sara Lindqvist' });
    await dialog.getByRole('button', { name: 'Save' }).click();
    await expect(dialog).toBeHidden();

    // Listed under the entity with its validity and next audit, and no term pill of its own.
    const certificate = licences.locator('[data-licence]').filter({ hasText: number });
    await expect(certificate).toContainText('Certificate');
    await expect(certificate).toContainText('Example Certification AB');
    await expect(certificate.getByRole('definition').filter({ hasText: shown(validUntil) })).toHaveCount(1);
    await expect(certificate.getByRole('definition').filter({ hasText: shown(nextAudit) })).toHaveCount(1);
    await expect(certificate).toContainText('Sara Lindqvist');
    await expect(certificate.locator('[data-pill]')).toHaveCount(0);

    // Withdrawn: it reads as withdrawn and stays in the history, behind Show withdrawn.
    const withdrawnOn = day(0);
    await certificate.getByRole('button', { name: /^Edit / }).click();
    const edit = page.getByRole('dialog');
    await edit.getByLabel('Withdrawn').fill(withdrawnOn);
    await edit.getByRole('button', { name: 'Save' }).click();
    await expect(edit).toBeHidden();
    await expect(certificate).toHaveCount(0);
    await licences.getByRole('button', { name: /^Show \d+ withdrawn$/ }).click();
    await expect(certificate).toHaveAttribute('data-withdrawn', '');
    await expect(certificate).toContainText(`Withdrawn ${shown(withdrawnOn)}`);
    await expect(certificate.getByRole('button')).toHaveCount(0);
  });
});

/** TEN-S5's teardown: the E2E-only `manage.py e2e_restore_leaver` puts the removed member back as seeded. */
function restoreLeaver(): void {
  // Forward slashes: bash opens the script by this path, and a Windows checkout hands path.join backslashes.
  const script = path.join(test.info().project.testDir, 'support', 'start-backend.sh').split(path.sep).join('/');
  execFileSync('bash', [script, 'manage', 'e2e_restore_leaver'], { encoding: 'utf8' });
}
