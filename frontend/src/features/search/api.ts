import { isAxiosError } from 'axios';

import { api } from '@/shared/utils/api-client';

import type { AnswerFeedbackBody, AskEvent, AskRequestBody, SearchRequestBody, SearchResponse } from './types';

export type { SearchRequestBody } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). `POST /search` is a
// read: it writes no audit row and needs no idempotency key, and it is a
// POST precisely so the reader's own words never travel in a URL or reach
// browser or server access logs (playbook 4.7). `POST /ask` is the same, and
// it answers a stream.

const SEARCH = '/api/v1/search';
const ASK = '/api/v1/ask';

export async function runSearch(body: SearchRequestBody): Promise<SearchResponse> {
  return (await api.post<SearchResponse>(SEARCH, body)).data;
}

/**
 * `POST /ask`, handing each event to `onEvent` as its frame arrives. The
 * stream goes through the one axios instance, so the bearer, refresh and
 * step-up interceptors apply, on its fetch adapter, the one that can hand
 * back the body as it arrives (`responseType: 'stream'`). A refusal comes
 * before the stream as a status with a problem body, which that adapter also
 * hands back as a stream; it is read here, so a screen branches on its
 * `code` as on any other call. Resolves when the stream ends.
 */
export async function askQuestion(body: AskRequestBody, onEvent: (event: AskEvent) => void, signal: AbortSignal): Promise<void> {
  let stream: ReadableStream<Uint8Array>;
  try {
    const response = await api.post<ReadableStream<Uint8Array>>(ASK, body, {
      adapter: 'fetch',
      responseType: 'stream',
      headers: { Accept: 'text/event-stream' },
      signal,
    });
    stream = response.data;
  } catch (error) {
    if (isAxiosError(error) && error.response !== undefined && isStream(error.response.data)) {
      error.response.data = parsed(await new Response(error.response.data).text());
    }
    throw error;
  }
  await readEvents(stream, onEvent);
}

export async function rateAnswer(answerId: string, body: AnswerFeedbackBody): Promise<void> {
  await api.post(`/api/v1/answers/${encodeURIComponent(answerId)}/feedback`, body);
}

// Every frame the server sends is one `data:` line and a blank line
// (`text/event-stream`); a frame may arrive split across reads.
async function readEvents(stream: ReadableStream<Uint8Array>, onEvent: (event: AskEvent) => void): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    const frames = (pending + decoder.decode(value, { stream: true })).split('\n\n');
    pending = frames.pop() ?? '';
    for (const frame of frames) {
      const data = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice('data:'.length).trimStart())
        .join('\n');
      if (data !== '') onEvent(JSON.parse(data) as AskEvent);
    }
  }
}

function isStream(value: unknown): value is ReadableStream<Uint8Array> {
  return typeof value === 'object' && value !== null && typeof (value as { getReader?: unknown }).getReader === 'function';
}

function parsed(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
