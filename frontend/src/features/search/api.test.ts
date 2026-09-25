import { isAxiosError } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { api, tokenStore } from '@/shared/utils/api-client';

import * as search from './api';
import { sseResponse, stubFetch } from './ask-testing';
import type { AskEvent } from './types';

// The search reads and Ask's stream: the route each posts to, the body it
// sends and the answer it hands back unchanged. Nothing here reshapes the
// server's answer, because the generated types are the screen's types.

describe('search api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('posts the query to POST /search and returns the ranked answer', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    const body: search.SearchRequestBody = { q: 'FFFS 2017:2', limit: 20 };
    const response = await search.runSearch(body);
    expect(response).toEqual({ items: [], asOf: '2026-09-20' });
    expect(sent[0]?.method).toBe('post');
    expect(sent[0]?.path).toBe('/api/v1/search');
    expect(sent[0]?.body).toEqual(body);
  });

  it('posts a verdict to POST /answers/{answerId}/feedback', async () => {
    const sent = installAdapter(() => ({ status: 204 }));
    await search.rateAnswer('ans-1', { feedback: 'wrong', note: 'Misses the exemption' });
    expect(sent[0]?.method).toBe('post');
    expect(sent[0]?.path).toBe('/api/v1/answers/ans-1/feedback');
    expect(sent[0]?.body).toEqual({ feedback: 'wrong', note: 'Misses the exemption' });
  });
});

describe('askQuestion', () => {
  beforeEach(() => {
    resetApiForTests();
    // The stream goes through the fetch adapter of the one instance, never a
    // test adapter, so the real interceptors and the real reader run here.
    // A browser resolves the relative route against the page; Node needs an
    // origin to resolve it against.
    api.defaults.baseURL = 'http://app.test';
    tokenStore.set('tok');
  });

  afterEach(() => {
    api.defaults.baseURL = '';
    vi.unstubAllGlobals();
  });

  it('streams through the one axios instance, with its bearer, and hands back every event in order', async () => {
    const events: AskEvent[] = [
      { event: 'start', id: 'ans-1' },
      { event: 'statement', statement: { text: 'Costs are disclosed.', citationIndexes: [1] } },
      {
        event: 'answer',
        stopReason: 'end_turn',
        answer: { id: 'ans-1', question: 'q', asOf: '2026-09-20', statements: [], citations: [], noAnswer: false, model: 'mock', aiGenerated: true, createdAt: '2026-09-20T09:00:00Z' },
      },
    ];
    // Frames split at awkward places, as a network delivers them.
    const wire = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
    const requests = stubFetch(() => sseResponse([wire.slice(0, 7), wire.slice(7, 60), wire.slice(60)]));

    const seen: AskEvent[] = [];
    await search.askQuestion({ question: 'What must we disclose?', asOf: '2026-09-20' }, (event) => seen.push(event), new AbortController().signal);

    expect(seen).toEqual(events);
    const request = requests[0];
    expect(request?.method).toBe('POST');
    expect(new URL(request?.url ?? '').pathname).toBe('/api/v1/ask');
    expect(request?.headers.get('Authorization')).toBe('Bearer tok');
    expect(request?.headers.get('Accept')).toBe('text/event-stream');
    expect(await request?.json()).toEqual({ question: 'What must we disclose?', asOf: '2026-09-20' });
  });

  it('reads a refusal before the stream as the problem body a screen branches on', async () => {
    stubFetch(() => new Response(JSON.stringify({ code: 'feature_off', detail: 'Switched off.', status: 403 }), { status: 403, headers: { 'Content-Type': 'application/problem+json' } }));

    const failure = await search.askQuestion({ question: 'q' }, () => undefined, new AbortController().signal).catch((error: unknown) => error);

    expect(isAxiosError(failure)).toBe(true);
    expect(isAxiosError(failure) ? failure.response?.data : null).toEqual({ code: 'feature_off', detail: 'Switched off.', status: 403 });
  });
});
