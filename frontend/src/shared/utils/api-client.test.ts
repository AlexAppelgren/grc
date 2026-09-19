import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  api,
  ensureColdLoadRefresh,
  isSessionBootstrapPath,
  isStepUpRequired,
  isWrite,
  newRequestId,
  pathOf,
  REFRESH_PATH,
  refreshSession,
  resetApiClientForTests,
  setStepUpHandler,
  SIGN_OUT_PATH,
  signOut,
  STEP_UP_REQUIRED_CODE,
  tokenStore,
} from './api-client';

// The adapter replaces the network: each test scripts what the server
// answers per call, and the test reads what the client sent.

interface Sent {
  method: string;
  path: string;
  headers: Record<string, string | undefined>;
}

function respond(config: InternalAxiosRequestConfig, status: number, data: unknown): AxiosResponse {
  return { data, status, statusText: String(status), headers: {}, config };
}

function install(script: (sent: Sent, index: number) => { status: number; data?: unknown }): Sent[] {
  const sent: Sent[] = [];
  const adapter: AxiosAdapter = async (config) => {
    const record: Sent = {
      method: (config.method ?? 'get').toLowerCase(),
      path: pathOf(config),
      headers: {
        authorization: config.headers.get('Authorization') as string | undefined,
        requestId: config.headers.get('X-Request-ID') as string | undefined,
        ifMatch: config.headers.get('If-Match') as string | undefined,
      },
    };
    sent.push(record);
    const answer = script(record, sent.length - 1);
    const response = respond(config, answer.status, answer.data ?? {});
    if (answer.status >= 400) {
      const { AxiosError } = await import('axios');
      throw new AxiosError(`status ${answer.status}`, String(answer.status), config, undefined, response);
    }
    return response;
  };
  api.defaults.adapter = adapter;
  return sent;
}

/** The server never answered: an axios error with no response, as a dropped connection makes. */
function installUnreachable(): Sent[] {
  const sent: Sent[] = [];
  const adapter: AxiosAdapter = async (config) => {
    sent.push({ method: (config.method ?? 'get').toLowerCase(), path: pathOf(config), headers: {} });
    const { AxiosError } = await import('axios');
    throw new AxiosError('Network Error', AxiosError.ERR_NETWORK, config, {});
  };
  api.defaults.adapter = adapter;
  return sent;
}

describe('api-client', () => {
  beforeEach(() => {
    resetApiClientForTests();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('classifies bootstrap paths and write methods', () => {
    expect(isSessionBootstrapPath(REFRESH_PATH)).toBe(true);
    expect(isSessionBootstrapPath('/api/v1/auth/invitations/abc/open')).toBe(true);
    expect(isSessionBootstrapPath('/api/v1/auth/invitations/verify')).toBe(true);
    expect(isSessionBootstrapPath('/api/v1/auth/passkeys/authenticate/options')).toBe(true);
    expect(isSessionBootstrapPath('/api/v1/auth/passkeys/authenticate/verify')).toBe(true);
    expect(isSessionBootstrapPath('/api/v1/auth/code/request')).toBe(true);
    expect(isSessionBootstrapPath('/api/v1/auth/code/verify')).toBe(true);
    // Registration runs under the enrolment or full session and carries its token.
    expect(isSessionBootstrapPath('/api/v1/auth/passkeys/register/options')).toBe(false);
    expect(isSessionBootstrapPath('/api/v1/auth/step-up/options')).toBe(false);
    expect(isSessionBootstrapPath('/api/v1/watch/changes')).toBe(false);
    expect(isWrite('POST')).toBe(true);
    expect(isWrite('patch')).toBe(true);
    expect(isWrite(undefined)).toBe(false);
    expect(pathOf({ url: 'https://api.example/api/v1/x?y=1' })).toBe('/api/v1/x');
    expect(pathOf({ url: '/api/v1/x', baseURL: 'http://localhost:8000' })).toBe('/api/v1/x');
    expect(newRequestId()).not.toBe(newRequestId());
  });

  it('falls back to a readable request id without crypto.randomUUID', () => {
    const original = globalThis.crypto.randomUUID;
    Object.defineProperty(globalThis.crypto, 'randomUUID', { value: undefined, configurable: true });
    try {
      expect(newRequestId()).toMatch(/^req-/);
    } finally {
      Object.defineProperty(globalThis.crypto, 'randomUUID', { value: original, configurable: true });
    }
  });

  it('refreshes once on cold load, then sends the bearer and a request id', async () => {
    const sent = install((s) => (s.path === REFRESH_PATH ? { status: 200, data: { accessToken: 'tok-1' } } : { status: 200, data: { ok: true } }));
    const response = await api.get('/api/v1/watch/changes');
    expect(response.data).toEqual({ ok: true });
    expect(sent.map((s) => s.path)).toEqual([REFRESH_PATH, '/api/v1/watch/changes']);
    expect(sent[0]?.headers.authorization).toBeUndefined();
    expect(sent[1]?.headers.authorization).toBe('Bearer tok-1');
    expect(sent[1]?.headers.requestId).toBeTruthy();
    expect(sent[0]?.headers.requestId).not.toBe(sent[1]?.headers.requestId);
    // A second request does not refresh again.
    await api.get('/api/v1/watch/changes');
    expect(sent.filter((s) => s.path === REFRESH_PATH)).toHaveLength(1);
  });

  it('never sends a bearer on session-bootstrap paths and does not refresh for them', async () => {
    tokenStore.set('stale');
    const sent = install(() => ({ status: 401 }));
    await expect(api.post('/api/v1/auth/passkeys/authenticate/options', {})).rejects.toBeTruthy();
    expect(sent).toHaveLength(1);
    expect(sent[0]?.headers.authorization).toBeUndefined();
  });

  it('retries once after a 401 through one shared refresh', async () => {
    tokenStore.set('old');
    const sent = install((s) => {
      if (s.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'new' } };
      return s.headers.authorization === 'Bearer new' ? { status: 200, data: { fresh: true } } : { status: 401 };
    });
    const [a, b] = await Promise.all([api.get('/api/v1/a'), api.get('/api/v1/b')]);
    expect(a.data).toEqual({ fresh: true });
    expect(b.data).toEqual({ fresh: true });
    expect(sent.filter((s) => s.path === REFRESH_PATH)).toHaveLength(1);
    expect(tokenStore.get()).toBe('new');
  });

  it('gives up when the refresh fails and clears the token', async () => {
    tokenStore.set('old');
    const sent = install(() => ({ status: 401 }));
    await expect(api.get('/api/v1/a')).rejects.toBeTruthy();
    expect(sent.map((s) => s.path)).toEqual(['/api/v1/a', REFRESH_PATH]);
    expect(tokenStore.get()).toBeNull();
  });

  it('does not retry a request that already retried', async () => {
    tokenStore.set('old');
    const sent = install((s) => (s.path === REFRESH_PATH ? { status: 200, data: { accessToken: 'new' } } : { status: 401 }));
    await expect(api.get('/api/v1/a')).rejects.toBeTruthy();
    expect(sent.map((s) => s.path)).toEqual(['/api/v1/a', REFRESH_PATH, '/api/v1/a']);
  });

  it('passes other errors through untouched', async () => {
    tokenStore.set('tok');
    install(() => ({ status: 500 }));
    await expect(api.get('/api/v1/a')).rejects.toMatchObject({ response: { status: 500 } });
  });

  it('sends If-Match on writes when the caller passes a version, never on reads', async () => {
    tokenStore.set('tok');
    const sent = install(() => ({ status: 200, data: {} }));
    await api.patch('/api/v1/obligations/1', { x: 1 }, { version: 7 });
    await api.get('/api/v1/obligations/1', { version: 7 });
    await api.post('/api/v1/obligations', { x: 1 });
    expect(sent[0]?.headers.ifMatch).toBe('"7"');
    expect(sent[1]?.headers.ifMatch).toBeUndefined();
    expect(sent[2]?.headers.ifMatch).toBeUndefined();
  });

  it('refreshSession is one-flight', async () => {
    const sent = install(() => ({ status: 200, data: { accessToken: 'x' } }));
    const [a, b] = await Promise.all([refreshSession(), refreshSession()]);
    expect(a).toEqual({ token: 'x', outcome: 'refreshed', error: null });
    expect(b.token).toBe('x');
    expect(sent).toHaveLength(1);
  });

  it('ensureColdLoadRefresh refreshes once and reports the token, or null for a visitor', async () => {
    const sent = install(() => ({ status: 401 }));
    expect((await ensureColdLoadRefresh()).token).toBeNull();
    expect((await ensureColdLoadRefresh()).token).toBeNull();
    expect(sent.map((s) => s.path)).toEqual([REFRESH_PATH]);
    tokenStore.set('later');
    expect(await ensureColdLoadRefresh()).toEqual({ token: 'later', outcome: 'refreshed', error: null });
  });

  // Chunk 1 review, security item 2: a flaky network used to read as a
  // sign-out, which threw people back to /sign-in and lost their work.
  it('treats a 401 from the refresh as signed out and forgets the token', async () => {
    tokenStore.set('stale');
    install(() => ({ status: 401, data: { code: 'session_expired' } }));
    const result = await refreshSession();
    expect(result).toEqual({ token: null, outcome: 'signed-out', error: null });
    expect(tokenStore.get()).toBeNull();
  });

  it('treats a refresh the server never answered as a connection state, keeping the token', async () => {
    tokenStore.set('held');
    installUnreachable();
    const result = await refreshSession();
    expect(result.outcome).toBe('unavailable');
    expect(result.token).toBe('held');
    expect(result.error).toBeTruthy();
    expect(tokenStore.get()).toBe('held');
  });

  it('treats a refresh the server failed to serve as a connection state too: only 401 signs out', async () => {
    tokenStore.set('held');
    for (const status of [500, 502, 503, 504]) {
      install(() => ({ status }));
      expect((await refreshSession()).outcome).toBe('unavailable');
      expect(tokenStore.get()).toBe('held');
    }
  });

  it('does not count an unreachable cold-load refresh, so the next call tries again', async () => {
    const offline = installUnreachable();
    expect((await ensureColdLoadRefresh()).outcome).toBe('unavailable');
    expect(offline).toHaveLength(1);
    const sent = install(() => ({ status: 200, data: { accessToken: 'back' } }));
    expect((await ensureColdLoadRefresh()).token).toBe('back');
    expect(sent.map((s) => s.path)).toEqual([REFRESH_PATH]);
  });

  it('does not retry a 401 request when the refresh could not reach the server', async () => {
    tokenStore.set('tok');
    let calls = 0;
    const adapterSent: string[] = [];
    api.defaults.adapter = async (config) => {
      calls += 1;
      adapterSent.push(pathOf(config));
      const { AxiosError } = await import('axios');
      if (pathOf(config) === REFRESH_PATH) throw new AxiosError('Network Error', AxiosError.ERR_NETWORK, config, {});
      throw new AxiosError('status 401', '401', config, undefined, respond(config, 401, {}));
    };
    await expect(api.get('/api/v1/watch/changes')).rejects.toMatchObject({ response: { status: 401 } });
    expect(adapterSent).toEqual(['/api/v1/watch/changes', REFRESH_PATH]);
    expect(calls).toBe(2);
    expect(tokenStore.get()).toBe('tok');
  });

  it('opens the step-up ceremony on 403 step_up_required and retries once when it succeeds', async () => {
    tokenStore.set('tok');
    let stepped = false;
    setStepUpHandler(async () => {
      stepped = true;
      return true;
    });
    const sent = install(() => (stepped ? { status: 202, data: {} } : { status: 403, data: { code: STEP_UP_REQUIRED_CODE, detail: 'Confirm first' } }));
    const response = await api.post('/api/v1/tenant/members/u1/reissue-enrolment');
    expect(response.status).toBe(202);
    expect(sent.map((s) => s.path)).toEqual(['/api/v1/tenant/members/u1/reissue-enrolment', '/api/v1/tenant/members/u1/reissue-enrolment']);
  });

  it('gives up when the person cancels the step-up, and never retries twice', async () => {
    tokenStore.set('tok');
    let calls = 0;
    setStepUpHandler(async () => {
      calls += 1;
      return calls > 1;
    });
    const sent = install(() => ({ status: 403, data: { code: STEP_UP_REQUIRED_CODE } }));
    await expect(api.post('/api/v1/tenant/api-keys', {})).rejects.toMatchObject({ response: { status: 403 } });
    expect(sent).toHaveLength(1);
    await expect(api.post('/api/v1/tenant/api-keys', {})).rejects.toMatchObject({ response: { status: 403 } });
    expect(sent).toHaveLength(3);
    expect(calls).toBe(2);
  });

  it('leaves other 403s and a missing handler alone', async () => {
    tokenStore.set('tok');
    const sent = install(() => ({ status: 403, data: { code: 'permission_denied' } }));
    await expect(api.get('/api/v1/tenant/members')).rejects.toBeTruthy();
    setStepUpHandler(async () => true);
    await expect(api.get('/api/v1/tenant/members')).rejects.toBeTruthy();
    setStepUpHandler(null);
    install(() => ({ status: 403, data: { code: STEP_UP_REQUIRED_CODE } }));
    await expect(api.get('/api/v1/tenant/members')).rejects.toBeTruthy();
    expect(sent).toHaveLength(2);
    const config = { headers: {} } as InternalAxiosRequestConfig;
    const { AxiosError } = await import('axios');
    expect(isStepUpRequired(new AxiosError('x', '403', config, undefined, respond(config, 403, 'text')))).toBe(false);
  });

  it('signOut posts to the server, forgets the token and skips the next cold-load refresh', async () => {
    tokenStore.set('tok');
    const sent = install(() => ({ status: 204 }));
    await signOut();
    expect(sent.map((s) => [s.method, s.path])).toEqual([['post', SIGN_OUT_PATH]]);
    expect(sent[0]?.headers.authorization).toBe('Bearer tok');
    expect(tokenStore.get()).toBeNull();
    expect((await ensureColdLoadRefresh()).token).toBeNull();
    expect(sent).toHaveLength(1);
  });

  it('signOut forgets the token even when the server does not answer', async () => {
    tokenStore.set('tok');
    install(() => ({ status: 500 }));
    await expect(signOut()).rejects.toBeTruthy();
    expect(tokenStore.get()).toBeNull();
  });
});
