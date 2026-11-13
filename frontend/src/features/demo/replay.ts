import axios, { type AxiosAdapter, AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';

import { createT, defaultLocale } from '@/shared/i18n';
import { isWrite, REFRESH_PATH, SIGN_OUT_PATH } from '@/shared/utils/api-client';

import { type DemoRecording, type DemoRecordings, requestKey, withoutQuery } from './recordings';

// The demo's only way to answer a request. It never touches the network: an
// answer is a recording, a session the demo grants itself, or a refusal the
// screen renders like any other problem. Writes are refused unless the
// recorder captured that exact write (a search is a POST that changes nothing).

const t = createT(defaultLocale);

export const DEMO_ACCESS_TOKEN = 'demo';
export const DEMO_READ_ONLY_CODE = 'demo_read_only';
export const DEMO_NOT_RECORDED_CODE = 'demo_not_recorded';

interface Answer {
  status: number;
  contentType: string;
  body: unknown;
}

function problem(status: number, code: string, detail: string): Answer {
  return { status, contentType: 'application/problem+json', body: { type: 'about:blank', title: detail, status, code, detail } };
}

function streamOf(text: string): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
}

// A read the recorder never made may borrow the first recording of its path that is
// about the same thing (below) when it asks for that list under a filter the recorder
// never clicked: the screen still shows the kind of rows it asked for. A later page or
// a search may not, since the first page would read as their answer.
const SEARCH_TEXT = ['q', 'query', 'search'];

function mayBorrow(params: URLSearchParams): boolean {
  return Number(params.get('offset') ?? 0) === 0 && SEARCH_TEXT.every((name) => (params.get(name) ?? '') === '');
}

// What a read is about rather than how it filters: a record or a company by its id, a
// regulation by its key, a day or a language. A borrowed answer must be about the same,
// or a list would show another regulation's or another company's rows as its own.
const ABOUT = new Set(['instrument', 'subjectType', 'asOf', 'lang', 'company']);

function about(target: string): string {
  const params = new URL(target, 'http://demo.invalid').searchParams;
  return [...params.keys()]
    .filter((name) => ABOUT.has(name) || /Ids?$/.test(name))
    .sort()
    .map((name) => `${name}=${params.getAll(name).join(',')}`)
    .join('&');
}

/** Every recorded GET of each path, in file order, for a read that may borrow one. */
type Index = { byKey: ReadonlyMap<string, DemoRecording>; byPath: ReadonlyMap<string, readonly DemoRecording[]> };

function borrowed(key: string, url: URL, index: Index): DemoRecording | undefined {
  if (!mayBorrow(url.searchParams)) return undefined;
  const wanted = about(`${url.pathname}${url.search}`);
  return index.byPath.get(withoutQuery(key))?.find((entry) => about(entry.key.split(' ')[1] ?? '') === wanted);
}

function answerFor(config: InternalAxiosRequestConfig, index: Index): Answer {
  // axios has merged its defaults into the config by now: a method and a status check are always set.
  const method = String(config.method).toUpperCase();
  // The URL the browser would have asked for, params serialised the way axios does it.
  const url = new URL(axios.getUri(config), 'http://demo.invalid');
  if (url.pathname === REFRESH_PATH) return { status: 200, contentType: 'application/json', body: { accessToken: DEMO_ACCESS_TOKEN } };
  if (url.pathname === SIGN_OUT_PATH) return { status: 204, contentType: 'application/json', body: null };

  const key = requestKey(method, `${url.pathname}${url.search}`, isWrite(method) ? config.data : undefined);
  const recorded = index.byKey.get(key) ?? (isWrite(method) ? undefined : borrowed(key, url, index));
  if (recorded !== undefined) return { status: recorded.status, contentType: recorded.contentType, body: structuredClone(recorded.body) };
  return isWrite(method) ? problem(409, DEMO_READ_ONLY_CODE, t('public.demo.readOnly')) : problem(404, DEMO_NOT_RECORDED_CODE, t('public.demo.notRecorded'));
}

/** An axios adapter that answers from the recordings, loaded once on the first request. */
export function createReplayAdapter(load: () => Promise<DemoRecordings>): AxiosAdapter {
  let index: Promise<Index> | null = null;
  return async (config) => {
    index ??= load().then((recordings) => {
      const byKey = new Map<string, DemoRecording>();
      const byPath = new Map<string, DemoRecording[]>();
      for (const entry of recordings.entries) {
        byKey.set(entry.key, entry);
        // A GET also answers its own path with a filter the recorder never tried (borrowed).
        if (entry.key.startsWith('GET ')) byPath.set(withoutQuery(entry.key), [...(byPath.get(withoutQuery(entry.key)) ?? []), entry]);
      }
      return { byKey, byPath };
    });
    const answer = answerFor(config, await index);
    const streamed = config.responseType === 'stream' && typeof answer.body === 'string';
    const response: AxiosResponse = {
      data: streamed ? streamOf(answer.body as string) : answer.body,
      status: answer.status,
      statusText: '',
      headers: new AxiosHeaders({ 'content-type': answer.contentType }),
      config,
      request: null,
    };
    if (config.validateStatus?.(answer.status) !== false) return response;
    throw new AxiosError(
      `Request failed with status code ${answer.status}`,
      answer.status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
      config,
      null,
      response,
    );
  };
}
