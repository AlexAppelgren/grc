import axios, { type AxiosError } from 'axios';
import { afterEach, describe, expect, it } from 'vitest';

import { installDemoClock } from './clock';
import { DEMO_FRAME_NAME, isDemoFrame, isDemoFrameWindow } from './frame';
import committed from './recordings.json';
import { type DemoRecordings, patternOf, requestKey, shapeDifference, shapeOf, staleness } from './recordings';
import { createReplayAdapter, DEMO_ACCESS_TOKEN, DEMO_NOT_RECORDED_CODE, DEMO_READ_ONLY_CODE } from './replay';

const ID = '068cca19-1a10-4a1b-8146-27aa18679c1e';
const OTHER_ID = '2e05374e-7cb7-436c-8bde-ad62ec2a815c';
const TEMPLATES = ['/api/v1/changes', '/api/v1/changes/{change_id}', '/api/v1/search'];

function recordings(entries: DemoRecordings['entries']): DemoRecordings {
  return { recordedAt: '2026-09-16T10:00:00.000Z', entries };
}

function client(recorded: DemoRecordings) {
  return axios.create({ adapter: createReplayAdapter(async () => recorded) });
}

describe('demo recordings', () => {
  it('keys a request by method, path, sorted query and canonical body', () => {
    expect(requestKey('get', '/api/v1/changes?tab=new&limit=20')).toBe('GET /api/v1/changes?limit=20&tab=new');
    expect(requestKey('post', '/api/v1/search', '{"b":1,"a":{"d":2,"c":3}}')).toBe('POST /api/v1/search {"a":{"c":3,"d":2},"b":1}');
    expect(requestKey('post', '/api/v1/search', '{"ids":[{"b":1,"a":2}]}')).toBe('POST /api/v1/search {"ids":[{"a":2,"b":1}]}');
  });

  it('keeps a body that is not JSON as it is', () => {
    expect(requestKey('post', '/api/v1/search', 'plain words')).toBe('POST /api/v1/search plain words');
    expect(patternOf('POST /api/v1/search plain words', TEMPLATES)).toBe('POST /api/v1/search {}');
    expect(patternOf('POST /api/v1/search "text"', TEMPLATES)).toBe('POST /api/v1/search {}');
  });

  it('compares requests by the API path template, never by which record they asked for', () => {
    expect(patternOf(`GET /api/v1/changes/${ID}`, TEMPLATES)).toBe('GET /api/v1/changes/{change_id}');
    expect(patternOf('GET /api/v1/changes?limit=20&tab=new', TEMPLATES)).toBe('GET /api/v1/changes?limit&tab');
    expect(patternOf('POST /api/v1/search {"query":"x","limit":5}', TEMPLATES)).toBe('POST /api/v1/search {limit,query}');
    expect(patternOf('GET /api/v1/unpublished', TEMPLATES)).toBe('GET /api/v1/unpublished');
  });

  it('reads a shape without values, and lets null and an empty list match anything', () => {
    expect(shapeDifference(shapeOf({ a: 1, b: [{ c: 'x' }] }), shapeOf({ a: 2, b: [] }))).toBeNull();
    expect(shapeDifference(shapeOf({ a: null }), shapeOf({ a: 'text' }))).toBeNull();
    expect(shapeDifference(shapeOf({ a: 1 }), shapeOf({ a: 1, b: 2 }))).toBe('$.b: new, and not in the recording');
    expect(shapeDifference(shapeOf({ a: 1, b: 2 }), shapeOf({ a: 1 }))).toBe('$.b: no longer answered');
    expect(shapeDifference(shapeOf({ a: [{ b: 1 }] }), shapeOf({ a: [{ b: 'one' }] }))).toBe('$.a[].b: number became string');
    expect(shapeDifference(shapeOf({ a: [1] }), shapeOf({ a: { b: 1 } }))).toBe('$.a: a list became an object');
    // A list whose items differ in kind keeps the first kind it met.
    expect(shapeOf([{ a: 1 }, [2]])).toEqual({ list: { a: 'number' } });
    expect(shapeOf([[1], [2]])).toEqual({ list: { list: 'number' } });
    expect(shapeOf([{ a: 1 }, null])).toEqual({ list: { a: 'number' } });
  });

  it('is stale when a screen asks for something unrecorded or an answer changed shape, and not when only the data moved', () => {
    // Each vocabulary list has fields of its own: a list is held against its own recording.
    const lists = recordings([
      { key: 'GET /api/v1/vocab/a', status: 200, contentType: 'application/json', body: { extra: { ordinal: 1 } } },
      { key: 'GET /api/v1/vocab/b', status: 200, contentType: 'application/json', body: { extra: { colour: 'x' } } },
    ]);
    expect(staleness(lists, recordings([lists.entries[1]!]), ['/api/v1/vocab/{list_name}'])).toEqual([]);
    const recorded = recordings([{ key: `GET /api/v1/changes/${ID}`, status: 200, contentType: 'application/json', body: { title: 'A', urgency: null } }]);
    const moved = recordings([{ key: `GET /api/v1/changes/${OTHER_ID}`, status: 200, contentType: 'application/json', body: { title: 'B', urgency: 'act_now' } }]);
    expect(staleness(recorded, moved, TEMPLATES)).toEqual([]);

    const reshaped = recordings([{ key: `GET /api/v1/changes/${OTHER_ID}`, status: 200, contentType: 'application/json', body: { heading: 'B', urgency: null } }]);
    expect(staleness(recorded, reshaped, TEMPLATES)).toEqual(['GET /api/v1/changes/{change_id} (200): $.title: no longer answered']);

    const unrecorded = recordings([{ key: 'GET /api/v1/changes?tab=new', status: 200, contentType: 'application/json', body: [] }]);
    const refused = recordings([{ key: `GET /api/v1/changes/${OTHER_ID}`, status: 404, contentType: 'application/problem+json', body: { code: 'not_found' } }]);
    expect(staleness(recorded, refused, TEMPLATES)).toEqual(['GET /api/v1/changes/{change_id} (404): not recorded']);
    expect(staleness(recorded, unrecorded, TEMPLATES)).toEqual(['GET /api/v1/changes?tab (200): not recorded']);
  });
});

describe('the committed recordings', () => {
  const recorded = committed as unknown as DemoRecordings;
  const text = JSON.stringify(recorded);

  it('hold no session, key or personal-settings answer, and no fixture marks', () => {
    for (const { key } of recorded.entries) expect(key).not.toMatch(/\/api\/v1\/(auth|api-keys|agent-keys|calendar-feeds|me\/)/);
    expect(text).not.toMatch(/"(accessToken|refreshToken|token|secret)":/);
    expect(text).not.toContain('(E2E)');
  });

  it('carry no grant that opens administration', () => {
    const me = recorded.entries.find((entry) => entry.key === 'GET /api/v1/me');
    expect((me?.body as { permissions: string[] } | undefined)?.permissions).not.toContain('audit.read');
  });
});

describe('the demo replay', () => {
  const recorded = recordings([
    { key: 'GET /api/v1/changes?limit=20&tab=new', status: 200, contentType: 'application/json', body: { items: [{ id: ID }] } },
    { key: 'POST /api/v1/search {"query":"research"}', status: 200, contentType: 'application/json', body: { results: 1 } },
    { key: 'POST /api/v1/ask {"question":"q"}', status: 200, contentType: 'text/event-stream', body: 'event: done\ndata: {}\n\n' },
  ]);

  it('answers a recorded request, with the query in any order and a filter it never saw', async () => {
    const api = client(recorded);
    expect((await api.get('/api/v1/changes', { params: { tab: 'new', limit: 20 } })).data).toEqual({ items: [{ id: ID }] });
    expect((await api.get('/api/v1/changes?tab=closed')).data).toEqual({ items: [{ id: ID }] });
    expect((await api.post('/api/v1/search', { query: 'research' })).data).toEqual({ results: 1 });
  });

  it('grants itself a session and ends it without a server', async () => {
    const api = client(recorded);
    expect((await api.post('/api/v1/auth/refresh')).data).toEqual({ accessToken: DEMO_ACCESS_TOKEN });
    expect((await api.post('/api/v1/auth/sign-out')).status).toBe(204);
  });

  it('refuses an unrecorded write, and says an unrecorded page has no sample data', async () => {
    const api = client(recorded);
    const write = await api.patch(`/api/v1/changes/${ID}`, { status: 'closed' }).catch((error: AxiosError) => error);
    expect((write as AxiosError).response?.status).toBe(409);
    expect((write as AxiosError).response?.data).toMatchObject({ code: DEMO_READ_ONLY_CODE, detail: 'This is a demo, so nothing you change here is saved.' });
    const read = await api.get(`/api/v1/changes/${ID}`).catch((error: AxiosError) => error);
    expect((read as AxiosError).response?.status).toBe(404);
    expect((read as AxiosError).response?.data).toMatchObject({ code: DEMO_NOT_RECORDED_CODE });
  });

  it('fails a recorded server error the way axios fails one', async () => {
    const api = client(recordings([{ key: 'GET /api/v1/home', status: 500, contentType: 'application/problem+json', body: { code: 'server_error' } }]));
    const error = (await api.get('/api/v1/home').catch((failure: AxiosError) => failure)) as AxiosError;
    expect(error.code).toBe('ERR_BAD_RESPONSE');
    expect(error.response?.status).toBe(500);
  });

  it('streams a recorded answer to a caller that asks for a stream', async () => {
    const api = client(recorded);
    const response = await api.post<ReadableStream<Uint8Array>>('/api/v1/ask', { question: 'q' }, { responseType: 'stream' });
    const { value } = await response.data.getReader().read();
    expect(new TextDecoder().decode(value)).toBe('event: done\ndata: {}\n\n');
  });

  it('hands out copies, so a screen cannot change the recording under the next one', async () => {
    const api = client(recorded);
    const first = await api.get<{ items: { id: string }[] }>('/api/v1/changes?limit=20&tab=new');
    first.data.items.length = 0;
    expect((await api.get('/api/v1/changes?limit=20&tab=new')).data).toEqual({ items: [{ id: ID }] });
  });
});

describe('demo mode', () => {
  const RealDate = Date;
  afterEach(() => {
    globalThis.Date = RealDate;
  });

  it('is off in a window that is not the demo frame', () => {
    expect(isDemoFrame()).toBe(false);
  });

  it('is on only in a frame of that name whose parent is this same origin', () => {
    const top = {};
    const here = { origin: 'https://bleqq.example' };
    const frame = (name: string, parent: () => string) => ({
      name,
      self: {},
      top,
      location: here,
      parent: {
        get location() {
          return { origin: parent() };
        },
      },
    });
    expect(isDemoFrameWindow(frame(DEMO_FRAME_NAME, () => here.origin))).toBe(true);
    expect(isDemoFrameWindow(frame('other', () => here.origin))).toBe(false);
    expect(isDemoFrameWindow({ ...frame(DEMO_FRAME_NAME, () => here.origin), self: top })).toBe(false);
    const crossOrigin = () => {
      throw new DOMException('Blocked a frame from accessing a cross-origin frame.', 'SecurityError');
    };
    expect(isDemoFrameWindow(frame(DEMO_FRAME_NAME, crossOrigin))).toBe(false);
  });

  it('keeps the real clock when the recording has no readable date', () => {
    installDemoClock('not a date');
    expect(Date).toBe(RealDate);
  });

  it('reads the recording day as today, while dates passed in stay what they are', () => {
    installDemoClock('2026-09-16T10:00:00.000Z');
    expect(Math.abs(Date.now() - RealDate.parse('2026-09-16T10:00:00.000Z'))).toBeLessThan(1_000);
    expect(new Date().toISOString().slice(0, 10)).toBe('2026-09-16');
    expect(new Date('2017-02-01T00:00:00.000Z').toISOString()).toBe('2017-02-01T00:00:00.000Z');
    expect(new Date(2020, 0, 1).getFullYear()).toBe(2020);
  });
});
