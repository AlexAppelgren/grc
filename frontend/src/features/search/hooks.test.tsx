import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { api, tokenStore } from '@/shared/utils/api-client';

import { framesOf, sseResponse, stubFetch } from './ask-testing';
import { searchKeys, useAsk, useRateAnswer, useSearchResults } from './hooks';

describe('search hooks', () => {
  it('asks nothing while there is no query yet', async () => {
    resetApiForTests();
    tokenStore.set('tok');
    const sent = installAdapter(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    const { wrapper } = queryWrapper();
    renderHook(() => useSearchResults(null), { wrapper });
    await waitFor(() => expect(sent).toHaveLength(0));
  });

  it('reads the results once a query is given', async () => {
    resetApiForTests();
    tokenStore.set('tok');
    const sent = installAdapter(() => ({ status: 200, data: { items: [{ id: 'h-1' }], asOf: '2026-09-20' } }));
    const { wrapper } = queryWrapper();
    const result = renderHook(() => useSearchResults({ q: 'FFFS 2017:2', limit: 20 }), { wrapper });
    await waitFor(() => expect(result.result.current.data?.items).toHaveLength(1));
    expect(sent[0]?.path).toBe('/api/v1/search');
    expect(sent[0]?.body).toEqual({ q: 'FFFS 2017:2', limit: 20 });
  });

  it('keys each request by its whole body, so a narrowed search re-reads', () => {
    expect(searchKeys.results({ q: 'a', limit: 20 })).not.toEqual(searchKeys.results({ q: 'b', limit: 20 }));
    expect(searchKeys.results({ q: 'a', limit: 20 })).toEqual(searchKeys.results({ q: 'a', limit: 20 }));
  });
});

const ANSWER = { id: 'ans-1', question: 'q', asOf: '2026-09-20', statements: [], citations: [], noAnswer: false, model: 'mock', aiGenerated: true, createdAt: '2026-09-20T09:00:00Z' };
const STATEMENT = { text: 'Costs are disclosed.', citationIndexes: [1] };

describe('useAsk', () => {
  function asking(): void {
    resetApiForTests();
    api.defaults.baseURL = 'http://app.test';
    tokenStore.set('tok');
  }

  afterEach(() => {
    api.defaults.baseURL = '';
    vi.unstubAllGlobals();
  });

  it('is idle until asked, then builds the answer statement by statement and closes on the answer', async () => {
    asking();
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const encoder = new TextEncoder();
    stubFetch(
      () =>
        new Response(
          new ReadableStream<Uint8Array>({
            async start(controller) {
              for (const frame of framesOf([{ event: 'start', id: 'ans-1' }, { event: 'statement', statement: STATEMENT }])) controller.enqueue(encoder.encode(frame));
              await held;
              for (const frame of framesOf([{ event: 'answer', answer: { ...ANSWER, statements: [STATEMENT] }, stopReason: 'max_tokens' }])) controller.enqueue(encoder.encode(frame));
              controller.close();
            },
          }),
          { status: 200 },
        ),
    );
    const { result } = renderHook(() => useAsk());
    expect(result.current.state).toEqual({ phase: 'idle' });

    act(() => result.current.ask({ question: 'q' }));
    await waitFor(() => expect(result.current.state).toEqual({ phase: 'streaming', id: 'ans-1', statements: [STATEMENT] }));

    release();
    await waitFor(() => expect(result.current.state).toEqual({ phase: 'answered', answer: { ...ANSWER, statements: [STATEMENT] }, stopReason: 'max_tokens' }));
  });

  it('ends on the problem a stream closed with', async () => {
    asking();
    stubFetch(() => sseResponse(framesOf([{ event: 'start', id: 'ans-1' }, { event: 'problem', code: 'model_unavailable', detail: 'Ask again.' }])));
    const { result } = renderHook(() => useAsk());
    act(() => result.current.ask({ question: 'q' }));
    await waitFor(() => expect(result.current.state).toEqual({ phase: 'problem', code: 'model_unavailable' }));
  });

  it('fails with the refusal when the question is refused before any stream', async () => {
    asking();
    stubFetch(() => new Response(JSON.stringify({ code: 'feature_off', detail: 'Off.' }), { status: 403 }));
    const { result } = renderHook(() => useAsk());
    act(() => result.current.ask({ question: 'q' }));
    await waitFor(() => expect(result.current.state.phase).toBe('failed'));
  });

  it('fails when the stream stops without saying how it ended', async () => {
    asking();
    stubFetch(() => sseResponse(framesOf([{ event: 'start', id: 'ans-1' }])));
    const { result } = renderHook(() => useAsk());
    act(() => result.current.ask({ question: 'q' }));
    await waitFor(() => expect(result.current.state.phase).toBe('failed'));
  });

  it('stops reading the stream it left when the reader leaves', async () => {
    asking();
    const signals: AbortSignal[] = [];
    stubFetch((request) => {
      signals.push(request.signal);
      return new Promise<Response>(() => undefined);
    });
    const { result, unmount } = renderHook(() => useAsk());
    act(() => result.current.ask({ question: 'q' }));
    await waitFor(() => expect(signals).toHaveLength(1));
    unmount();
    expect(signals[0]?.aborted).toBe(true);
  });
});

describe('useRateAnswer', () => {
  it('posts the verdict on the answer', async () => {
    resetApiForTests();
    tokenStore.set('tok');
    const sent = installAdapter(() => ({ status: 204 }));
    const { wrapper } = queryWrapper();
    const { result } = renderHook(() => useRateAnswer('ans-1'), { wrapper });
    await act(() => result.current.mutateAsync({ feedback: 'helpful', note: '' }));
    expect(sent[0]?.path).toBe('/api/v1/answers/ans-1/feedback');
    expect(sent[0]?.body).toEqual({ feedback: 'helpful', note: '' });
  });
});
