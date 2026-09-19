import { expect, test } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs, signOut } from './support/passkeys';

// governance: the @e2e scenarios from backend/apps/governance/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.

test.describe('governance journeys', () => {
  test("AUD-S3: The audit log screen shows who did what, with before and after", async ({ page, apiGuard }) => {
    // pending: AUD-S3 (AUD-01) -> built in chunk 4. The record changed with step-up is an
    // API key: creating one is the shortest action in R1 that asks for a passkey. The
    // reader then reads the log, because audit.read is in every system role and the log is
    // the tenant's, not the actor's.
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/api-keys$/, 403, 'creating a key answers step_up_required first and opens the prompt');
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/api-keys');
    await page.getByRole('button', { name: 'Create a key' }).click();
    const form = page.locator('[data-key-form]');
    await form.getByLabel('Name', { exact: true }).fill('Audit log evidence');
    await form.locator('label', { hasText: /^tenant read/ }).getByRole('checkbox').check();
    // The key this run created, pinned by id: the log is filtered to it, never counted.
    const created = page.waitForResponse((r) => r.url().endsWith('/api/v1/tenant/api-keys') && r.request().method() === 'POST' && r.ok());
    await form.getByRole('button', { name: 'Create key' }).click();
    const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
    await expect(prompt).toBeVisible();
    await prompt.getByRole('button', { name: 'Use passkey' }).click();
    const { id: keyId } = (await (await created).json()) as { id: string };
    const keyRow = page.locator(`[data-key-id="${keyId}"]`);
    await expect(keyRow).toBeVisible();

    try {
      // A reader holds audit.read and nothing else of Admin's sections.
      await signOut(page);
      await signInAs(page, LOGINS.reader);
      await page.goto('/admin');
      await expect(page.locator('[data-admin-section="admin-organisation"]')).toBeVisible();
      await expect(page.locator('[data-admin-section="admin-audit-log"]')).toBeVisible();
      for (const section of ['admin-members', 'admin-roles', 'admin-vocabularies', 'admin-footprint', 'admin-api-keys', 'admin-security-log']) {
        await expect(page.locator(`[data-admin-section="${section}"]`)).toHaveCount(0);
      }
      await page.locator('[data-admin-section="admin-audit-log"]').click();
      await expect(page).toHaveURL(/\/admin\/audit-log$/);
      await expect(page.getByRole('heading', { level: 1, name: 'Audit log' })).toBeVisible();

      // Filter to the kind, then find the event this run wrote.
      await page.getByLabel('Record kind').selectOption('api_key');
      const event = page.locator(`[data-audit-row][data-subject-id="${keyId}"][data-action="api_key.created"]`);
      await expect(event).toBeVisible();
      await expect(event).toContainText('Audit log evidence');
      await expect(event).toContainText('By Erik Holm');
      await expect(event).toContainText('api key created');
      await expect(event.locator('time')).toHaveAttribute('datetime', /^\d{4}-\d{2}-\d{2}T/);
      // Before and after are the snapshot's own fields, as data.
      await expect(event.locator('[data-audit-diff] [data-field="scopes"] [data-after]')).toContainText('tenant:read');
      await expect(event.locator('[data-audit-diff] [data-field="scopes"] [data-before]')).toHaveText('Not set');
      // The passkey marker: this action was completed with a step-up.
      await expect(event.getByText('Confirmed with a passkey')).toBeVisible();

      // Filtering to that record leaves the log showing it and nothing else.
      await event.locator('[data-only-record]').click();
      await expect(page.getByRole('button', { name: 'Record: Audit log evidence ✕' })).toBeVisible();
      await expect(event).toBeVisible();
      await expect(page.locator(`[data-audit-row]:not([data-subject-id="${keyId}"])`)).toHaveCount(0);
    } finally {
      // Teardown that runs on failure too: a live key never outlives the attempt.
      await signOut(page);
      await signInAs(page, LOGINS.admin);
      await page.goto('/admin/api-keys');
      await expect(keyRow).toBeVisible();
      if ((await keyRow.getByRole('button', { name: 'Revoke' }).count()) > 0) {
        await keyRow.getByRole('button', { name: 'Revoke' }).click();
        await keyRow.getByRole('button', { name: 'Revoke' }).click();
        await expect(keyRow).toContainText('Revoked');
      }
    }
  });

  test.fixme("AUD-S4: Every model output is logged with its review state", async () => {
    // pending: AUD-S4 (AUD-02)
  });

  test.fixme("AUD-S5: A problem report is resolved by a proposal", async () => {
    // pending: AUD-S5 (AUD-03)
  });

  test.fixme("ADM-S4: The platform console offers each surface to the platform role that owns it", async () => {
    // pending: ADM-S4 (ADM-02)
  });

  test.fixme("ADM-S5: System health names what is wrong", async () => {
    // pending: ADM-S5 (ADM-02)
  });

  test.fixme("ADM-S6: Tenants, plans and support access are managed from the console", async () => {
    // pending: ADM-S6 (ADM-02)
  });
});
