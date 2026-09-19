import type { BrowserContext } from '@playwright/test';

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

// Fixed test credentials, one per seeded login. seed_e2e stores the public
// keys; the private keys below are test-only and allowlisted by exact
// literal in .gitleaks.toml. Empty until the backend's seed lands: generate
// with `generatePasskey()` once and paste both halves here and into the seed.
export const E2E_PASSKEYS: Readonly<Record<string, SeededPasskey>> = {};

export const E2E_RP_ID = process.env.E2E_RP_ID ?? 'localhost';

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
    throw new Error(`passkeys: no fixed credential for "${login}". Add it to E2E_PASSKEYS and to seed_e2e.`);
  }
  await installAuthenticator(context);
  await seedPasskey(context, passkey, rpId);
  return passkey;
}

// One-off helper to mint a fixed credential for a new seeded login: run it
// in a spec, copy the returned object into E2E_PASSKEYS and its publicKey
// and id into the backend seed.
export async function generatePasskey(context: BrowserContext, rpId: string = E2E_RP_ID): Promise<SeededPasskey> {
  await installAuthenticator(context);
  const created = await context.credentials.create(rpId);
  return { id: created.id, userHandle: created.userHandle, privateKey: created.privateKey, publicKey: created.publicKey };
}
