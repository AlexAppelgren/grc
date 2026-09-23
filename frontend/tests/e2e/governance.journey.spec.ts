import type { Page } from '@playwright/test';

import { destinations, type Destination } from '@/shared/navigation/registry';

import { expect, test } from './support/api-guard';
import { allowFreshContext, BACKEND_URL, inviteLinkFrom, LOGINS, mailOutbox, mailsTo, restrictedScreen, signInAs, signOut } from './support/passkeys';

// governance: the @e2e scenarios from backend/apps/governance/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// ADM-S4 reads the console from the registry (src/shared/navigation/registry.ts),
// never from a list written here, so a console destination a later chunk adds
// joins the role matrix with no edit to this file.

const CONSOLE_DESTINATIONS: readonly Destination[] = destinations.filter((d) => d.surface === 'console');

/** The grant the Restricted screen names, in plain words (humanisePermission, require-permission.tsx). */
function missingGrant(destination: Destination): string {
  return (destination.anyOfPermissions[0] ?? '').replace(/[._]/g, ' ');
}

/**
 * Signs the login in, then walks every console destination the registry holds:
 * the ones in their rail must open, the rest must refuse by address. Returns
 * the ids of the ones they hold, so the journey can prove the two platform
 * roles divide the console between them.
 */
async function consoleDestinationsOf(page: Page, login: string): Promise<string[]> {
  await signInAs(page, login);
  await page.goto('/console');
  const nav = page.getByRole('navigation', { name: 'Main' });
  // The landing sends each person on to their first destination: settle there
  // before reading the rail.
  await expect(page).not.toHaveURL(/\/console$/);
  // By address, not by label: the registry is the only list, and a spec that
  // read the catalog could not run under Playwright's JSON-free loader.
  const link = (destination: Destination) => nav.locator(`a[href="${destination.href}"]`);

  const mine: Destination[] = [];
  const theirs: Destination[] = [];
  for (const destination of CONSOLE_DESTINATIONS) {
    ((await link(destination).count()) > 0 ? mine : theirs).push(destination);
  }
  expect(mine.length, `${login} holds no console destination`).toBeGreaterThan(0);

  for (const destination of mine) {
    await link(destination).click();
    await expect(page).toHaveURL(new RegExp(`${destination.href}$`));
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
    await expect(restrictedScreen(page)).toHaveCount(0);
  }

  for (const destination of theirs) {
    await page.goto(destination.href);
    // The client gate refuses before any request is made, so the API guard
    // sees no 403 here; the server's own refusal is ADM-S4's integration half.
    await expect(restrictedScreen(page)).toBeVisible();
    await expect(restrictedScreen(page)).toContainText(missingGrant(destination));
    await expect(link(destination)).toHaveCount(0);
  }
  return mine.map((destination) => destination.id);
}

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
    // pending: AUD-S4 (AUD-02, chunk 7)
  });

  test.fixme("AUD-S5: A problem report stays inside the bank that filed it", async () => {
    // pending: AUD-S5 (AUD-03, chunk 4)
  });

  test("ADM-S4: The platform console offers each surface to the platform role that owns it", async ({ page, request, apiGuard }) => {
    // The two platform roles, each walking the whole console. No destination is
    // named here: the registry is the list, and the closing assertion is that it
    // divides cleanly between the two roles with nothing left over.
    allowFreshContext(apiGuard);
    const editor = await consoleDestinationsOf(page, LOGINS.editor);
    await signOut(page);
    const platform = await consoleDestinationsOf(page, LOGINS.platform);

    expect(editor.filter((id) => platform.includes(id))).toEqual([]);
    expect([...editor, ...platform].sort()).toEqual(CONSOLE_DESTINATIONS.map((d) => d.id).sort());

    // A bank's report that a library record looks wrong stays inside that bank
    // (Alex, 2026-09-20, item 3): the console offers no surface for one, and no
    // console route serves one. Asserted directly against the API, so it cannot
    // come back unnoticed. The request fixture is used on purpose — the guard
    // watches the page, and these 404s are the point of the assertion.
    expect(CONSOLE_DESTINATIONS.map((d) => d.id)).not.toContain('console-problem-reports');
    for (const path of ['/api/v1/console/problem-reports', '/api/v1/console/reports']) {
      expect((await request.get(`${BACKEND_URL}${path}`)).status(), `${path} must not exist`).toBe(404);
    }
  });

  test.fixme("ADM-S5: System health names what is wrong", async () => {
    // pending: ADM-S5 (ADM-02, chunk 14)
  });

  test("ADM-S6: A tenant is created from the console with its first administrator invited", async ({ page, request, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    // A name carries the attempt, so a retry and a parallel run never collide and nothing
    // seeded is touched. The short name is derived from it, never typed here.
    const name = `ADM-S6 Bank AB ${Date.now().toString(36)}-${testInfo.retry}`;
    const email = `administrator@${Date.now().toString(36)}-${testInfo.retry}.test`;

    await signInAs(page, LOGINS.platform);
    await page.goto('/console/tenants');
    await expect(page.getByRole('heading', { level: 1, name: 'Tenants' })).toBeVisible();
    await expect(page.locator('[data-tenants-list]').or(page.locator('[data-empty-state]')).first()).toBeVisible();

    const openForm = async () => {
      await page.getByRole('button', { name: 'Create a tenant', exact: true }).click();
      const form = page.getByRole('dialog', { name: 'Create a tenant' });
      await expect(form).toBeVisible();
      return form;
    };

    const form = await openForm();
    await form.getByLabel('Name', { exact: true }).fill(name);
    await form.getByLabel("First administrator's email").fill(email);
    await form.getByLabel('Their title').fill('Head of compliance');
    const created = page.waitForResponse((r) => r.url().endsWith('/api/v1/console/tenants') && r.request().method() === 'POST' && r.ok());
    await form.getByRole('button', { name: 'Create tenant', exact: true }).click();
    const { id: tenantId } = (await (await created).json()) as { id: string };
    await expect(form).toBeHidden();

    // The bank this attempt created, pinned by id, never by a count. It has a short name
    // even though nobody typed one, and no timezone or language field was ever shown.
    const row = page.locator(`[data-tenant-id="${tenantId}"]`);
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute('data-tenant-slug', /.+/);
    await expect(row.getByText('Active', { exact: true })).toBeVisible();

    // One pending invitation went to that address, with the link that opens it.
    await expect.poll(async () => mailsTo(await mailOutbox(request), email).length).toBe(1);
    const [invitation] = mailsTo(await mailOutbox(request), email);
    expect(invitation === undefined ? null : inviteLinkFrom(invitation)).not.toBeNull();

    // A second bank with the same name is created too, not refused: two console
    // create-tenant calls never collide on a name a person never chose a short form for.
    const again = await openForm();
    await again.getByLabel('Name', { exact: true }).fill(name);
    await again.getByLabel("First administrator's email").fill(`second-${email}`);
    const createdAgain = page.waitForResponse((r) => r.url().endsWith('/api/v1/console/tenants') && r.request().method() === 'POST' && r.ok());
    await again.getByRole('button', { name: 'Create tenant', exact: true }).click();
    const { id: secondTenantId, slug: secondSlug } = (await (await createdAgain).json()) as { id: string; slug: string };
    await expect(again).toBeHidden();
    await expect(page.locator(`[data-tenant-id="${secondTenantId}"]`)).toHaveAttribute('data-tenant-slug', secondSlug);
    expect(secondTenantId).not.toBe(tenantId);
  });
});
