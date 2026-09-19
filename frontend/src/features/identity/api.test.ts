import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as identity from './api';

// Each wrapper hits its route with its method and body and returns `.data`.

const credential = { id: 'x', rawId: 'x', type: 'public-key', clientExtensionResults: {}, response: { clientDataJSON: 'a', authenticatorData: 'b', signature: 'c', userHandle: null } };

describe('identity api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('bootstrap routes carry no bearer', async () => {
    const sent = installAdapter(() => ({ status: 202, data: {} }));
    await identity.openInvitation('e2e/invite');
    await identity.requestCode({ email: 'anna@example-bank.test' });
    expect(sent.map((s) => [s.method, s.path, s.authorization])).toEqual([
      ['post', '/api/v1/auth/invitations/open', undefined],
      ['post', '/api/v1/auth/code/request', undefined],
    ]);
    // The token rides in the body, never a path (security review F29).
    expect(sent[0]?.body).toEqual({ token: 'e2e/invite' });
    expect(sent[1]?.body).toEqual({ email: 'anna@example-bank.test' });
  });

  it('verifies an invitation code with the token in the body, no address and no bearer', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { accessToken: 'enrol', sessionKind: 'enrolment', expiresIn: 600 } }));
    const tokens = await identity.verifyInvitationCode({ token: 'e2e-invite', code: '123456' });
    expect(tokens.accessToken).toBe('enrol');
    expect(sent[0]).toMatchObject({ method: 'post', path: '/api/v1/auth/invitations/verify', body: { token: 'e2e-invite', code: '123456' }, authorization: undefined });
  });

  it('verifies a code and returns the session tokens', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { accessToken: 'enrol', sessionKind: 'enrolment', expiresIn: 600 } }));
    const tokens = await identity.verifyCode({ email: 'a@b.c', code: '123456' });
    expect(tokens.sessionKind).toBe('enrolment');
    expect(sent[0]).toMatchObject({ method: 'post', path: '/api/v1/auth/code/verify', body: { email: 'a@b.c', code: '123456' }, authorization: undefined });
  });

  it('runs the registration routes under the session token', async () => {
    const sent = installAdapter((s) => (s.path.endsWith('/options') ? { status: 200, data: { challenge: 'Y2g' } } : { status: 201, data: { passkey: { id: 'p1' }, sessionKind: 'full' } }));
    expect(await identity.registerOptions()).toEqual({ challenge: 'Y2g' });
    const registered = await identity.registerVerify({ credential: { ...credential, response: { clientDataJSON: 'a', attestationObject: 'b' } } });
    expect(registered.passkey.id).toBe('p1');
    expect(sent.map((s) => [s.path, s.authorization])).toEqual([
      ['/api/v1/auth/passkeys/register/options', 'Bearer tok'],
      ['/api/v1/auth/passkeys/register/verify', 'Bearer tok'],
    ]);
    // No name is sent: the server names the passkey from the device (ID-04).
    expect(sent[1]?.body).not.toHaveProperty('nickname');
  });

  it('runs the sign-in routes without a bearer and the step-up routes with one', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.path.endsWith('/options') ? { challenge: 'Y2g' } : { accessToken: 'full', sessionKind: 'full', expiresIn: 600, assertionId: 'a1', expiresAt: 'x' } }));
    await identity.authenticateOptions();
    await identity.authenticateVerify({ credential });
    await identity.stepUpOptions();
    const stepUp = await identity.stepUpVerify({ credential });
    expect(stepUp.assertionId).toBe('a1');
    expect(sent.map((s) => [s.path, s.authorization])).toEqual([
      ['/api/v1/auth/passkeys/authenticate/options', undefined],
      ['/api/v1/auth/passkeys/authenticate/verify', undefined],
      ['/api/v1/auth/step-up/options', 'Bearer tok'],
      ['/api/v1/auth/step-up/verify', 'Bearer tok'],
    ]);
  });

  it('reads and updates me', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { user: { id: 'u1' } } }));
    expect((await identity.getMe()).user.id).toBe('u1');
    await identity.updateMe({ name: 'Anna' });
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/me'],
      ['patch', '/api/v1/me'],
    ]);
    expect(sent[1]?.body).toEqual({ name: 'Anna' });
  });

  it('lists, renames and removes passkeys; lists and revokes sessions', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: s.method === 'get' ? [] : { id: 'p1' } }));
    expect(await identity.listPasskeys()).toEqual([]);
    await identity.renamePasskey('p 1', { nickname: 'Phone' });
    await identity.removePasskey('p1');
    expect(await identity.listSessions()).toEqual([]);
    await identity.revokeSession('s1');
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/me/passkeys'],
      ['patch', '/api/v1/me/passkeys/p%201'],
      ['delete', '/api/v1/me/passkeys/p1'],
      ['get', '/api/v1/me/sessions'],
      ['delete', '/api/v1/me/sessions/s1'],
    ]);
    expect(sent[1]?.body).toEqual({ nickname: 'Phone' });
  });
});
