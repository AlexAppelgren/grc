import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetApiForTests } from '@/shared/testing/api-adapter';
import { api, pathOf, tokenStore } from '@/shared/utils/api-client';

import * as cases from './api';

// Every case workflow operation: the route it calls, the method, what it
// sends and whether it carries `If-Match`. The version travels as `If-Match`
// on every write the contract checks it on, and on nothing else.

interface Call {
  method: string;
  path: string;
  ifMatch: string | null;
  data: unknown;
  responseType: string | undefined;
}

function record(answer: unknown = {}, status = 200): Call[] {
  const calls: Call[] = [];
  const adapter: AxiosAdapter = async (config) => {
    const header = config.headers.get('If-Match');
    calls.push({
      method: (config.method ?? 'get').toUpperCase(),
      path: pathOf(config),
      ifMatch: typeof header === 'string' ? header : null,
      data: config.data,
      responseType: config.responseType,
    });
    return { data: answer, status, statusText: String(status), headers: {}, config: config as InternalAxiosRequestConfig };
  };
  api.defaults.adapter = adapter;
  return calls;
}

const json = (call: Call | undefined) => (typeof call?.data === 'string' ? JSON.parse(call.data) : call?.data);

describe('cases api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('moves a case with its version as If-Match: triage, dismiss, restore, start, close', async () => {
    const calls = record({ id: 'case-1', status: 'assigned', version: 3 });
    expect((await cases.triageChange('c-1', { urgency: 'act_now', ownerId: 'u-1' }, 2)).version).toBe(3);
    await cases.dismissChange('c-1', { reasonKey: 'out_of_scope' }, 2);
    await cases.restoreChange('c-1', 5);
    await cases.startAssessment('c-1', 3);
    await cases.closeWithoutAction('c-1', { reasonKey: 'no_action', note: 'Covered by our 2025 policy.' }, 4);
    expect(calls.map((c) => [c.method, c.path, c.ifMatch])).toEqual([
      ['POST', '/api/v1/changes/c-1/triage', '"2"'],
      ['POST', '/api/v1/changes/c-1/dismiss', '"2"'],
      ['POST', '/api/v1/changes/c-1/restore', '"5"'],
      ['POST', '/api/v1/changes/c-1/assessment/start', '"3"'],
      ['POST', '/api/v1/changes/c-1/close', '"4"'],
    ]);
    expect(json(calls[0])).toEqual({ urgency: 'act_now', ownerId: 'u-1' });
    expect(json(calls[1])).toEqual({ reasonKey: 'out_of_scope' });
    expect(json(calls[4])).toEqual({ reasonKey: 'no_action', note: 'Covered by our 2025 policy.' });
  });

  it('saves the assessment with PUT and the case’s version', async () => {
    const calls = record({ id: 'case-1', version: 5 });
    const body = { applies: 'yes' as const, why: 'We pay for research.', whatMustChange: 'Criteria.', internalDeadline: null, effort: 'm', subStatus: null };
    await cases.saveAssessment('c-1', body, 4);
    expect([calls[0]?.method, calls[0]?.path, calls[0]?.ifMatch]).toEqual(['PUT', '/api/v1/changes/c-1/assessment', '"4"']);
    expect(json(calls[0])).toEqual(body);
  });

  it('lists, adds, edits and removes actions: the case’s version to add, the action’s own to change', async () => {
    const calls = record({ items: [], total: 0 });
    expect(await cases.listActions('c-1', { limit: 50 })).toEqual({ items: [], total: 0 });
    await cases.addAction('c-1', { title: 'Write the criteria', ownerId: 'u-1', dueDate: '2026-10-10' }, 6);
    await cases.updateAction('a-1', { done: true }, 2);
    await cases.deleteAction('a-1', 3);
    expect(calls.map((c) => [c.method, c.path, c.ifMatch])).toEqual([
      ['GET', '/api/v1/changes/c-1/actions', null],
      ['POST', '/api/v1/changes/c-1/actions', '"6"'],
      ['PATCH', '/api/v1/actions/a-1', '"2"'],
      ['DELETE', '/api/v1/actions/a-1', '"3"'],
    ]);
    expect(json(calls[2])).toEqual({ done: true });
  });

  it('attaches evidence as one multipart post with the bytes, and sends no version where none is checked', async () => {
    const calls = record({ evidence: { id: 'e-1', scanState: 'pending' } });
    const file = new Blob(['%PDF-1.7'], { type: 'application/pdf' });
    expect((await cases.addEvidence('c-1', { kind: 'file', name: 'criteria.pdf', file })).evidence.scanState).toBe('pending');
    await cases.addEvidence('c-1', { kind: 'link', name: 'FI decision memo', url: 'https://intranet.example.com/memo/42' });
    await cases.removeEvidence('e-1');
    expect(calls.map((c) => [c.method, c.path, c.ifMatch])).toEqual([
      ['POST', '/api/v1/changes/c-1/evidence', null],
      ['POST', '/api/v1/changes/c-1/evidence', null],
      ['DELETE', '/api/v1/evidence/e-1', null],
    ]);
    const sentFile = calls[0]?.data as FormData;
    expect(sentFile).toBeInstanceOf(FormData);
    expect([sentFile.get('kind'), sentFile.get('name'), sentFile.get('url')]).toEqual(['file', 'criteria.pdf', null]);
    expect(sentFile.get('file')).toBeInstanceOf(Blob);
    const sentLink = calls[1]?.data as FormData;
    expect([sentLink.get('kind'), sentLink.get('url'), sentLink.get('file')]).toEqual(['link', 'https://intranet.example.com/memo/42', null]);
  });

  it('lists evidence and downloads a checked file as bytes through the API', async () => {
    const calls = record({ items: [], total: 0 });
    await cases.listEvidence('c-1');
    await cases.downloadEvidence('e-1');
    expect(calls.map((c) => [c.method, c.path, c.responseType])).toEqual([
      ['GET', '/api/v1/changes/c-1/evidence', undefined],
      ['GET', '/api/v1/evidence/e-1/download', 'blob'],
    ]);
  });

  it('requests, approves and sends back a sign-off with the case’s version', async () => {
    const calls = record({ id: 'case-1', version: 8 });
    await cases.requestSignoff('c-1', 6);
    await cases.approveSignoff('c-1', { note: '' }, 7);
    await cases.sendBackSignoff('c-1', { note: 'The criteria need the committee’s date.' }, 7);
    expect(calls.map((c) => [c.method, c.path, c.ifMatch])).toEqual([
      ['POST', '/api/v1/changes/c-1/signoff/request', '"6"'],
      ['POST', '/api/v1/changes/c-1/signoff/approve', '"7"'],
      ['POST', '/api/v1/changes/c-1/signoff/send-back', '"7"'],
    ]);
    expect(json(calls[2])).toEqual({ note: 'The criteria need the committee’s date.' });
  });

  it('reads the case file as the server’s plain text', async () => {
    const calls = record('Case file: FI adopts amended rules\nStatus: closed (signed off)\n');
    expect(await cases.getCaseFile('c-1')).toBe('Case file: FI adopts amended rules\nStatus: closed (signed off)\n');
    expect([calls[0]?.path, calls[0]?.responseType, calls[0]?.ifMatch]).toEqual(['/api/v1/changes/c-1/case-file', 'text', null]);
  });

  it('puts an id into the path as one segment', async () => {
    const calls = record({});
    await cases.getCaseFile('a/b');
    expect(calls[0]?.path).toBe('/api/v1/changes/a%2Fb/case-file');
  });
});
