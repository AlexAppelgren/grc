import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api, isSessionBootstrapPath, isWrite, newRequestId, pathOf, REFRESH_PATH, refreshSession, resetApiClientForTests, tokenStore } from './api-client';

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

describe('api-client', () => {
  beforeEach(() => {
    resetApiClientForTests();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('classifies bootstrap paths and write methods', () => {
    expect(isSessionBootstrapPath(REFRESH_PATH)).toBe(true);
    expect(isSessionBootstrapPath('/api/v1/auth/invitations/abc')).toBe(true);
    expect(isSessionBootstrapPath('/api/v1/auth/passkeys/authenticate/begin')).toBe(true);
    expect(isSessionBootstrapPath('/api/v1/auth/code')).toBe(true);
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
    await expect(api.post('/api/v1/auth/passkeys/authenticate/begin', {})).rejects.toBeTruthy();
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
    expect(a).toBe('x');
    expect(b).toBe('x');
    expect(sent).toHaveLength(1);
  });
});
