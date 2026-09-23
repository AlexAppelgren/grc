'use client';

import { useMutation, useQuery, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

import * as search from './api';
import type { SearchRequestBody } from './api';
import type { Answer, AnswerFeedbackBody, AnswerStatement, AskRequestBody, SearchResponse } from './types';

// One read, keyed on the whole request: a narrowed search is a different
// answer, never a trimmed one, exactly as the watch feed's filters are part
// of its own key.

export const searchKeys = {
  results: (body: SearchRequestBody) => ['search', body] as const,
};

/**
 * `body` is `null` until the reader has asked for something: a POST body is
 * required, an empty query is not a search, and a screen must never guess at
 * one (SRC-01).
 */
export function useSearchResults(body: SearchRequestBody | null): UseQueryResult<SearchResponse> {
  return useQuery({
    queryKey: searchKeys.results(body ?? { q: '', limit: 0 }),
    queryFn: () => search.runSearch(body as SearchRequestBody),
    enabled: body !== null,
  });
}

/**
 * Where an Ask is. `streaming` holds the statements so far; the citations
 * they point at arrive with the closing answer. `problem` is a stream that
 * ended with a `problem` event; `failed` is a refusal before the stream, or a
 * stream that stopped without saying how it ended.
 */
export type AskState =
  | { phase: 'idle' }
  | { phase: 'streaming'; id: string | null; statements: AnswerStatement[] }
  | { phase: 'answered'; answer: Answer; stopReason: string | null }
  | { phase: 'problem'; code: string }
  | { phase: 'failed'; error: unknown };

/**
 * One question at a time. Asking again, or leaving the screen, stops
 * reading the stream before, which the server logs as a call the reader
 * left (D-82). The question lives in the request alone: nothing here keeps,
 * stores or logs it.
 */
export function useAsk(): { state: AskState; ask: (body: AskRequestBody) => void } {
  const [state, setState] = useState<AskState>({ phase: 'idle' });
  const current = useRef<AbortController | null>(null);

  useEffect(() => () => current.current?.abort(), []);

  const ask = useCallback((body: AskRequestBody) => {
    current.current?.abort();
    const controller = new AbortController();
    current.current = controller;
    let ended: AskState | null = null;
    let statements: AnswerStatement[] = [];
    let id: string | null = null;
    const show = (next: AskState) => {
      if (!controller.signal.aborted) setState(next);
    };
    show({ phase: 'streaming', id, statements });
    search
      .askQuestion(
        body,
        (event) => {
          if (event.event === 'start') id = event.id;
          else if (event.event === 'statement') statements = [...statements, event.statement];
          else if (event.event === 'answer') ended = { phase: 'answered', answer: event.answer, stopReason: event.stopReason ?? null };
          else ended = { phase: 'problem', code: event.code };
          show(ended ?? { phase: 'streaming', id, statements });
        },
        controller.signal,
      )
      .then(() => {
        if (ended === null) show({ phase: 'failed', error: new Error('stream ended early') });
      })
      .catch((error: unknown) => show({ phase: 'failed', error }));
  }, []);

  return { state, ask };
}

/** A reader's verdict on one answer: helpful, or wrong with a reason. */
export function useRateAnswer(answerId: string): UseMutationResult<void, unknown, AnswerFeedbackBody> {
  return useMutation({ mutationFn: (body: AnswerFeedbackBody) => search.rateAnswer(answerId, body) });
}
