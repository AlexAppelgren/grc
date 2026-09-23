import { execFileSync } from 'node:child_process';
import path from 'node:path';

import type { Browser, Page } from '@playwright/test';

import { expect, test, type ApiGuard } from './support/api-guard';
import { allowFreshContext, E2E_FIXED_CODE, installAuthenticator, inviteLink, inviteLinkFrom, mailOutbox, mailsTo } from './support/passkeys';

// The cold start (ADM-S8, docs/runbooks/FIRST_RUN_SETUP.md steps 4 to 11).
//
// Every other journey runs on seed_e2e, which hands the suite two banks, a passkey per
// role and a full library. That hides what a first deploy actually hits: a reference seed
// that runs nowhere, a screen that assumes data, a command that refuses. This journey runs
// on a database a deploy has only migrated and seeded reference data into — no fixture, no
// extra row — and walks it to a signed-in bank administrator through the browser alone.
// `npm run test:e2e -- --grep @coldstart` boots that stack on its own ports and its own
// database; every other run filters this file out (playwright.config.ts).
//
// What it proves is not that a button is where it was: it is that no `/api/` call answers
// 400 or above undeclared and no page throws on the way from nothing to a working bank,
// and that the first screens render honest empty states rather than an error.

/** A suffix no other run, attempt or parallel worker shares: every address and the bank's own name carries it. */
const RUN = Date.now().toString(36);
const PLATFORM_ADMIN = `platform-admin-${RUN}@bleqq.test`;
const BANK_ADMIN = `administrator@coldstart-${RUN}.test`;
const BANK_APPROVER = `approver@coldstart-${RUN}.test`;
const BANK_NAME = `Cold Start Bank ${RUN}`;

/**
 * FIRST_RUN_SETUP step 4: `manage.py bootstrap_platform` on the api service, as a person
 * runs it — the same database, the same app role, the same environment the server has
 * (tests/e2e/support/start-backend.sh `manage`). It prints the one-time invitation link;
 * the enrolment path starts there, never at a token this test minted.
 */
function bootstrapPlatformAdmin(email: string): string {
  // Forward slashes: bash opens the script by this path, and a Windows checkout hands
  // path.join backslashes.
  const script = path.join(test.info().project.testDir, 'support', 'start-backend.sh').split(path.sep).join('/');
  let printed: string;
  try {
    printed = execFileSync('bash', [script, 'manage', 'bootstrap_platform', '--admin-email', email], { encoding: 'utf8' });
  } catch (failure) {
    // A command that refuses on a fresh database is exactly what this journey exists to
    // catch, so its own words are the failure, not "command failed with exit code 1".
    const { stdout, stderr } = failure as { stdout?: string; stderr?: string };
    throw new Error(`bootstrap_platform failed on an empty database:\n${stdout ?? ''}\n${stderr ?? ''}`);
  }
  const token = /\/invite#([A-Za-z0-9_\-.~]+)/.exec(printed)?.[1];
  expect(token, `bootstrap_platform printed an invitation link:\n${printed}`).toBeDefined();
  return inviteLink(token ?? '');
}

/** The invitation link a person was emailed, once the worker has delivered it. */
async function invitationEmailedTo(page: Page, address: string): Promise<string> {
  await expect
    .poll(async () => mailsTo(await mailOutbox(page.request), address).length, { timeout: 15_000 })
    .toBeGreaterThan(0);
  const message = mailsTo(await mailOutbox(page.request), address).at(-1);
  const link = message === undefined ? null : inviteLinkFrom(message);
  expect(link, `the invitation emailed to ${address} carries a link`).not.toBeNull();
  return link ?? '';
}

/** Code, then passkey, then past the offer of a second one: the whole of FIRST_RUN_SETUP step 5. */
async function enrol(page: Page, invitePath: string): Promise<void> {
  await installAuthenticator(page.context());
  await page.goto(invitePath);
  await expect(page.getByRole('heading', { level: 1, name: 'Enter your code' })).toBeVisible();
  await page.getByLabel('Code', { exact: true }).fill(E2E_FIXED_CODE);
  await expect(page.getByRole('heading', { level: 1, name: 'Create your passkey' })).toBeVisible();
  await page.getByRole('button', { name: 'Create passkey' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Add a second passkey?' })).toBeVisible();
  await page.getByRole('button', { name: 'Skip for now' }).click();
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible({ timeout: 15_000 });
}

/** Another person, in their own browser and their own authenticator, held to the same API guard. */
async function otherPerson(browser: Browser, apiGuard: ApiGuard): Promise<Page> {
  const context = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const page = await context.newPage();
  apiGuard.watch(page);
  return page;
}

test.describe('cold start', () => {
  // A first deploy happens once. A retry would run against the platform admin, the bank and
  // the invitations the first attempt already made, and fail for that rather than for the
  // real cause; as with Anna's chain in the identity journeys, the first failure is the one.
  test.describe.configure({ retries: 0 });

  test('ADM-S8 @coldstart: an empty database becomes a working bank, and the first screens are honestly empty', async ({ page, browser, apiGuard }) => {
    // Three enrolments, a tenant, an invitation and a four-eyes footprint change, all
    // through the browser: far more than one screen's worth of waiting.
    test.setTimeout(240_000);
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/footprint\/requests\/[^/]+\/approve$/, 403, 'the first approval answers step_up_required and opens the passkey prompt');

    // ——— steps 4 and 5: the first platform administrator ————————————————————
    await enrol(page, bootstrapPlatformAdmin(PLATFORM_ADMIN));

    // ——— steps 6 and 7: the first bank, with its administrator invited ——————
    await page.goto('/console/tenants');
    await expect(page.getByRole('heading', { level: 1, name: 'Tenants' })).toBeVisible();
    // Nothing has ever been created here, so the list is the empty state and not an error.
    await expect(page.locator('[data-empty-state]')).toBeVisible();

    await page.getByRole('button', { name: 'Create a tenant', exact: true }).click();
    const form = page.getByRole('dialog', { name: 'Create a tenant' });
    await form.getByLabel('Name', { exact: true }).fill(BANK_NAME);
    await form.getByLabel("First administrator's email").fill(BANK_ADMIN);
    await form.getByLabel('Their title').fill('Head of compliance');
    const created = page.waitForResponse((r) => r.url().endsWith('/api/v1/console/tenants') && r.request().method() === 'POST' && r.ok());
    await form.getByRole('button', { name: 'Create tenant', exact: true }).click();
    const { id: tenantId } = (await (await created).json()) as { id: string };
    // Pinned by id, never by a short name: nobody types one any more, it is derived.
    await expect(page.locator(`[data-tenant-id="${tenantId}"]`)).toHaveAttribute('data-tenant-slug', /.+/);

    // ——— step 8: the bank's administrator enrols from their own emailed link ————
    const admin = await otherPerson(browser, apiGuard);
    await enrol(admin, await invitationEmailedTo(page, BANK_ADMIN));
    await expect(admin.locator('[data-who-panel]')).toContainText(BANK_NAME);

    // ——— step 9: the bank's profile ————————————————————————————————————————
    await admin.goto('/admin/organisation');
    await expect(admin.getByRole('heading', { level: 1, name: 'Organisation' })).toBeVisible();
    await admin.getByLabel('Timezone').fill('Europe/Helsinki');
    await admin.getByRole('button', { name: 'Save' }).click();
    await expect(admin.getByText('Saved.')).toBeVisible();

    // ——— step 10: a second person, because four eyes needs two ————————————————
    await admin.goto('/admin/members');
    await admin.getByRole('button', { name: 'Invite a person' }).click();
    const invite = admin.getByRole('dialog', { name: 'Invite a person' });
    await invite.getByLabel('Email address', { exact: true }).fill(BANK_APPROVER);
    await invite.getByLabel('Title', { exact: true }).fill('Head of risk');
    await invite.locator('label', { hasText: /^Approver/ }).getByRole('checkbox').check();
    await invite.getByRole('button', { name: 'Send invitation' }).click();
    await expect(admin.getByText(`Invitation sent to ${BANK_APPROVER}.`)).toBeVisible();

    const approver = await otherPerson(browser, apiGuard);
    await enrol(approver, await invitationEmailedTo(admin, BANK_APPROVER));

    // ——— step 11: the footprint, requested by one person and approved by the other ———
    await admin.goto('/admin/footprint');
    await expect(admin.getByRole('heading', { level: 1, name: 'Regulatory scope' })).toBeVisible();
    // A bank that has just been created holds no terms, so every group reads as unrestricted
    // and the first scope is an addition. Found by dimension key, never by a label: terms are rows.
    const regime = admin.locator('[data-dimension="regime"]');
    await expect(regime.getByText('Not restricted: every option applies.')).toBeVisible();
    await admin.getByRole('button', { name: 'Propose a change' }).click();
    await regime.getByRole('checkbox').first().check();
    const draft = admin.locator('[data-draft-preview]');
    await expect(draft).toBeVisible();
    await expect(draft.getByText('Loading…')).toHaveCount(0);
    await draft.getByRole('button', { name: 'Request approval' }).click();
    await expect(admin.getByText('Sent for approval.')).toBeVisible();
    // Four eyes on screen: the requester is offered Withdraw, never Approve.
    await expect(admin.locator('[data-pending-request]').getByRole('button', { name: 'Approve' })).toHaveCount(0);

    await approver.goto('/admin/footprint');
    await approver.locator('[data-pending-request]').getByRole('button', { name: 'Approve' }).click();
    await approver.getByRole('dialog', { name: /^Approve ".+"\?$/ }).getByRole('button', { name: 'Approve with passkey' }).click();
    const prompt = approver.getByRole('dialog', { name: 'Confirm with your passkey' });
    const approved = approver.getByText('Approved. The regulatory scope has changed.');
    await expect(prompt.or(approved).first()).toBeVisible();
    if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
    await expect(approved).toBeVisible();

    await admin.reload();
    await expect(regime.locator('[data-term]').first()).toHaveText(/ In our scope$/);

    // ——— the first screens, on a library that has never held a row ————————————
    // Each answers with its own empty state, and the api guard fails this journey if any
    // of the reads behind them answered 400 or above, or if a page threw.
    await admin.goto('/inventory');
    await expect(admin.locator('[data-empty-state]')).toBeVisible();
    await admin.goto('/');
    await expect(admin.locator('[data-empty-state]')).toBeVisible();

    await approver.context().close();
    await admin.context().close();
  });

  test.fixme('ADM-S8 @coldstart: the watch feed is empty rather than broken on a new bank', async () => {
    // /watch is in the navigation registry and has no route yet: chunk 5 (Watch and the
    // agent API) builds the feed and its empty state. Until then a cold start cannot prove
    // it, and the inventory and the timeline above carry the empty-state half of ADM-S8.
  });
});
