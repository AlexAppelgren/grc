import { execFileSync } from 'node:child_process';
import path from 'node:path';

import type { Page } from '@playwright/test';

import { expect, test, type ApiGuard } from './support/api-guard';
import { openCase } from './support/cases-signoff';
import { allowRegisterEntryPending } from './support/obligation-page';
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

// c11-fe-admin-security (ADM-S1, ID-08): the admin sets the bank's session limits. Above the
// platform maximum the server's 422 renders under its field; a limit at the maximum saves
// behind the passkey step-up. The limits the bank had are restored whatever happens, so no
// other journey signs in under a changed session policy for longer than this step.
const SECURITY_POLICY = /\/api\/v1\/tenant\/security-policy$/;
type SessionLimits = { sessionIdleMinutes: number | null; sessionAbsoluteHours: number | null; sessionAbsoluteHoursMax: number };

async function saveSecurityPage(page: Page): Promise<void> {
  const answered = page.waitForResponse((r) => SECURITY_POLICY.test(r.url()) && r.request().method() === 'PUT' && r.status() !== 403);
  await page.getByRole('button', { name: 'Save' }).click();
  // The step-up is asked for unless this session's passkey assertion is still fresh.
  const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
  const prompted = prompt.waitFor({ state: 'visible' }).then(
    () => true,
    () => false,
  );
  if (await Promise.race([answered.then(() => false), prompted])) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  await answered;
}

async function setSessionLimits(page: Page, apiGuard: ApiGuard): Promise<void> {
  apiGuard.allow(SECURITY_POLICY, 403, 'the save answers step_up_required first and opens the prompt');
  apiGuard.allow(SECURITY_POLICY, 422, 'a limit above the platform maximum is refused with above_platform_maximum');
  const read = page.waitForResponse((r) => SECURITY_POLICY.test(r.url()) && r.request().method() === 'GET');
  await page.goto('/admin/security');
  const held = (await (await read).json()) as SessionLimits;
  const absolute = page.getByLabel('Sign out after this long in all, in hours', { exact: true });
  const idle = page.getByLabel('Sign out after this long without activity, in minutes', { exact: true });
  const max = held.sessionAbsoluteHoursMax;
  await expect(page.getByText(`At most ${max} hours.`, { exact: false })).toBeVisible();
  // No passkey policy on this page in this release (D-100).
  await expect(page.getByText('Passkeys we accept')).toHaveCount(0);
  try {
    await absolute.fill(String(max + 1));
    await saveSecurityPage(page);
    await expect(page.getByText(`At most ${max} hours. Choose ${max} or fewer.`, { exact: true })).toBeVisible();
    await expect(absolute).toHaveAttribute('aria-invalid', 'true');

    // At the maximum, never below what the bank had: nobody is signed out sooner by this step.
    await absolute.fill(String(max));
    await saveSecurityPage(page);
    await expect(page.getByText('Saved. New limits apply to sessions from their next refresh.', { exact: true })).toBeVisible();
    await page.reload();
    await expect(absolute).toHaveValue(String(max));
  } finally {
    await page.goto('/admin/security');
    await idle.fill(held.sessionIdleMinutes === null ? '' : String(held.sessionIdleMinutes));
    await absolute.fill(held.sessionAbsoluteHours === null ? '' : String(held.sessionAbsoluteHours));
    await saveSecurityPage(page);
    await expect(page.getByText('Saved. New limits apply to sessions from their next refresh.', { exact: true })).toBeVisible();
  }
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

// r2-j8-isolation (TEN-S7, J-8): tenant A's R2 rows the journey reaches for from tenant B, as
// backend/apps/shared/e2e_seed.py seeds them (EXPECTED_J8_ISOLATION, EXPECTED_ORG_REGISTER,
// EXPECTED_COMMENTS and the participants block). The fixed ids are the seed's; the rest are
// found by name or purpose in tenant A's own session.
const A_ONLY = {
  sharedCase: { stableKey: 'chg-e2e-c5-timeline', title: 'FI clarifies the appropriateness assessment for complex instruments' },
  caseComment: 'Erik, the appropriateness procedure for structured products now names the new test; the evidence is attached.',
  evidence: 'Research payment criteria.pdf',
  commentedObligation: 'obl-dora-ict-register',
  obligationComment: 'Oskar, does the register also need the sub-outsourcing chain for the card processor?',
  participationObligation: 'obl-costs-charges',
  participant: 'Oskar Lund',
  entity: 'Example Liv Försäkring AB',
  department: 'Retail Banking',
  product: 'Guided investing',
  team: 'cards',
  grantPurpose: "Checking why last week's briefing reached nobody at the bank.",
  entryId: '00000000-0000-4000-a000-000000008c03',
  entryName: 'Card settlement checker',
  keyId: '00000000-0000-4000-a000-000000008c04',
  tenantAgentKey: 'tenant-source-watch',
  idleMinutes: '45',
} as const;
// Tenant B's own rows beside them, so every list below is not empty by accident.
const B_OWN = {
  obligationComment: 'The register must be complete before we file it with Finanstilsynet.',
  participant: 'Freja Madsen',
  entity: 'Second Bank A/S',
  product: 'Online custody account',
  team: 'aml_desk',
  evidence: 'Research payment criteria (DK).pdf',
} as const;

type Named = { id: string; name: string };

/** A read in the signed-in bank's own session, which must answer. */
async function readAs<T>(page: Page, headers: Record<string, string>, path: string): Promise<T> {
  const response = await page.request.get(`${BACKEND_URL}/api/v1${path}`, { headers });
  expect(response.status(), path).toBe(200);
  return (await response.json()) as T;
}

function idNamed(items: readonly Named[], name: string): string {
  const row = items.find((item) => item.name === name);
  if (row === undefined) throw new Error(`tenant A has no "${name}"`);
  return row.id;
}

/**
 * Calls the API from the signed-in page, as a person typing the URL would reach it, and
 * expects 404 `not_found`: another bank's record is not there, never forbidden. The 404 is
 * declared where it is expected, so any other failure still fails the journey.
 */
async function expectNotFound(page: Page, apiGuard: ApiGuard, headers: Record<string, string>, method: string, path: string, body?: object): Promise<void> {
  const url = `${BACKEND_URL}/api/v1${path}`;
  apiGuard.allow(new URL(url).pathname, 404, "tenant A's record is not there for tenant B");
  const answer = await page.evaluate(
    async ({ url, method, headers, body }) => {
      const response = await fetch(url, {
        method,
        headers: { ...headers, ...(body === null ? {} : { 'Content-Type': 'application/json', 'If-Match': '"1"' }) },
        body: body === null ? undefined : JSON.stringify(body),
      });
      return { status: response.status, code: ((await response.json()) as { code?: string }).code };
    },
    { url, method, headers, body: body ?? null },
  );
  expect(answer, `${method} ${path}`).toEqual({ status: 404, code: 'not_found' });
}

/**
 * A real passkey step-up in the signed-in page, the ceremony the app's prompt runs, so a
 * route behind a fresh assertion answers for the record rather than for the missing step-up.
 */
async function stepUp(page: Page, headers: Record<string, string>): Promise<void> {
  const status = await page.evaluate(
    async ({ base, headers }) => {
      type Options = { challenge: string; rpId?: string; timeout?: number; userVerification?: UserVerificationRequirement; allowCredentials?: { id: string }[] };
      const bytes = (value: string) => Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(value.length / 4) * 4, '=')), (c) => c.charCodeAt(0));
      const text = (buffer: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(buffer))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      const post = (route: string, body: unknown) => fetch(`${base}${route}`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const answer = (await (await post('/auth/step-up/options', {})).json()) as Options | { publicKey: Options };
      const options = 'publicKey' in answer ? answer.publicKey : answer;
      const credential = (await navigator.credentials.get({
        publicKey: {
          challenge: bytes(options.challenge),
          rpId: options.rpId,
          timeout: options.timeout,
          userVerification: options.userVerification,
          allowCredentials: (options.allowCredentials ?? []).map((allowed) => ({ type: 'public-key' as const, id: bytes(allowed.id) })),
        },
      })) as PublicKeyCredential;
      const signed = credential.response as AuthenticatorAssertionResponse;
      const verified = await post('/auth/step-up/verify', {
        credential: {
          id: credential.id,
          rawId: text(credential.rawId),
          type: credential.type,
          clientExtensionResults: {},
          response: {
            clientDataJSON: text(signed.clientDataJSON),
            authenticatorData: text(signed.authenticatorData),
            signature: text(signed.signature),
            userHandle: signed.userHandle === null ? null : text(signed.userHandle),
          },
        },
      });
      return verified.status;
    },
    { base: `${BACKEND_URL}/api/v1`, headers },
  );
  expect(status, 'the passkey step-up').toBe(200);
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

  test("TEN-S4: An out-of-office delegate receives approvals and reminders", async ({ page, apiGuard }) => {
    // TEN-S4 (TEN-04, COL-02): the absent approver's own screen. Henrik Wallin sets his
    // last day away on the bank's calendar and a delegate who holds his approve
    // permissions; a delegate who cannot approve is refused under the field, a second
    // absence set meanwhile from another tab is refused as already_delegated, and End now
    // brings the work back. Where the notices then go is proved by the integration
    // scenario (tenants/tests_scenarios.py, collab/tests_delegation.py): no screen yet
    // requests a sign-off or sends a reminder on demand.
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/api\/v1\/me\/out-of-office$/, 422, 'a contributor cannot approve, so cannot stand in');
    apiGuard.allow(/\/api\/v1\/me\/out-of-office$/, 409, 'the absence was set meanwhile from another tab');
    // The seeded approver roles (backend/apps/shared/e2e_logins.py): Maria Ek holds what
    // Henrik approves; Karin Nyström, a contributor, holds none of it.
    const DELEGATE = 'Maria Ek';
    const CANNOT_APPROVE = 'Karin Nyström';
    // A week from the bank's today (Europe/Stockholm), never a literal date.
    const bankToday = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm' }).format(new Date());
    const lastDay = new Date(`${bankToday}T12:00:00Z`);
    lastDay.setUTCDate(lastDay.getUTCDate() + 7);
    const untilDate = lastDay.toISOString().slice(0, 10);

    const pickDelegate = async (target: Page, name: string) => {
      const combo = target.getByRole('combobox', { name: 'Delegate' });
      await combo.fill(name.slice(0, 4));
      await target.getByRole('listbox', { name: 'People' }).getByRole('option', { name, exact: true }).click();
      await expect(combo).toHaveValue(name);
    };
    const endNow = page.getByRole('button', { name: 'End now' });
    const setButton = page.getByRole('button', { name: 'Set out of office' });

    await signInAs(page, LOGINS.awayApprover);
    await page.goto('/me/out-of-office');
    await expect(page.getByRole('heading', { level: 1, name: 'Out of office' })).toBeVisible();
    // Settle before branching: a failed earlier run may have left him away.
    await expect(endNow.or(setButton).first()).toBeVisible();
    if (await endNow.isVisible()) {
      await endNow.click();
      await expect(setButton).toBeVisible();
    }
    await expect(page.getByLabel('Away until')).toHaveAttribute('min', bankToday);
    try {
      // A second tab of the same person, open on the form before the absence exists.
      const other = await page.context().newPage();
      apiGuard.watch(other);
      await other.goto('/me/out-of-office');
      await expect(other.getByRole('button', { name: 'Set out of office' })).toBeVisible();

      await page.getByLabel('Away until').fill(untilDate);
      await pickDelegate(page, CANNOT_APPROVE);
      await setButton.click();
      await expect(page.getByText(`${CANNOT_APPROVE} cannot approve, so they cannot stand in for you. Choose someone whose role can approve.`)).toBeVisible();
      await expect(page.getByRole('combobox', { name: 'Delegate' })).toHaveAttribute('aria-invalid', 'true');

      await pickDelegate(page, DELEGATE);
      await setButton.click();
      const away = page.locator('[data-away]');
      await expect(away.getByRole('heading', { name: 'You are away' })).toBeVisible();
      await expect(away).toContainText(`${DELEGATE} receives your approval requests and reminders.`);
      await page.reload();
      await expect(away).toContainText(`${DELEGATE} receives your approval requests and reminders.`);

      // The other tab still shows the form; its absence is refused by its code.
      await other.getByLabel('Away until').fill(untilDate);
      await pickDelegate(other, DELEGATE);
      await other.getByRole('button', { name: 'Set out of office' }).click();
      await expect(other.getByText('You are already away. End that first to set a new one.')).toBeVisible();
      await other.getByRole('button', { name: 'Show it' }).click();
      await expect(other.locator('[data-away]')).toContainText(DELEGATE);
      await other.close();

      await endNow.click();
      await expect(page.getByText('You are back. Approval requests and reminders come to you again.')).toBeVisible();
      await expect(setButton).toBeVisible();
    } finally {
      // Leave Henrik at home whatever happened above.
      await page.goto('/me/out-of-office');
      await expect(endNow.or(setButton).first()).toBeVisible();
      if (await endNow.isVisible()) {
        await endNow.click();
        await expect(setButton).toBeVisible();
      }
    }
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
    // TEN-S7 (NFR-01, TEN-02, TEN-03, TEN-06, COL-01, COL-02, COL-04, AGT-04, ACC-01, ID-08, J-8):
    // tenant A's members, scope, roles and tags, and its R2 records and configuration, are not
    // there for tenant B, by URL or in a list; B's own rows are.
    test.slow();
    allowFreshContext(apiGuard);
    allowRegisterEntryPending(apiGuard);
    apiGuard.allow(/\/tenant\/members\/[^/]+\/sessions$/, 404, "another tenant's member is not there, never forbidden");
    apiGuard.allow(/\/api\/v1\/agent-access\/[^/]+(\/calls)?$/, 404, "tenant A's agent access entry is not there for tenant B");

    // Tenant A: the member, role and tag exist, and so does each R2 record below, so their
    // absence in B is not vacuous. Ids B cannot learn from its own screens are read here.
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/members');
    const memberOfA = page.locator('[data-member-id]', { hasText: LOGINS.reader });
    await expect(memberOfA).toBeVisible();
    const memberUrl = await memberOfA.getAttribute('href');
    expect(memberUrl).toMatch(/^\/admin\/members\/.+/);
    await page.goto('/admin/roles');
    await expect(page.locator(`[data-role-key="${A_ONLY_ROLE}"]`)).toBeVisible();
    await page.goto(`/admin/vocabularies/${A_ONLY_TAG_LIST}`);
    await expect(page.locator(`[data-value-key="${A_ONLY_TAG}"]`)).toBeVisible();
    await page.goto(`/admin/agents/access/${A_ONLY.entryId}`);
    await expect(page.getByText(A_ONLY.entryName).first()).toBeVisible();
    await openCase(page, A_ONLY.sharedCase);
    await expect(page.locator('[data-comments-panel="change_case"]')).toContainText(A_ONLY.caseComment);
    const changeId = new URL(page.url()).pathname.split('/').pop() ?? '';
    const asA = await bearerOf(page);
    const aCaseId = (await readAs<{ case: { id: string } }>(page, asA, `/changes/${changeId}`)).case.id;
    const aEvidenceId = idNamed((await readAs<{ items: Named[] }>(page, asA, `/changes/${changeId}/evidence`)).items, A_ONLY.evidence);
    const aUnits = (await readAs<{ items: Named[] }>(page, asA, '/tenant/org-units?limit=100')).items;
    const aEntityId = idNamed(aUnits, A_ONLY.entity);
    const aDepartmentId = idNamed(aUnits, A_ONLY.department);
    const aProductId = idNamed((await readAs<{ items: Named[] }>(page, asA, '/tenant/products?limit=100')).items, A_ONLY.product);
    const aGrants = (await readAs<{ items: { id: string; purpose: string }[] }>(page, asA, '/tenant/support-access?limit=100')).items;
    const aGrantId = aGrants.find((grant) => grant.purpose === A_ONLY.grantPurpose)?.id ?? '';
    expect(aGrantId, "A's declined support request").not.toBe('');
    const library = (await readAs<{ items: { id: string; stableKey: string }[] }>(page, asA, '/obligations?footprint=all&limit=100')).items;
    const obligationPath = (stableKey: string): string => `/inventory/obligations/${library.find((row) => row.stableKey === stableKey)?.id ?? stableKey}`;
    const aInbox = (await readAs<{ items: { id: string; subjectId: string }[] }>(page, asA, '/notifications?limit=100')).items;
    const aTenantAgentId = (await readAs<{ items: { id: string; agent: string }[] }>(page, asA, '/agents')).items.find((row) => row.agent === A_ONLY.tenantAgentKey)?.id ?? '';
    expect(aTenantAgentId, "A's own agent").not.toBe('');
    const aNotificationId = aInbox.find((row) => row.subjectId === aCaseId)?.id;
    expect(aNotificationId, "the mention on A's case is in A's inbox").toBeDefined();
    await signOut(page);

    // Tenant B's compliance officer: B's own case on the change both banks work on, the
    // obligations both discuss and take part in, and B's inbox.
    await signInAs(page, LOGINS.secondBankComplianceOfficer);
    await expect(page.locator('[data-who-panel]')).toContainText('Second Bank A/S');
    const commentsRead = page.waitForResponse((r) => r.url().includes('/api/v1/comments?') && r.request().method() === 'GET');
    await openCase(page, A_ONLY.sharedCase);
    expect((await commentsRead).status(), "B's comments on its own case").toBe(200);
    const caseComments = page.locator('[data-comments-panel="change_case"]');
    await expect(caseComments).toBeVisible();
    await expect(caseComments).not.toContainText(A_ONLY.caseComment);
    const asB = await bearerOf(page);
    const bEvidence = (await readAs<{ items: Named[] }>(page, asB, `/changes/${changeId}/evidence`)).items.map((row) => row.name);
    expect(bEvidence).toContain(B_OWN.evidence);
    expect(bEvidence).not.toContain(A_ONLY.evidence);
    await expectNotFound(page, apiGuard, asB, 'GET', `/comments?subjectType=change_case&subjectId=${aCaseId}`);
    await expectNotFound(page, apiGuard, asB, 'GET', `/evidence/${aEvidenceId}/download`);

    // Opened by URL: neither obligation need be in B's own scope for B to discuss it.
    await page.goto(obligationPath(A_ONLY.commentedObligation));
    const obligationComments = page.locator('[data-comments-panel="obligation"]');
    await expect(obligationComments).toContainText(B_OWN.obligationComment);
    await expect(obligationComments).not.toContainText(A_ONLY.obligationComment);

    await page.goto(obligationPath(A_ONLY.participationObligation));
    const participants = page.locator('[data-participants-panel]');
    await expect(participants.locator('[data-participant-id]').filter({ hasText: B_OWN.participant })).toHaveCount(1);
    await expect(participants).not.toContainText(A_ONLY.participant);

    const inbox = page.waitForResponse((r) => /\/api\/v1\/notifications(\?|$)/.test(r.url()) && r.request().method() === 'GET');
    await page.goto('/notifications');
    const bInbox = ((await (await inbox).json()) as { items: { id: string }[] }).items.map((row) => row.id);
    await expect(page.locator('[data-notifications-list]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    expect(bInbox).not.toContain(aNotificationId);
    await expect(page.locator(`[data-notification-id="${aNotificationId}"]`)).toHaveCount(0);
    await expectNotFound(page, apiGuard, asB, 'POST', `/notifications/${aNotificationId}/read`);
    await signOut(page);

    // Tenant B's administrator: A's member, agent access entry and configuration by URL, and
    // B's own lists.
    await signInAs(page, LOGINS.secondBankAdmin);
    await expect(page.locator('[data-who-panel]')).toContainText('Second Bank A/S');
    await page.goto(memberUrl ?? '/admin/members/none');
    await expect(page.getByRole('heading', { level: 1, name: 'Not found' })).toBeVisible();
    await expect(page.getByText('This page is not available to you')).toHaveCount(0);
    await page.goto(`/admin/agents/access/${A_ONLY.entryId}`);
    await expect(page.getByRole('heading', { level: 1, name: 'Not found' })).toBeVisible();
    await expect(page.getByText('This page is not available to you')).toHaveCount(0);
    await expect(page.locator('main')).not.toContainText(A_ONLY.entryName);

    const asBAdmin = await bearerOf(page);
    await expectNotFound(page, apiGuard, asBAdmin, 'GET', `/tenant/org-units/${aEntityId}/licences`);
    await expectNotFound(page, apiGuard, asBAdmin, 'GET', `/tenant/org-units/${aDepartmentId}/licences`);
    await expectNotFound(page, apiGuard, asBAdmin, 'PATCH', `/tenant/products/${aProductId}`, {});
    await expectNotFound(page, apiGuard, asBAdmin, 'GET', `/tenant/teams/${A_ONLY.team}/members`);
    await expectNotFound(page, apiGuard, asBAdmin, 'POST', `/tenant/support-access/${aGrantId}/decline`);
    await expectNotFound(page, apiGuard, asBAdmin, 'PATCH', `/agents/${aTenantAgentId}`, {});
    await expectNotFound(page, apiGuard, asBAdmin, 'POST', `/agents/${aTenantAgentId}/pause`);
    await expectNotFound(page, apiGuard, asBAdmin, 'GET', `/agent-access/${A_ONLY.entryId}/calls`);
    // Revoking a key needs a fresh passkey; with it, A's key is not there either.
    await stepUp(page, asBAdmin);
    await expectNotFound(page, apiGuard, asBAdmin, 'POST', `/agent-access/${A_ONLY.entryId}/keys/${A_ONLY.keyId}/revoke`);

    await page.goto('/admin/members');
    const rows = page.locator('[data-member-id]');
    await expect(rows.first()).toBeVisible();
    const emails = await rows.allTextContents();
    expect(emails.length).toBeGreaterThan(0);
    for (const text of emails) {
      expect(text).toContain('second-bank.test');
      expect(text).not.toContain('example-bank.test');
    }

    // B's organisation: its own entity, product and team, and none of A's.
    await page.goto('/admin/organisation');
    await expect(page.locator(`[data-org-unit="${B_OWN.entity}"]`)).toBeVisible();
    await expect(page.locator(`[data-product="${B_OWN.product}"]`)).toBeVisible();
    await expect(page.locator(`[data-team="${B_OWN.team}"]`)).toBeVisible();
    await expect(page.locator(`[data-org-unit="${A_ONLY.entity}"]`)).toHaveCount(0);
    await expect(page.locator(`[data-department="${A_ONLY.department}"]`)).toHaveCount(0);
    await expect(page.locator(`[data-product="${A_ONLY.product}"]`)).toHaveCount(0);
    await expect(page.locator(`[data-team="${A_ONLY.team}"]`)).toHaveCount(0);

    // B's support access, agents, agent access entries and session limits are B's own.
    await page.goto('/admin/support-access');
    await expect(page.locator('[data-support-section="history"]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    await expect(page.locator(`[data-grant-id="${aGrantId}"]`)).toHaveCount(0);
    await page.goto('/admin/agents');
    await expect(page.locator('[data-our-agents]')).toBeVisible();
    await expect(page.locator(`[data-tenant-agent="${aTenantAgentId}"]`)).toHaveCount(0);
    await page.goto('/admin/agents/access');
    await expect(page.locator('[data-access-list]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    await expect(page.locator(`[data-entry-id="${A_ONLY.entryId}"]`)).toHaveCount(0);
    await page.goto('/admin/security');
    const idle = page.getByLabel('Sign out after this long without activity, in minutes', { exact: true });
    await expect(idle).toBeVisible();
    await expect(idle).not.toHaveValue(A_ONLY.idleMinutes);

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
    // c11-fe-admin-security: the security page (ID-08) is the admin's by security.manage.
    await expect(page.locator('[data-admin-section="admin-security"]')).toBeVisible();
    await setSessionLimits(page, apiGuard);
    await signOut(page);

    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/admin');
    await expect(page.locator('[data-admin-section="admin-organisation"]')).toBeVisible();
    await expect(page.locator('[data-admin-section="admin-members"]')).toHaveCount(0);
    await expect(page.locator('[data-admin-section="admin-security-log"]')).toHaveCount(0);
    await page.goto('/admin/members');
    await expect(restrictedScreen(page)).toContainText('Needs members manage');
    // c11-fe-admin-security: without security.manage the security page is neither listed nor open.
    await expect(page.locator('[data-admin-section="admin-security"]')).toHaveCount(0);
    await page.goto('/admin/security');
    await expect(restrictedScreen(page)).toContainText('Needs security manage');

    // --- c11-fe-admin-agents: Agents (AGT-03, AGT-04, ADM-01) ---------------------------
    // Every member holding watch.read reaches Agents and reads what bleqq watches; the
    // controls are drawn only for agents.manage, which the compliance officer lacks, so the
    // page says what changing agents needs instead of answering a page-level 403.
    await page.goto('/admin');
    await page.locator('[data-admin-section="admin-agents"]').click();
    await expect(page).toHaveURL(/\/admin\/agents$/);
    await expect(page.getByRole('heading', { name: 'What bleqq watches' })).toBeVisible();
    // bleqq's agents, or the empty state until the seed publishes one: settled, then read.
    const watch = page.locator('[data-platform-watch]');
    await expect(watch.locator('[data-platform-agent]').or(watch.getByRole('heading', { name: 'Nothing to show yet' })).first()).toBeVisible();
    await expect(page.getByText('Changing agents needs agents manage.')).toBeVisible();
    await expect(page.locator('[data-our-agents], [data-agent-budget]')).toHaveCount(0);
    await expect(page.locator('[data-platform-watch]').getByRole('button')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Add an agent' })).toHaveCount(0);
    await signOut(page);

    // The admin holds agents.manage: bleqq's watch stays read-only above the bank's own
    // spend and agents. Research requests answer 501 until c11-research-requests builds them,
    // and a seeded agent of the bank's own would open that panel.
    apiGuard.allow(/\/research-requests$/, 501, 'research requests are built by c11-research-requests');
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin');
    await page.locator('[data-admin-section="admin-agents"]').click();
    await expect(page).toHaveURL(/\/admin\/agents$/);
    await expect(page.getByRole('heading', { name: 'What bleqq watches' })).toBeVisible();
    await expect(page.locator('[data-platform-watch]').getByRole('button')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Spend this month' })).toBeVisible();
    await expect(page.getByText("Our own agents only. bleqq's watch runs at bleqq's cost and is not counted here.")).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Our agents', exact: true })).toBeVisible();
    await expect(page.getByText('Changing agents needs agents manage.')).toHaveCount(0);
    // --- end c11-fe-admin-agents ----------------------------------------------------------
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
