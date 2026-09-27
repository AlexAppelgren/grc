import type { APIRequestContext, Locator, Page } from '@playwright/test';

import { allowAgentAccessStepUps, confirmWithPasskey, issueEntryKey, registerEntry, revokeEntry } from './support/agent-access-screens';
import { mintAgentKey, revokeAgentKey } from './support/agent-key';
import { expect, test } from './support/api-guard';
import {
  allowFreshContext,
  ANNA_INVITE_TOKEN,
  BACKEND_URL,
  E2E_FIXED_CODE,
  installAuthenticator,
  inviteLink,
  inviteLinkFrom,
  LOGINS,
  mailOutbox,
  mailsTo,
  restrictedScreen,
  signInAs,
  signOut,
} from './support/passkeys';

// identity: the @e2e scenarios from backend/apps/identity/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// Anna (anna@example-bank.test) is the one seeded user awaiting enrolment, so
// the journeys that spend her invitation run in order in one worker: ID-S4
// leaves her un-enrolled, J-1 enrols her, ID-S6 proves the code now sends
// nothing, ID-S12 re-issues her enrolment behind step-up, ID-S5 enrols her
// again from the re-issued link. The seed is fresh per run, which is what
// makes the chain restartable per run. It is not restartable within a run: a
// retry re-runs the whole serial group against a spent invitation, so ID-S4
// failed its retry with a 410 whenever a later link failed (playbook 8.3 rule
// 4). The group therefore never retries; the first failure is the real one.

/** The tenant-local day (Europe/Stockholm) plus `days`, as YYYY-MM-DD. */
function stockholmDayPlus(days: number): string {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const date = new Date(`${today}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

// The invitation path: the link's token names the account, so the code step
// asks for the code alone (no address) and submits once all six digits are in.
async function enterInvitationCode(page: Page): Promise<void> {
  await expect(page.getByRole('heading', { level: 1, name: 'Enter your code' })).toBeVisible();
  await expect(page.getByLabel('Email address', { exact: true })).toHaveCount(0);
  await expect(page).toHaveURL(/\/enrol\?via=invitation$/);
  const verify = page.waitForRequest((r) => r.url().endsWith('/auth/invitations/verify') && r.method() === 'POST');
  await page.getByLabel('Code', { exact: true }).fill(E2E_FIXED_CODE);
  // The token and the code travel in the body; no address does.
  expect(Object.keys((await verify).postDataJSON() as object).sort()).toEqual(['code', 'token']);
  await expect(page.getByRole('heading', { level: 1, name: 'Create your passkey' })).toBeVisible();
}

// The person names nothing: the server names the passkey from the device
// (ID-04). The name is read from the real verify response, never assumed,
// so the journey proves the screen shows what the server derived.
async function createPasskey(page: Page, scope: Page | Locator = page): Promise<string> {
  const verified = page.waitForResponse((r) => r.url().endsWith('/auth/passkeys/register/verify') && r.request().method() === 'POST');
  await scope.getByRole('button', { name: 'Create passkey' }).click();
  const body = (await (await verified).json()) as { passkey: { nickname: string } };
  expect(body.passkey.nickname.trim(), 'the derived name is never blank').not.toBe('');
  return body.passkey.nickname;
}

// The sign-in page's "First time here?" path, which still asks for the address.
async function requestCodeNeutrally(page: Page, email: string): Promise<void> {
  await page.goto('/sign-in');
  await page.getByRole('button', { name: 'First time here? Enter the code from your invitation' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Enter your code' })).toBeVisible();
  await page.getByLabel('Email address').fill(email);
  await page.getByRole('button', { name: 'Send a new code' }).click();
  await expect(page.getByText('If that address is awaiting enrolment, a new code is on its way.')).toBeVisible();
}

test.describe('identity journeys', () => {
  test.describe('Anna enrols', () => {
    test.describe.configure({ mode: 'serial', retries: 0 });

    let reissuedInvitePath: string | null = null;

    test("ID-S4: The enrolment session reaches only passkey registration and GET /me", async ({ page, apiGuard }) => {
      // pending: ID-S4 (ID-02, AC-ID2) -> built in chunk 1
      allowFreshContext(apiGuard);
      // The token rides in the link's fragment and the request bodies, never a
      // request line any server logs (security review F29).
      const requestLines: string[] = [];
      page.on('request', (request) => requestLines.push(request.url()));
      await page.goto(inviteLink(ANNA_INVITE_TOKEN));
      await enterInvitationCode(page);
      expect(requestLines.some((url) => url.endsWith('/api/v1/auth/invitations/open'))).toBe(true);
      expect(requestLines.filter((url) => url.includes(ANNA_INVITE_TOKEN))).toEqual([]);
      // The enrolment session may reach only registration and GET /me: every
      // tenant screen sends her back to the passkey step.
      await page.goto('/');
      await expect(page).toHaveURL(/\/enrol$/);
      await expect(page.getByRole('heading', { level: 1, name: 'Create your passkey' })).toBeVisible();
      await page.goto('/me/passkeys');
      await expect(page).toHaveURL(/\/enrol$/);
      await expect(page.getByRole('heading', { level: 1, name: 'Create your passkey' })).toBeVisible();
    });

    test("ID-S25 J-1 @smoke: invitation to passkey sign-in", async ({ page, apiGuard, request }) => {
      // pending: ID-S25 (ID-01, ID-02, ID-03, AC-ID1, J-1) -> built in chunk 1
      allowFreshContext(apiGuard);
      await installAuthenticator(page.context());
      await page.goto(inviteLink(ANNA_INVITE_TOKEN));
      await enterInvitationCode(page);
      const firstName = await createPasskey(page);
      // ID-S5 in passing: the first passkey activates the account and asks for a second one.
      await expect(page.getByRole('heading', { level: 1, name: 'Add a second passkey?' })).toBeVisible();
      await expect(page.getByText(`${firstName} added`, { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Skip for now' }).click();
      await expect(page.locator('[data-who-panel]')).toBeVisible();
      await expect(page.locator('[data-who-panel]')).toContainText('Example Bank AB');
      // She lands on Today; it has read what it shows before she signs out.
      await expect(page.getByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeVisible();

      await signOut(page);

      // The passkey just created is the only way back in, from the public page's Sign in.
      await page.getByRole('banner').getByRole('link', { name: 'Sign in' }).click();
      await page.getByRole('button', { name: 'Sign in with a passkey' }).click();
      await expect(page.locator('[data-who-panel]')).toBeVisible();
      await expect(page.getByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeVisible();

      // A code request for her address now looks normal and sends nothing (AC-ID1).
      await signOut(page);
      const before = mailsTo(await mailOutbox(request), LOGINS.anna).length;
      await requestCodeNeutrally(page, LOGINS.anna);
      const after = mailsTo(await mailOutbox(request), LOGINS.anna).length;
      expect(after).toBe(before);
    });

    test("ID-S6: A code request for an enrolled account looks normal and sends nothing", async ({ page, apiGuard, request }) => {
      // pending: ID-S6 (ID-03, AC-ID1) -> built in chunk 1
      allowFreshContext(apiGuard);
      const before = mailsTo(await mailOutbox(request), LOGINS.anna).length;
      await requestCodeNeutrally(page, LOGINS.anna);
      // The same sentence an unknown address gets.
      await requestCodeNeutrally(page, 'nobody@example-bank.test');
      const outbox = await mailOutbox(request);
      expect(mailsTo(outbox, LOGINS.anna)).toHaveLength(before);
      expect(mailsTo(outbox, 'nobody@example-bank.test')).toHaveLength(0);
    });

    test("ID-S12: A tenant admin re-issues enrolment behind step-up", async ({ page, apiGuard, request }) => {
      // pending: ID-S12 (ID-05) -> built in chunk 1
      allowFreshContext(apiGuard);
      apiGuard.allow(/\/tenant\/members\/[^/]+\/reissue-enrolment$/, 403, 'the first attempt answers step_up_required and opens the prompt');
      await signInAs(page, LOGINS.admin);
      await page.goto('/admin/members');
      await page.locator('[data-member-id]', { hasText: LOGINS.anna }).click();
      await page.getByRole('button', { name: 'Re-issue enrolment' }).click();
      await expect(page.getByText('Re-issue enrolment? Their sessions end and their passkeys stop working now.')).toBeVisible();
      await page.getByRole('button', { name: 'Re-issue enrolment' }).click();
      const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
      await expect(prompt).toBeVisible();
      await prompt.getByRole('button', { name: 'Use passkey' }).click();
      await expect(page.getByText('Enrolment re-issued. A new invitation is on its way.')).toBeVisible();
      await expect(page.getByText('Awaiting enrolment').first()).toBeVisible();

      const mail = mailsTo(await mailOutbox(request), LOGINS.anna).at(-1);
      expect(mail, 'Anna was notified with a new invitation link').toBeDefined();
      reissuedInvitePath = mail === undefined ? null : inviteLinkFrom(mail);
      expect(reissuedInvitePath).not.toBeNull();
    });

    test("ID-S5: The first passkey activates the account and asks for a second one", async ({ page, apiGuard }) => {
      // pending: ID-S5 (ID-02, ID-03) -> built in chunk 1
      allowFreshContext(apiGuard);
      expect(reissuedInvitePath, 'ID-S12 left a re-issued invitation').not.toBeNull();
      await installAuthenticator(page.context());
      await page.goto(reissuedInvitePath ?? '/');
      await enterInvitationCode(page);
      const reenrolledName = await createPasskey(page);
      await expect(page.getByRole('heading', { level: 1, name: 'Add a second passkey?' })).toBeVisible();
      await expect(page.getByText(`${reenrolledName} added`, { exact: true })).toBeVisible();
      // She may add the second one straight away, on another device: as in ID-S10, this
      // authenticator forgets the first key, which the registration excludes.
      for (const held of await page.context().credentials.get({})) await page.context().credentials.delete(held.id);
      await page.getByRole('button', { name: 'Add another passkey' }).click();
      await expect(page.getByText('Step 3 of 3')).toBeVisible();
      await createPasskey(page);
      await expect(page.locator('[data-who-panel]')).toBeVisible();
      await page.goto('/me/passkeys');
      await expect(page.locator('[data-passkey-id]')).toHaveCount(2);
    });
  });

  test("ID-S8: Passkey sign-in issues a session", async ({ page, apiGuard }) => {
    // pending: ID-S8 (ID-03) -> built in chunk 1
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await expect(page.locator('[data-who-panel]')).toContainText('Example Bank AB');
    await page.goto('/me/sessions');
    await expect(page.locator('[data-session-id][data-current]')).toHaveCount(1);
    await expect(page.getByText('This device', { exact: true })).toBeVisible();
  });

  test("ID-S10: A user adds and renames passkeys and can never remove the last one", async ({ page, apiGuard }) => {
    // pending: ID-S10 (ID-04) -> built in chunk 1
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/me\/passkeys\/[^/]+$/, 409, 'the last passkey cannot be removed (last_passkey)');
    const seededKey = await signInAs(page, LOGINS.auditor);
    // The second passkey is created on another device: this authenticator
    // forgets the seeded key, which the registration excludes.
    await page.context().credentials.delete(seededKey.id);
    await page.goto('/me/passkeys');
    await expect(page.locator('[data-passkey-id]')).toHaveCount(1);
    const seededId = await page.locator('[data-passkey-id]').first().getAttribute('data-passkey-id');
    expect(seededId, 'the seeded passkey is listed').not.toBeNull();
    const seeded = page.locator(`[data-passkey-id="${seededId ?? ''}"]`);
    // Pinned by id: while the rename form is open the name is an input value, not text.
    const phone = page.locator(`[data-passkey-id]:not([data-passkey-id="${seededId ?? ''}"])`);

    // The passkey removed is the one this journey added, never the seeded one: a removed
    // passkey is retired for good, and the auditor's seeded key must survive for a retry
    // and for any later journey that signs in as the auditor (playbook 8.3 rule 4).
    try {
      await page.getByRole('button', { name: 'Add a passkey' }).click();
      const dialog = page.getByRole('dialog', { name: 'Add a passkey' });
      // No name to fill: the server names it from the device and the page says so.
      const addedName = await createPasskey(page, dialog);
      await expect(page.locator('[data-passkey-id]')).toHaveCount(2);
      await expect(page.getByText(`${addedName} added`, { exact: true })).toBeVisible();
      await expect(phone).toContainText(addedName);

      await phone.getByRole('button', { name: 'Rename' }).click();
      await phone.getByLabel('Name', { exact: true }).fill('Work phone');
      await phone.getByRole('button', { name: 'Save' }).click();
      await expect(phone).toContainText('Work phone');
      await expect(phone.getByRole('button', { name: 'Rename' })).toBeVisible();

      await phone.getByRole('button', { name: 'Remove' }).click();
      await expect(phone.getByText('Remove this passkey? You will no longer be able to sign in with it.')).toBeVisible();
      await phone.getByRole('button', { name: 'Remove' }).click();
      await expect(page.locator('[data-passkey-id]')).toHaveCount(1);
      await expect(seeded).toBeVisible();

      // The seeded key is now the only one, and the only one is never removed.
      await seeded.getByRole('button', { name: 'Remove' }).click();
      await seeded.getByRole('button', { name: 'Remove' }).click();
      await expect(seeded.getByText('This is your only passkey. Add another one before removing it.')).toBeVisible();
      await expect(page.locator('[data-passkey-id]')).toHaveCount(1);
    } finally {
      // Teardown that runs on failure too: whatever this attempt added goes, so the
      // auditor holds exactly the seeded passkey again.
      await page.goto('/me/passkeys');
      await expect(seeded).toBeVisible();
      for (let left = await phone.count(); left > 0; left -= 1) {
        const extra = phone.first();
        await extra.getByRole('button', { name: 'Remove' }).click();
        await extra.getByRole('button', { name: 'Remove' }).click();
        await expect(phone).toHaveCount(left - 1);
      }
    }
  });

  test("ID-S11: A user sees and revokes their sessions", async ({ page, apiGuard, browser }) => {
    // pending: ID-S11 (ID-04) -> built in chunk 1
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.owner);

    // The same person on a second device.
    const other = await browser.newContext();
    const otherPage = await other.newPage();
    try {
      await signInAs(otherPage, LOGINS.owner);

      await page.goto('/me/sessions');
      await expect(page.locator('[data-session-id]')).toHaveCount(2);
      const theirs = page.locator('[data-session-id]:not([data-current])');
      await theirs.getByRole('button', { name: 'Sign out this device' }).click();
      await expect(page.locator('[data-session-id]')).toHaveCount(1);

      // The other device's next request answers 401 and it lands on the public page.
      await otherPage.goto('/me/sessions');
      await expect(otherPage).toHaveURL(/\/welcome$/);
      await expect(otherPage.getByRole('heading', { level: 1, name: 'A register of record for everything regulation asks of your bank.' })).toBeVisible();
    } finally {
      await other.close();
    }
  });

  test("ID-S14: A sensitive action without a fresh assertion answers step_up_required", async ({ page, apiGuard }) => {
    // pending: ID-S14 (ID-06, AC-ID3) -> built in chunk 1. Until sign-off exists the
    // sensitive action is a role change (playbook 4.2: role and permission changes).
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/members\/[^/]+$/, 403, 'the first role change answers step_up_required and opens the prompt');
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/members');
    const auditor = page.locator('label', { hasText: /^Auditor/ }).getByRole('checkbox');
    const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
    // The first answer to the restoring save: 200 proves the step-up above was still
    // fresh, so the second sensitive action needed no prompt.
    let restoreStatus: number | null = null;
    try {
      await page.locator('[data-member-id]', { hasText: LOGINS.contributor }).click();
      await expect(auditor).not.toBeChecked();
      await auditor.check();
      await page.getByRole('button', { name: 'Save', exact: true }).click();
      await expect(prompt).toBeVisible();
      await prompt.getByRole('button', { name: 'Use passkey' }).click();
      await expect(page.getByText('Saved.')).toBeVisible();
      await expect(auditor).toBeChecked();
    } finally {
      // Teardown that runs on failure too (playbook 8.3 rule 4): the contributor gets the
      // seeded roles back whatever happened above. Read from a fresh load of the member,
      // whose form renders only once the member is there, so the box shows the server.
      await page.goto('/admin/members');
      await page.locator('[data-member-id]', { hasText: LOGINS.contributor }).click();
      await expect(auditor).toBeVisible();
      if (await auditor.isChecked()) {
        await auditor.uncheck();
        const first = page.waitForResponse((r) => /\/tenant\/members\/[^/]+$/.test(r.url()) && r.request().method() === 'PATCH');
        await page.getByRole('button', { name: 'Save', exact: true }).click();
        restoreStatus = (await first).status();
        // Only on a failure path can the assertion have gone stale: then confirm again.
        if (restoreStatus === 403) await prompt.getByRole('button', { name: 'Use passkey' }).click();
        await expect(page.getByText('Saved.')).toBeVisible();
        await expect(auditor).not.toBeChecked();
      }
    }
    // Reached only when the journey passed: the restore went through without a prompt.
    expect(restoreStatus, 'the restoring save needed no second step-up').toBe(200);
  });

  test("ID-S18: Permissions are code and roles are rows", async ({ page, apiGuard }) => {
    // pending: ID-S18 (ID-09) -> built in chunk 1
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/roles$/, 403, 'creating a role answers step_up_required first and opens the prompt');
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/roles');
    await expect(page.locator('[data-role-key="admin"]')).toContainText('System role');

    await page.getByRole('button', { name: 'Create a role' }).click();
    const form = page.locator('[data-role-form]');
    await form.getByLabel('Key', { exact: true }).fill('legal-reviewer');
    await form.getByLabel('Label (English)').fill('Legal reviewer');
    await form.getByLabel('Label (Swedish)').fill('Juridisk granskare');
    await form.getByLabel('Usage note').fill('Reads cases and saves assessment input');
    await form.locator('label', { hasText: /^cases read/ }).getByRole('checkbox').check();
    await form.locator('label', { hasText: /^cases contribute/ }).getByRole('checkbox').check();
    await form.getByRole('button', { name: 'Create role' }).click();
    const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
    await expect(prompt).toBeVisible();
    await prompt.getByRole('button', { name: 'Use passkey' }).click();

    const row = page.locator('[data-role-key="legal-reviewer"]');
    await expect(row).toBeVisible();
    try {
      await expect(row).toContainText('Legal reviewer');
      await expect(row).toContainText('cases read');
      await expect(row).toContainText('cases contribute');
      await expect(row).not.toContainText('System role');

      // The new row labels the picker: no code names a role.
      await page.goto('/admin/members');
      await page.getByRole('button', { name: 'Invite a person' }).click();
      const dialog = page.getByRole('dialog', { name: 'Invite a person' });
      await expect(dialog.locator('label', { hasText: /^Legal reviewer/ })).toBeVisible();
      await dialog.getByRole('button', { name: 'Cancel' }).click();
    } finally {
      // Teardown that runs on failure too (playbook 8.3 rule 4): retire the role so
      // the seed's picture holds for a retry and the next journey. A retired role
      // leaves the list, which only holds roles that can still be granted.
      await page.goto('/admin/roles');
      await row.getByRole('button', { name: 'Retire' }).click();
      await row.getByRole('button', { name: 'Retire' }).click();
      await expect(row).toHaveCount(0);
    }
  });

  test("ID-S20: An API key is shown once, stored hashed and revocable", async ({ page, apiGuard }) => {
    // pending: ID-S20 (ID-10) -> built in chunk 1
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/api-keys$/, 403, 'creating a key answers step_up_required first and opens the prompt');
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/api-keys');
    await page.getByRole('button', { name: 'Create a key' }).click();
    const form = page.locator('[data-key-form]');
    // A bank's key is offered reads and proposals only: the watch writes belong
    // to the platform's own agents and are not on the form at all.
    await expect(form.locator('label', { hasText: /^proposals write/ })).toBeVisible();
    for (const platformOnly of [/^agent runs write/, /^sources write/, /^changes write/]) {
      await expect(form.locator('label', { hasText: platformOnly })).toHaveCount(0);
    }
    await form.getByLabel('Name', { exact: true }).fill('GRC export sync');
    await form.locator('label', { hasText: /^tenant read/ }).getByRole('checkbox').check();
    await form.locator('label', { hasText: /^search read/ }).getByRole('checkbox').check();
    // The key this run created, pinned by id: a revoked key stays listed, so an earlier
    // attempt's row with the same name must not match (playbook 8.3 rule 4).
    const created = page.waitForResponse((r) => r.url().endsWith('/api/v1/tenant/api-keys') && r.request().method() === 'POST' && r.ok());
    await form.getByRole('button', { name: 'Create key' }).click();
    const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
    await expect(prompt).toBeVisible();
    await prompt.getByRole('button', { name: 'Use passkey' }).click();
    const { id: keyId } = (await (await created).json()) as { id: string };
    const row = page.locator(`[data-key-id="${keyId}"]`);

    try {
      const panel = page.locator('[data-new-key]');
      await expect(panel.getByRole('heading', { name: 'Copy your new key now' })).toBeVisible();
      const plain = (await panel.locator('[data-plain-key]').textContent())?.trim() ?? '';
      expect(plain).toMatch(/^cw_/);
      await expect(row).toContainText('GRC export sync');
      await expect(row).toContainText('tenant read');
      await expect(row).toContainText('search read');
      await expect(row).not.toContainText(plain);

      // Never again: a reload shows the prefix only.
      await page.reload();
      await expect(row).toBeVisible();
      await expect(page.locator('[data-new-key]')).toHaveCount(0);
      await expect(page.getByText(plain)).toHaveCount(0);

      await row.getByRole('button', { name: 'Revoke' }).click();
      await page.getByRole('dialog', { name: 'Revoke GRC export sync?' }).getByRole('button', { name: 'Revoke key' }).click();
      await expect(row).toContainText('Key revoked.');
      await expect(row).toContainText('Revoked');
      await expect(row.getByRole('button', { name: 'Revoke' })).toHaveCount(0);
    } finally {
      // Teardown that runs on failure too: a live key never outlives the attempt.
      await page.goto('/admin/api-keys');
      await expect(row).toBeVisible();
      if ((await row.getByRole('button', { name: 'Revoke' }).count()) > 0) {
        await row.getByRole('button', { name: 'Revoke' }).click();
        await page.getByRole('dialog').getByRole('button', { name: 'Revoke key' }).click();
        await expect(row).toContainText('Revoked');
      }
    }
  });

  test("ID-S20: An agent key is shown once in the console and is bound to its agent", async ({ page, apiGuard }) => {
    // ID-10, AGT-01: a platform administrator mints a key bound to the watch
    // sweeper through the console's own form, behind a passkey step-up.
    const stepUp = page.waitForResponse((r) => r.url().endsWith('/api/v1/agent-keys') && r.request().method() === 'POST' && r.status() === 403);
    const { id, plainKey } = await mintAgentKey(page, apiGuard, { name: `ID-S20 sweeper ${Date.now()}`, agent: 'watch-sweeper', scopes: ['agent-runs:write', 'sources:write'] });
    const row = page.locator(`[data-agent-key-id="${id}"]`);

    try {
      expect(((await (await stepUp).json()) as { code: string }).code).toBe('step_up_required');
      await expect(row).toContainText('watch-sweeper');
      await expect(row).toContainText('agent runs write');
      await expect(row).toContainText('sources write');
      await expect(row).toContainText(`Key ${plainKey.split('_')[1]}`);
      await expect(row).not.toContainText(plainKey);

      // Never again: a reload shows the prefix only.
      await page.reload();
      await expect(row).toBeVisible();
      await expect(page.locator('[data-new-key]')).toHaveCount(0);
      await expect(page.getByText(plainKey)).toHaveCount(0);

      await revokeAgentKey(page, id);
      await expect(row.getByRole('button', { name: 'Revoke' })).toHaveCount(0);
    } finally {
      // Teardown that runs on failure too: a live key never outlives the attempt.
      await revokeAgentKey(page, id);
    }
  });

  test("ID-S26: A denied request answers a structured 403 the UI renders as is", async ({ page, apiGuard }) => {
    // pending: ID-S26 (ID-09) -> built in chunk 1
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/api\/v1\/tenant$/, 403, 'a reader may not change the profile (permission_denied)');
    await signInAs(page, LOGINS.reader);
    // The client gate: the missing grant in plain words, before any call.
    await page.goto('/admin/members');
    await expect(restrictedScreen(page)).toContainText('Needs members manage');
    // The server's 403: rendered as is where the write happened.
    await page.goto('/admin/organisation');
    await expect(page.getByRole('heading', { level: 1, name: 'Organisation' })).toBeVisible();
    await page.getByRole('button', { name: 'Save' }).click();
    const alert = page.locator('[data-problem-code="permission_denied"]');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText('Needs security manage');
  });

  test("ACC-S3: A service key acts as the entry and a personal token acts as the person", async ({ page, browser, playwright, apiGuard }, testInfo) => {
    // ACC-03: an administrator issues an entry's service key, a compliance officer mints a
    // personal token that reads as them, each is used and logged with its own method, the
    // administrator sees both with their kind and who each reads as, and revokes the token.
    test.setTimeout(180_000);
    allowFreshContext(apiGuard);
    allowAgentAccessStepUps(apiGuard);
    apiGuard.allow(/\/api\/v1\/me\/tokens$/, 403, 'minting a token answers step_up_required first and opens the prompt');
    const attempt = `${Date.now()}`;
    const entryName = `ACC-S3 order router ${attempt}`;
    const tokenName = `ACC-S3 laptop ${attempt}`;
    let entryId: string | null = null;
    let tokenId: string | null = null;
    const agents: APIRequestContext[] = [];
    const callWith = async (plainKey: string): Promise<APIRequestContext> => {
      const agent = await playwright.request.newContext({ baseURL: BACKEND_URL, extraHTTPHeaders: { 'X-API-Key': plainKey } });
      agents.push(agent);
      return agent;
    };

    // The administrator works on this page, the member in a context of their own.
    await signInAs(page, LOGINS.admin);
    const member = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
    const memberPage = await member.newPage();
    apiGuard.watch(memberPage);

    try {
      // The administrator issues the entry's service key behind a passkey.
      entryId = await registerEntry(page, entryName);
      const serviceKey = await issueEntryKey(page, entryId, { name: `${entryName} CI`, scopes: ['library:read'] });

      // The member mints a token with a passkey; it shows once, with its expiry.
      await signInAs(memberPage, LOGINS.tokens);
      await memberPage.goto('/me/tokens');
      await memberPage.getByRole('button', { name: 'Create a token' }).first().click();
      const form = memberPage.locator('[data-token-form]');
      await form.getByLabel('Name', { exact: true }).fill(tokenName);
      await form.getByLabel(/^library read/).check();
      await form.getByLabel('Expires', { exact: true }).fill(stockholmDayPlus(30));
      const minted = memberPage.waitForResponse((r) => r.url().endsWith('/api/v1/me/tokens') && r.request().method() === 'POST' && r.status() === 201);
      await form.getByRole('button', { name: 'Create token' }).click();
      const panel = memberPage.locator('[data-new-key]');
      await confirmWithPasskey(memberPage, panel);
      tokenId = ((await (await minted).json()) as { id: string }).id;
      await expect(panel.getByRole('heading', { name: 'Copy your token now' })).toBeVisible();
      const plainToken = (await panel.locator('[data-plain-key]').textContent())?.trim() ?? '';
      expect(plainToken).toMatch(/^cw_/);
      await panel.getByRole('button', { name: 'Done' }).click();
      const tokenRow = memberPage.locator(`[data-token-id="${tokenId}"]`);
      await expect(tokenRow).toContainText(tokenName);
      await expect(tokenRow).toContainText('reads as me');
      await expect(tokenRow).toContainText('library read');

      // Never again: the member's list holds their token by its prefix only.
      await memberPage.reload();
      await expect(tokenRow).toBeVisible();
      await expect(memberPage.getByText(plainToken)).toHaveCount(0);

      // Both credentials read the library: the key as its entry, the token as its person.
      const asEntry = await callWith(serviceKey);
      const asMember = await callWith(plainToken);
      expect((await asEntry.get('/api/v1/obligations', { params: { limit: 1 } })).status()).toBe(200);
      expect((await asMember.get('/api/v1/obligations', { params: { limit: 1 } })).status()).toBe(200);

      // Each use is in the security log with its own method.
      await page.goto('/admin/security-log');
      const tokenUse = page.locator('[data-event="token_used"]', { hasText: LOGINS.tokens }).first();
      await expect(tokenUse).toContainText('Token used');
      await expect(tokenUse).toContainText('Personal access token');
      await expect(page.locator('[data-event="key_used"]').first()).toContainText('API key');

      // The administrator sees both, with their kind and who each reads as.
      await page.goto('/admin/api-keys');
      const tokenListed = page.locator(`[data-key-id="${tokenId}"]`);
      await expect(tokenListed).toContainText('Personal');
      await expect(tokenListed).toContainText('Acts as Elsa Hansson');
      const keyListed = page.locator('[data-key-kind="service"]', { hasText: `${entryName} CI` });
      await expect(keyListed).toContainText('Service');
      await expect(keyListed).toContainText(`Reads as ${entryName}`);

      // Revoking the token needs no passkey; its next request answers 401.
      await tokenListed.getByRole('button', { name: 'Revoke' }).click();
      const confirm = page.getByRole('dialog', { name: `Revoke Elsa Hansson's token "${tokenName}"?` });
      await confirm.getByRole('button', { name: 'Revoke token' }).click();
      await expect(tokenListed.getByText('Token revoked.')).toBeVisible();
      await expect(tokenListed).toContainText('Revoked');
      expect((await asMember.get('/api/v1/obligations', { params: { limit: 1 } })).status()).toBe(401);
      await page.goto('/admin/security-log');
      // The revocation is logged as a token's, under the administrator who revoked it.
      await expect(page.locator('[data-event="token_revoked"]', { hasText: LOGINS.admin }).first()).toContainText('Personal access token');

      // The member sees it revoked on their own list.
      await memberPage.reload();
      await expect(tokenRow).toContainText('Revoked');
      await expect(tokenRow.getByRole('button', { name: 'Revoke' })).toHaveCount(0);
    } finally {
      // Teardown that runs on failure too: no credential of this attempt stays live.
      await Promise.all(agents.map((agent) => agent.dispose()));
      if (tokenId !== null) {
        await page.goto('/admin/api-keys');
        const row = page.locator(`[data-key-id="${tokenId}"]`);
        await expect(row).toBeVisible();
        if ((await row.getByRole('button', { name: 'Revoke' }).count()) > 0) {
          await row.getByRole('button', { name: 'Revoke' }).click();
          await page.getByRole('dialog').getByRole('button', { name: 'Revoke token' }).click();
          await expect(row.getByText('Token revoked.')).toBeVisible();
        }
      }
      if (entryId !== null) await revokeEntry(page, entryId);
      await member.close();
    }
  });

  test("ACC-S3: A member without tokens.create is told why and mints nothing", async ({ page, apiGuard }) => {
    // ACC-03: the page is every member's own; without the permission it lists what they
    // hold, offers no Create, and says which permission creating needs.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await page.goto('/me/tokens');
    await expect(page.getByRole('heading', { level: 1, name: 'My access tokens' })).toBeVisible();
    await expect(page.getByText('Creating tokens needs tokens create, which your role does not include. Ask your administrator if you need one.').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create a token' })).toHaveCount(0);
  });
});
