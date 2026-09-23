import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, tokenStore } from '@/shared/utils/api-client';

import {
  sessionStatusOf,
  useAddPasskey,
  useFormatContext,
  useOpenInvitation,
  usePasskeys,
  useRegisterPasskey,
  useRemovePasskey,
  useRenamePasskey,
  useRequestCode,
  useRevokeSession,
  userLocaleOf,
  useSession,
  useSessions,
  useSetLanguage,
  useSignIn,
  useSignOut,
  useStepUp,
  useVerifyCode,
  useVerifyInvitationCode,
} from './hooks';
import type { Me } from './types';

// The hooks against the real query client and the one axios instance, with
// the network scripted per test and the browser's credentials stubbed.

const me: Me = {
  user: { id: 'u1', email: 'anna@example-bank.test', name: 'Anna', locale: 'sv' },
  tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Helsinki' },
  roles: [],
  permissions: ['watch.read'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
  counts: { triage: 0, proposals: 0, assignedToMe: 0 },
  lastVisitAt: null,
};

function stubCredentials() {
  const registration = {
    id: 'AQID',
    rawId: new Uint8Array([1, 2, 3]).buffer,
    type: 'public-key',
    authenticatorAttachment: 'platform',
    response: { clientDataJSON: new Uint8Array([1]).buffer, attestationObject: new Uint8Array([2]).buffer },
    getClientExtensionResults: () => ({}),
  };
  const assertion = {
    ...registration,
    response: { clientDataJSON: new Uint8Array([1]).buffer, authenticatorData: new Uint8Array([4]).buffer, signature: new Uint8Array([5]).buffer, userHandle: null },
  };
  vi.stubGlobal('navigator', { credentials: { create: vi.fn(async () => registration), get: vi.fn(async () => assertion) } });
}

describe('identity hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    stubCredentials();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('useSession: a visitor without a cookie is anonymous after one refresh and no GET /me', async () => {
    const sent = installAdapter(() => ({ status: 401 }));
    const { wrapper } = queryWrapper();
    const { result } = renderHook(() => useSession(), { wrapper });
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('anonymous'));
    expect(sent.map((s) => s.path)).toEqual([REFRESH_PATH]);
    expect(result.current.me).toBeNull();
  });

  it('useSession: a refresh cookie yields the person, enrolment when pending', async () => {
    let pending = true;
    installAdapter((s) => (s.path === REFRESH_PATH ? { status: 200, data: { accessToken: 'tok' } } : { status: 200, data: { ...me, enrolmentPending: pending } }));
    const { wrapper, queryClient } = queryWrapper();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('enrolment'));
    pending = false;
    await queryClient.invalidateQueries({ queryKey: ['me'] });
    await waitFor(() => expect(result.current.status).toBe('signed-in'));
    expect(result.current.me?.user.name).toBe('Anna');
    result.current.refetch();
  });

  it('useSession: a 401 from /me is anonymous and other failures are errors', async () => {
    tokenStore.set('stale');
    installAdapter((s) => ({ status: s.path === REFRESH_PATH ? 401 : 401 }));
    const { wrapper } = queryWrapper();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('anonymous'));
    expect(tokenStore.get()).toBeNull();

    resetApiForTests();
    tokenStore.set('tok');
    installAdapter(() => ({ status: 500 }));
    const second = renderHook(() => useSession(), { wrapper: queryWrapper().wrapper });
    await waitFor(() => expect(second.result.current.status).toBe('error'));
  });

  it('sessionStatusOf and userLocaleOf are pure', () => {
    expect(sessionStatusOf({ isPending: true, isError: false, data: undefined })).toBe('loading');
    expect(sessionStatusOf({ isPending: false, isError: true, data: undefined })).toBe('error');
    expect(sessionStatusOf({ isPending: false, isError: false, data: null })).toBe('anonymous');
    expect(sessionStatusOf({ isPending: false, isError: false, data: me })).toBe('signed-in');
    expect(sessionStatusOf({ isPending: false, isError: false, data: { ...me, enrolmentPending: true } })).toBe('enrolment');
    expect(userLocaleOf(me)).toBe('sv');
    expect(userLocaleOf({ ...me, user: { ...me.user, locale: 'fi' } })).toBe('en');
    expect(userLocaleOf(null)).toBe('en');
  });

  it('useFormatContext follows the user language and the tenant timezone', async () => {
    tokenStore.set('tok');
    installAdapter(() => ({ status: 200, data: me }));
    const { wrapper } = queryWrapper();
    const { result } = renderHook(() => useFormatContext(), { wrapper });
    await waitFor(() => expect(result.current.timeZone).toBe('Europe/Helsinki'));
    expect(result.current.locale).toBe('sv');
  });

  it('useSignIn runs options, the ceremony and verify, then stores the token', async () => {
    const sent = installAdapter((s) => (s.path.endsWith('/options') ? { status: 200, data: { challenge: 'Y2g', allowCredentials: [] } } : { status: 200, data: { accessToken: 'full', sessionKind: 'full', expiresIn: 600 } }));
    const { wrapper } = queryWrapper();
    const { result } = renderHook(() => useSignIn(), { wrapper });
    await result.current.mutateAsync();
    expect(tokenStore.get()).toBe('full');
    expect(sent.map((s) => s.path)).toEqual(['/api/v1/auth/passkeys/authenticate/options', '/api/v1/auth/passkeys/authenticate/verify']);
    expect(sent[1]?.body).toMatchObject({ credential: { id: 'AQID', response: { signature: 'BQ' } } });
  });

  it('useVerifyCode stores the enrolment token; useRequestCode and useOpenInvitation post', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { accessToken: 'enrol', sessionKind: 'enrolment', expiresIn: 600 } }));
    const { wrapper } = queryWrapper();
    const verify = renderHook(() => useVerifyCode(), { wrapper });
    await verify.result.current.mutateAsync({ email: 'a@b.c', code: '123456' });
    expect(tokenStore.get()).toBe('enrol');
    const request = renderHook(() => useRequestCode(), { wrapper });
    await request.result.current.mutateAsync('a@b.c');
    const open = renderHook(() => useOpenInvitation(), { wrapper });
    await open.result.current.mutateAsync('tok-1');
    expect(sent.map((s) => s.path)).toEqual(['/api/v1/auth/code/verify', '/api/v1/auth/code/request', '/api/v1/auth/invitations/open']);
    expect(sent[2]?.body).toEqual({ token: 'tok-1' });
  });

  it('useVerifyInvitationCode stores the enrolment token', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { accessToken: 'enrol-2', sessionKind: 'enrolment', expiresIn: 600 } }));
    const { wrapper } = queryWrapper();
    const verify = renderHook(() => useVerifyInvitationCode(), { wrapper });
    await verify.result.current.mutateAsync({ token: 'tok-1', code: '123456' });
    expect(tokenStore.get()).toBe('enrol-2');
    expect(sent.map((s) => [s.path, s.body])).toEqual([['/api/v1/auth/invitations/verify', { token: 'tok-1', code: '123456' }]]);
  });

  it('useRegisterPasskey upgrades the session when the answer carries a token; useAddPasskey does not', async () => {
    tokenStore.set('enrol');
    let withToken = true;
    const sent = installAdapter((s) => (s.path.endsWith('/options') ? { status: 200, data: { challenge: 'Y2g', rp: { name: 'x' }, user: { id: 'dQ', name: 'a', displayName: 'a' }, pubKeyCredParams: [] } } : { status: 201, data: { passkey: { id: 'p1' }, sessionKind: 'full', accessToken: withToken ? 'full' : null, expiresIn: withToken ? 600 : null } }));
    const { wrapper } = queryWrapper();
    const register = renderHook(() => useRegisterPasskey(), { wrapper });
    const registered = await register.result.current.mutateAsync();
    expect(registered.passkey.id).toBe('p1');
    expect(tokenStore.get()).toBe('full');
    expect(sent[1]?.body).toMatchObject({ credential: { response: { attestationObject: 'Ag' } } });
    // The server names the passkey from the device (ID-04); the ceremony sends no name.
    expect(sent[1]?.body).not.toHaveProperty('nickname');

    withToken = false;
    const add = renderHook(() => useAddPasskey(), { wrapper });
    await add.result.current.mutateAsync();
    expect(tokenStore.get()).toBe('full');
    expect(sent).toHaveLength(4);
  });

  it('useStepUp runs the assertion and posts it to step-up verify', async () => {
    tokenStore.set('tok');
    const sent = installAdapter((s) => (s.path.endsWith('/options') ? { status: 200, data: { challenge: 'Y2g' } } : { status: 200, data: { assertionId: 'a1', expiresAt: 'x' } }));
    const { wrapper } = queryWrapper();
    const { result } = renderHook(() => useStepUp(), { wrapper });
    expect((await result.current.mutateAsync()).assertionId).toBe('a1');
    expect(sent.map((s) => s.path)).toEqual(['/api/v1/auth/step-up/options', '/api/v1/auth/step-up/verify']);
  });

  it('useSignOut posts sign-out, clears the token and the cache', async () => {
    tokenStore.set('tok');
    const sent = installAdapter(() => ({ status: 204 }));
    const { wrapper, queryClient } = queryWrapper();
    queryClient.setQueryData(['me'], me);
    const { result } = renderHook(() => useSignOut(), { wrapper });
    await result.current.mutateAsync();
    expect(sent.map((s) => s.path)).toEqual(['/api/v1/auth/sign-out']);
    expect(tokenStore.get()).toBeNull();
    await waitFor(() => expect(queryClient.getQueryData(['me'])).toBeUndefined());
  });

  it('passkeys and sessions: list, rename, remove, revoke, with invalidation', async () => {
    tokenStore.set('tok');
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: s.method === 'get' ? [{ id: 'p1', current: true }] : { id: 'p1' } }));
    const { wrapper } = queryWrapper();
    const passkeys = renderHook(() => usePasskeys(), { wrapper });
    await waitFor(() => expect(passkeys.result.current.data).toHaveLength(1));
    const rename = renderHook(() => useRenamePasskey(), { wrapper });
    await rename.result.current.mutateAsync({ id: 'p1', nickname: 'Phone' });
    const remove = renderHook(() => useRemovePasskey(), { wrapper });
    await remove.result.current.mutateAsync('p1');
    const sessions = renderHook(() => useSessions(), { wrapper });
    await waitFor(() => expect(sessions.result.current.data).toHaveLength(1));
    const revoke = renderHook(() => useRevokeSession(), { wrapper });
    await revoke.result.current.mutateAsync('s1');
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/me/passkeys').length).toBeGreaterThanOrEqual(3));
    expect(sent.some((s) => s.method === 'patch' && s.path === '/api/v1/me/passkeys/p1')).toBe(true);
    expect(sent.some((s) => s.method === 'delete' && s.path === '/api/v1/me/sessions/s1')).toBe(true);
    const disabled = renderHook(() => usePasskeys(false), { wrapper: queryWrapper().wrapper });
    expect(disabled.result.current.fetchStatus).toBe('idle');
    const disabledSessions = renderHook(() => useSessions(false), { wrapper: queryWrapper().wrapper });
    expect(disabledSessions.result.current.fetchStatus).toBe('idle');
  });

  it('useSetLanguage saves the language on the person and refetches every answer, the session with it, in that language', async () => {
    tokenStore.set('tok');
    let locale = 'en';
    const sent = installAdapter((s) => {
      if (s.method === 'patch') locale = (s.body as { locale: string }).locale;
      if (s.path === '/api/v1/me/passkeys') return { status: 200, data: [{ id: 'p1', nickname: locale === 'sv' ? 'Telefon' : 'Phone' }] };
      return { status: 200, data: { ...me, user: { ...me.user, locale } } };
    });
    const { wrapper, queryClient } = queryWrapper();
    const session = renderHook(() => useSession(), { wrapper });
    const passkeys = renderHook(() => usePasskeys(), { wrapper });
    await waitFor(() => expect(userLocaleOf(session.result.current.me)).toBe('en'));
    await waitFor(() => expect(passkeys.result.current.data?.[0]?.nickname).toBe('Phone'));

    const setLanguage = renderHook(() => useSetLanguage(), { wrapper });
    await setLanguage.result.current.mutateAsync('sv');

    expect(sent.filter((s) => s.method === 'patch')).toEqual([expect.objectContaining({ path: '/api/v1/me', body: { locale: 'sv' } })]);
    // Settled only once every answer is back in the new language, so the switch never shows a mix.
    expect(userLocaleOf(queryClient.getQueryData<Me>(['me']) ?? null)).toBe('sv');
    expect(queryClient.getQueryData<{ nickname: string }[]>(['me', 'passkeys'])?.[0]?.nickname).toBe('Telefon');
    await waitFor(() => expect(userLocaleOf(session.result.current.me)).toBe('sv'));
  });
});
