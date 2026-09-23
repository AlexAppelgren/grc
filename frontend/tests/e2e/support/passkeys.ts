import type { APIRequestContext, BrowserContext, Locator, Page } from '@playwright/test';

import { expect, type ApiGuard } from './api-guard';

// Passkey fixtures for journeys (playbook 8.3, ID-*). Playwright 1.61+
// exposes `browserContext.credentials`, a virtual WebAuthn authenticator
// (verified against the installed @playwright/test 1.63.0 typings):
//   credentials.install()                      replaces every real authenticator in the context
//   credentials.create(rpId, {id, userHandle, privateKey, publicKey})
//                                              seeds a known, discoverable credential; all four
//                                              base64url fields together import a fixed key
//   credentials.get({rpId?, id?})              lists held credentials with their keys
//   credentials.delete(id)                     removes one
// Call install() before navigating to a page that uses WebAuthn. Never
// inject tokens or cookies; the sign-in page runs a real ceremony.
//
// The fixed key pairs live in ./e2e-passkeys.generated.ts, written by
// backend/scripts/generate_e2e_passkeys.py so both halves come from one
// source: seed_e2e stores the COSE public keys and the generated file carries
// the private keys, allowlisted by exact literal in .gitleaks.toml.

import { E2E_PASSKEYS_GENERATED } from './e2e-passkeys.generated';

export interface SeededPasskey {
  /** Base64url credential id. */
  id: string;
  /** Base64url user handle: the seeded user's id as the backend encodes it. */
  userHandle: string;
  /** Base64url PKCS#8 (DER) private key. */
  privateKey: string;
  /** Base64url SPKI (DER) public key, the value seed_e2e stores. */
  publicKey: string;
}

export const E2E_PASSKEYS: Readonly<Record<string, SeededPasskey>> = E2E_PASSKEYS_GENERATED;

export const E2E_RP_ID = process.env.E2E_RP_ID ?? 'localhost';
export const BACKEND_URL = process.env.E2E_BACKEND_URL ?? `http://localhost:${process.env.E2E_BACKEND_PORT ?? '8000'}`;

// The seeded logins (apps/shared/e2e_seed.py): one per system role in tenant
// A, the admin of tenant B, the one user awaiting enrolment, and the logins a
// single journey spends in a way the UI cannot undo (`reserved_for` in
// apps/shared/e2e_logins.py). Only the journey named beside a reserved login
// may use it (playbook 8.3 rule 4).
export const LOGINS = {
  admin: 'admin@example-bank.test',
  complianceOfficer: 'compliance_officer@example-bank.test',
  owner: 'owner@example-bank.test',
  approver: 'approver@example-bank.test',
  contributor: 'contributor@example-bank.test',
  reader: 'reader@example-bank.test',
  auditor: 'auditor@example-bank.test',
  anna: 'anna@example-bank.test',
  secondBankAdmin: 'admin@second-bank.test',
  /** Platform staff, no tenant: the console signs in as these. */
  editor: 'editor@bleqq.test',
  /** The second library editor, so the console can keep four eyes on a proposal. */
  editor2: 'editor2@bleqq.test',
  platform: 'platform@bleqq.test',
  /** Reserved for ADM-S2: it re-issues this member's enrolment, which retires their passkeys. */
  reissue: 'reissue@example-bank.test',
  /** AGT-S10 (J-4): creates a platform agent key through the console. Not reserved: the key is revocable. */
  agentKeys: 'agent-keys@bleqq.test',
  /** The one login whose own `locale` is Swedish (WAT-S2); read-only, so not reserved. */
  readerSv: 'reader-sv@example-bank.test',
  /** Reserved for I18N-S3: it switches this member's own interface language, which every session of theirs follows. */
  language: 'language@example-bank.test',
} as const;

export const ANNA_INVITE_TOKEN = 'e2e-invite-anna';
export const E2E_FIXED_CODE = '123456';

export async function installAuthenticator(context: BrowserContext): Promise<void> {
  await context.credentials.install();
}

export async function seedPasskey(context: BrowserContext, passkey: SeededPasskey, rpId: string = E2E_RP_ID): Promise<void> {
  await context.credentials.create(rpId, {
    id: passkey.id,
    userHandle: passkey.userHandle,
    privateKey: passkey.privateKey,
    publicKey: passkey.publicKey,
  });
}

export async function seedPasskeyFor(context: BrowserContext, login: string, rpId: string = E2E_RP_ID): Promise<SeededPasskey> {
  const passkey = E2E_PASSKEYS[login];
  if (passkey === undefined) {
    throw new Error(`passkeys: no fixed credential for "${login}". Add it to the backend roster (apps/shared/e2e_logins.py) and re-run generate_e2e_passkeys.py.`);
  }
  await installAuthenticator(context);
  // One login per authenticator: a discoverable ceremony answers with the
  // first credential it holds, so a key seeded earlier in this context
  // (a journey that signs in as two people) must go first.
  for (const held of await context.credentials.get({ rpId })) {
    if (held.id !== passkey.id) await context.credentials.delete(held.id);
  }
  await seedPasskey(context, passkey, rpId);
  return passkey;
}

// A fresh browser context holds no refresh cookie, so the client's one
// cold-load refresh answers 401 before the first screen. Every journey
// declares it once, here.
export function allowFreshContext(apiGuard: ApiGuard): void {
  apiGuard.allow(/\/api\/v1\/auth\/refresh$/, 401, 'no refresh cookie on a fresh browser context');
}

// The real ceremony on /sign-in: the seeded key answers the discoverable
// request and the shell appears. The shell renders only for a signed-in
// person, and exactly one "Main" navigation is visible at every width: the
// rail from 1024 px, the tab bar below it (design/system/navigation.md 11).
export async function signInAs(page: Page, login: string): Promise<SeededPasskey> {
  const passkey = await seedPasskeyFor(page.context(), login);
  await page.goto('/sign-in');
  await page.getByRole('button', { name: 'Sign in with a passkey' }).click();
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible({ timeout: 15_000 });
  return passkey;
}

/** Below 1024 px: opens the More sheet from the tab bar and returns it. */
export async function openMore(page: Page): Promise<Locator> {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'More' }).click();
  const sheet = page.getByRole('dialog', { name: 'More' });
  await expect(sheet).toBeVisible();
  return sheet;
}

/** The quiet Restricted screen, distinct from Next's own route announcer (also role=alert). */
export function restrictedScreen(page: Page) {
  return page.getByRole('alert').filter({ hasText: 'This page is not available to you' });
}

export async function signOut(page: Page): Promise<void> {
  // The width decides, as COMPACT_QUERY does: below 1024 px the account lives
  // in the More sheet; from 1024 px in the rail's account menu (open the
  // account row first, then choose the menu item). [data-who-panel] marks the
  // rail's row only, so journeys that read it run at desktop width.
  if ((page.viewportSize()?.width ?? 1280) < 1024) {
    await openMore(page);
    await page.getByRole('dialog', { name: 'More' }).getByRole('button', { name: 'Sign out' }).click();
  } else {
    await page.locator('[data-who-panel]').getByRole('button', { name: /, account menu$/ }).click();
    await page.getByRole('menuitem', { name: 'Sign out' }).click();
  }
  await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
}

// One-off helper to mint a fixed credential for a new seeded login: run it
// in a spec, copy the returned object into the backend seed's key list.
export async function generatePasskey(context: BrowserContext, rpId: string = E2E_RP_ID): Promise<SeededPasskey> {
  await installAuthenticator(context);
  const created = await context.credentials.create(rpId);
  return { id: created.id, userHandle: created.userHandle, privateKey: created.privateKey, publicKey: created.publicKey };
}

export interface OutboxMessage {
  to: string;
  subject: string;
  body: string;
}

// The mock mailer's outbox, an E2E-only route (GET /api/v1/e2e/mail-outbox).
export async function mailOutbox(request: APIRequestContext): Promise<OutboxMessage[]> {
  const response = await request.get(`${BACKEND_URL}/api/v1/e2e/mail-outbox`);
  expect(response.ok(), `mail outbox answered ${response.status()}`).toBe(true);
  const body: unknown = await response.json();
  return Array.isArray(body) ? (body as OutboxMessage[]) : ((body as { items?: OutboxMessage[] }).items ?? []);
}

export function mailsTo(outbox: OutboxMessage[], address: string): OutboxMessage[] {
  return outbox.filter((m) => m.to.toLowerCase() === address.toLowerCase());
}

/** The invitation link for a token: in the fragment, never a path (security review F29). */
export function inviteLink(token: string): string {
  return `/invite#${token}`;
}

/** The `/invite#<token>` link in a mail body, or null. */
export function inviteLinkFrom(message: OutboxMessage): string | null {
  const token = /\/invite#([A-Za-z0-9_\-.~]+)/.exec(message.body)?.[1];
  return token === undefined ? null : inviteLink(token);
}
