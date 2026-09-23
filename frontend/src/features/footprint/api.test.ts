import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as footprint from './api';

// Each wrapper hits its route with its method, body or query and returns `.data`.

describe('footprint api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  // The server's shapes (openapi.json) as they arrive, and what the screen reads.
  const serverRequest = {
    id: 'r1',
    status: 'pending',
    requestedAt: '2026-09-18T12:00:00Z',
    requestedBy: { id: 'u1', name: 'Sara Lindqvist' },
    removes: [{ dimension: 'service_type', key: 'advice', kind: null, label: 'Advice' }],
    preview: { obligations: { hidden: 4, revealed: 0, available: true }, cases: { hidden: 0, revealed: 0, available: false } },
    decisionNote: '',
    version: 2,
  };
  const screenRequest = {
    id: 'r1',
    status: 'pending',
    requestedAt: '2026-09-18T12:00:00Z',
    requestedBy: { id: 'u1', name: 'Sara Lindqvist' },
    adds: [],
    removes: [{ dimension: 'service_type', key: 'advice', kind: null, label: 'Advice' }],
    preview: {
      hidden: { obligations: { count: 4, available: true }, cases: { count: 0, available: false } },
      revealed: { obligations: { count: 0, available: true }, cases: { count: 0, available: false } },
    },
    decidedBy: null,
    decidedAt: null,
    decisionNote: '',
    version: 2,
  };

  it('reads the footprint and its requests into the shapes the screen uses', async () => {
    const view = {
      dimensions: [{ dimension: { key: 'service_type', kind: null, label: 'Services we provide' }, restrictsFootprint: true, allSelected: false, terms: [{ key: 'advice', label: 'Advice' }] }],
      pendingRequest: serverRequest,
      markets: [
        { jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' }, level: 'operating' },
        { jurisdiction: { key: 'no', label: 'Norway' }, level: 'watching' },
      ],
    };
    const sent = installAdapter((s) => ({ status: 200, data: s.path.endsWith('/requests') ? { items: [serverRequest], total: 1 } : view }));
    expect(await footprint.getFootprint()).toEqual({
      dimensions: [{ dimension: { key: 'service_type', kind: null, label: 'Services we provide' }, restrictsFootprint: true, terms: [{ key: 'advice', kind: null, label: 'Advice' }], allSelected: false }],
      pendingRequest: screenRequest,
      markets: [
        { jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' }, level: 'operating' },
        { jurisdiction: { key: 'no', kind: null, label: 'Norway' }, level: 'watching' },
      ],
    });
    expect(await footprint.listFootprintRequests({ limit: 20, offset: 0 })).toEqual({ items: [screenRequest], total: 1 });
    expect(await footprint.listFootprintRequests()).toEqual({ items: [screenRequest], total: 1 });
    expect(sent.map((s) => [s.method, s.path, s.params, s.authorization])).toEqual([
      ['get', '/api/v1/tenant/footprint', null, 'Bearer tok'],
      ['get', '/api/v1/tenant/footprint/requests', { limit: 20, offset: 0 }, 'Bearer tok'],
      ['get', '/api/v1/tenant/footprint/requests', {}, 'Bearer tok'],
    ]);
  });

  it('reads a footprint with no pending request and dimensions with no terms', () => {
    expect(footprint.footprintOf({ dimensions: [{ dimension: { key: 'channel', label: 'Channels' }, restrictsFootprint: true, allSelected: true }], pendingRequest: null })).toEqual({
      dimensions: [{ dimension: { key: 'channel', kind: null, label: 'Channels' }, restrictsFootprint: true, terms: [], allSelected: true }],
      pendingRequest: null,
      markets: [],
    });
    expect(footprint.footprintOf({ dimensions: [] }).pendingRequest).toBeNull();
  });

  it('never mistakes a request whose requester is gone for the viewer, and reads an unknown status as waiting', () => {
    const orphan = footprint.requestOf({
      id: 'r2',
      status: 'someday',
      requestedAt: '2026-09-01T00:00:00Z',
      requestedBy: null,
      preview: {},
      decidedBy: { id: 'u2', name: 'Maria Ek' },
      decidedAt: '2026-09-02T00:00:00Z',
      decisionNote: 'Ours',
      version: 7,
    });
    expect(orphan.requestedBy).toEqual({ id: '', name: '' });
    expect(orphan.status).toBe('pending');
    expect(orphan.adds).toEqual([]);
    expect(orphan.version).toBe(7);
    expect(orphan.decisionNote).toBe('Ours');
    for (const status of ['approved', 'rejected', 'withdrawn']) expect(footprint.requestOf({ ...serverRequest, status }).status).toBe(status);
    const { requestedBy: _gone, ...unnamed } = serverRequest;
    expect(footprint.requestOf(unnamed).requestedBy).toEqual({ id: '', name: '' });
  });

  it('turns the per-kind preview into hides and reveals, skipping an empty kind', () => {
    expect(footprint.previewOf(null)).toEqual({ hidden: {}, revealed: {} });
    expect(footprint.previewOf({ obligations: { hidden: 0, revealed: 2, available: true } })).toEqual({
      hidden: { obligations: { count: 0, available: true } },
      revealed: { obligations: { count: 2, available: true } },
    });
    expect(footprint.previewOf({ obligations: undefined, cases: { hidden: 1, revealed: 0, available: false } })).toEqual({
      hidden: { cases: { count: 1, available: false } },
      revealed: { cases: { count: 0, available: false } },
    });
  });

  it('creates, approves, rejects and withdraws a request, with If-Match when a version is known', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'post' && s.path.endsWith('/requests') ? 201 : 200, data: serverRequest }));
    await footprint.createFootprintRequest({ adds: [], removes: [{ dimension: 'service_type', key: 'advice' }] });
    await footprint.approveFootprintRequest('r1', 3);
    await footprint.rejectFootprintRequest('r1', { note: 'We still advise' });
    await footprint.withdrawFootprintRequest('r1');
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['post', '/api/v1/tenant/footprint/requests'],
      ['post', '/api/v1/tenant/footprint/requests/r1/approve'],
      ['post', '/api/v1/tenant/footprint/requests/r1/reject'],
      ['post', '/api/v1/tenant/footprint/requests/r1/withdraw'],
    ]);
    expect(sent[0]?.body).toEqual({ adds: [], removes: [{ dimension: 'service_type', key: 'advice' }] });
    expect(sent[2]?.body).toEqual({ note: 'We still advise' });
  });

  it('lists terms by the key of their dimension, and the dimensions with their footprint flag', async () => {
    const term = { id: 't1', key: 'advice', label: 'Advice', dimension: { key: 'service_type', kind: null, label: 'Services we provide' }, active: true, isSystem: true, sortOrder: 0, usageNote: '', version: 1, mirrored: false };
    const dimensions = [
      { key: 'regime', label: 'Regime', extra: { restrictsFootprint: true } },
      { key: 'theme', label: 'Theme', kind: 'classification', extra: { restrictsFootprint: false } },
      { key: 'other', label: 'Other' },
    ];
    const sent = installAdapter((s) => ({ status: 200, data: s.path.endsWith('/dimensions') ? { items: dimensions, total: 3 } : { items: [term], total: 1 } }));
    const expected = [{ dimension: 'service_type', key: 'advice', kind: null, label: 'Advice', usageNote: '', sortOrder: 0, active: true, mirrored: false }];
    expect(await footprint.listTerms()).toEqual(expected);
    expect(await footprint.listTerms('service_type')).toEqual(expected);
    expect(await footprint.listDimensions()).toEqual([
      { key: 'regime', kind: null, label: 'Regime', restrictsFootprint: true },
      { key: 'theme', kind: 'classification', label: 'Theme', restrictsFootprint: false },
      { key: 'other', kind: null, label: 'Other', restrictsFootprint: false },
    ]);
    expect(footprint.taxonomyTermOf({ ...term, active: false, usageNote: 'n', sortOrder: 3 }).active).toBe(false);
    expect(footprint.taxonomyTermOf({ ...term, mirrored: true }).mirrored).toBe(true);
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/taxonomy/terms', {}],
      ['/api/v1/taxonomy/terms', { dimension: 'service_type' }],
      ['/api/v1/taxonomy/dimensions', null],
    ]);
  });

  it('watches and unwatches a market with its key in the body, never in the path or the query', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: { jurisdiction: { key: 'no', kind: 'country', label: 'Norway' }, level: s.path.endsWith('/remove') ? 'not_followed' : 'watching' } }));
    expect(await footprint.watchMarket('no')).toEqual({ jurisdiction: { key: 'no', kind: 'country', label: 'Norway' }, level: 'watching' });
    expect(await footprint.unwatchMarket('no')).toEqual({ jurisdiction: { key: 'no', kind: 'country', label: 'Norway' }, level: 'not_followed' });
    expect(sent.map((s) => [s.method, s.path, s.params, s.body])).toEqual([
      ['post', '/api/v1/tenant/footprint/watching', null, { jurisdiction: 'no' }],
      ['post', '/api/v1/tenant/footprint/watching/remove', null, { jurisdiction: 'no' }],
    ]);
  });

  it('reads the jurisdictions with the one whose rules reach each', async () => {
    const sent = installAdapter(() => ({
      status: 200,
      data: [
        { key: 'eu', kind: 'supranational', label: 'European Union', parentKey: null, defaultLanguage: null },
        { key: 'no', kind: 'country', label: 'Norway', parentKey: 'eu' },
        { key: 'xx', label: 'Nowhere' },
      ],
    }));
    expect(await footprint.listJurisdictions()).toEqual([
      { key: 'eu', kind: 'supranational', label: 'European Union', parentKey: null },
      { key: 'no', kind: 'country', label: 'Norway', parentKey: 'eu' },
      { key: 'xx', kind: null, label: 'Nowhere', parentKey: null },
    ]);
    expect(sent.map((s) => [s.method, s.path])).toEqual([['get', '/api/v1/reference/jurisdictions']]);
  });

  it('suggests a term and reads the proposal back, nested or flat', async () => {
    let flat = false;
    const sent = installAdapter(() => ({ status: 202, data: flat ? { id: 'p2', kind: 'term_create', status: 'open', title: 'T+1' } : { proposal: { id: 'p1', kind: 'term_create', status: 'open', title: 'Robo' } } }));
    expect(await footprint.suggestTerm({ dimension: 'channel', labels: { en: 'Robo' } })).toEqual({ id: 'p1', kind: 'term_create', status: 'open', title: 'Robo' });
    flat = true;
    expect(await footprint.suggestTerm({ dimension: 'channel', labels: { en: 'T+1' } })).toEqual({ id: 'p2', kind: 'term_create', status: 'open', title: 'T+1' });
    expect(sent[0]).toMatchObject({ method: 'post', path: '/api/v1/taxonomy/terms', body: { dimension: 'channel', labels: { en: 'Robo' } } });
  });
});
