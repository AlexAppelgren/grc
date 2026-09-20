import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as library from './api';

// GET /obligations: the route, its keys-only query, and the server's shape
// read into the one the inventory uses.

const serverRow = {
  id: '11111111-1111-4111-8111-111111111111',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: false, isMachine: true },
  instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
  bindingLevel: { key: 'regulation', kind: null, label: 'FI regulation' },
  binding: true,
  dutyType: { key: 'conduct', kind: null, label: 'Conduct' },
  tags: [{ key: 'research', kind: null, label: 'Research' }],
  scope: [
    { dimension: { key: 'service_type', kind: null, label: 'Service' }, terms: [{ key: 'advice', kind: null, label: 'Advice' }], allSelected: false },
    { dimension: { key: 'channel', kind: null, label: 'Channel' }, terms: [], allSelected: false },
  ],
  version: { versionNumber: 1, effectiveFrom: { date: '2018-01-03', precision: 'day' } },
  upcomingVersion: { versionNumber: 2, effectiveFrom: { date: '2026-10-01', precision: 'day' } },
  inFootprint: true,
  outsideReason: [],
  lastVerifiedAt: '2026-06-30',
  openChangeCount: 1,
  pendingApplicability: null,
  complianceStatus: null,
};

const screenRow = {
  id: '11111111-1111-4111-8111-111111111111',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: false, isMachine: true },
  instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
  bindingLevel: { key: 'regulation', kind: null, label: 'FI regulation' },
  binding: true,
  dutyType: { key: 'conduct', kind: null, label: 'Conduct' },
  tags: [{ key: 'research', kind: null, label: 'Research' }],
  scope: [
    { dimension: { key: 'service_type', kind: null, label: 'Service' }, terms: [{ key: 'advice', kind: null, label: 'Advice' }], allSelected: false },
    { dimension: { key: 'channel', kind: null, label: 'Channel' }, terms: [], allSelected: false },
  ],
  version: { versionNumber: 1, effectiveFrom: { date: '2018-01-03', precision: 'day' } },
  upcomingVersion: { versionNumber: 2, effectiveFrom: { date: '2026-10-01', precision: 'day' } },
  inFootprint: true,
  outsideReason: [],
  lastVerifiedAt: '2026-06-30',
  openChangeCount: 1,
  pendingApplicability: null,
  complianceStatus: null,
};

describe('library api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('lists obligations and reads the page into the shape the screen uses', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [serverRow], total: 1 } }));
    expect(await library.listObligations({ term: ['regime:securities', 'service_type:advice'], dutyType: 'conduct', asOf: '2026-09-16', limit: 20, offset: 0 })).toEqual({
      items: [screenRow],
      total: 1,
    });
    expect(await library.listObligations()).toEqual({ items: [screenRow], total: 1 });
    expect(sent.map((s) => [s.method, s.path, s.params, s.authorization])).toEqual([
      ['get', '/api/v1/obligations', { term: ['regime:securities', 'service_type:advice'], dutyType: 'conduct', asOf: '2026-09-16', limit: 20, offset: 0 }, 'Bearer tok'],
      ['get', '/api/v1/obligations', {}, 'Bearer tok'],
    ]);
  });

  it('repeats each term as its own parameter and drops what was not set', () => {
    expect(library.serializeQuery({ term: ['regime:securities', 'service_type:advice'], dutyType: 'conduct' })).toBe(
      'term=regime%3Asecurities&term=service_type%3Aadvice&dutyType=conduct',
    );
    expect(library.serializeQuery({ asOf: undefined, instrument: null, outsideFootprint: true, offset: 0 })).toBe('outsideFootprint=true&offset=0');
    expect(library.serializeQuery({})).toBe('');
  });

  it('reads a version, a legal date and a compliance status only when the server sent one it knows', () => {
    expect(library.versionOf(null)).toBeNull();
    expect(library.versionOf(undefined)).toBeNull();
    expect(library.versionOf({ versionNumber: 3, effectiveFrom: null })).toEqual({ versionNumber: 3, effectiveFrom: null });
    expect(library.partialDateOf({ date: '2026-10-01', precision: 'quarter' })).toEqual({ date: '2026-10-01', precision: 'quarter' });
    // A precision the screen has no rule for reads as the day the string carries, never as a crash.
    expect(library.partialDateOf({ date: '2026-10-01', precision: 'decade' })).toEqual({ date: '2026-10-01', precision: 'day' });
    expect(library.complianceOf(null)).toBeNull();
    expect(library.complianceOf(undefined)).toBeNull();
    expect(library.complianceOf({ key: 'partly', kind: 'partly', label: 'Partly compliant' })).toEqual({ key: 'partly', kind: 'partly', label: 'Partly compliant' });
    // A status whose kind is not one of the four has no tone, so it is not shown as a pill.
    expect(library.complianceOf({ key: 'invented', kind: 'something_else', label: 'Invented' })).toBeNull();
    expect(library.complianceOf({ key: 'invented', kind: null, label: 'Invented' })).toBeNull();
  });

  it('reads a row with no title, no versions, no tags and a footprint reason', async () => {
    const outside = {
      ...serverRow,
      title: null,
      tags: undefined,
      scope: undefined,
      version: null,
      upcomingVersion: null,
      inFootprint: false,
      outsideReason: [
        { dimension: { key: 'service_type', kind: null, label: 'Service' }, terms: [{ key: 'advice', kind: null, label: 'Advice' }] },
        { dimension: { key: 'channel', kind: null, label: 'Channel' } },
      ],
      lastVerifiedAt: null,
      pendingApplicability: true,
      complianceStatus: { key: 'gap', kind: 'gap', label: 'Gap' },
    };
    // A dimension the record carries no term in, and a server that sends no reason at all.
    const bare = {
      ...serverRow,
      id: '33333333-3333-4333-8333-333333333333',
      scope: [{ dimension: { key: 'channel', kind: null, label: 'Channel' }, allSelected: false }],
      outsideReason: undefined,
    };
    installAdapter(() => ({ status: 200, data: { items: [outside, bare], total: 2 } }));
    const page = await library.listObligations({ outsideFootprint: true });
    expect(page.items[1]).toMatchObject({
      scope: [{ dimension: { key: 'channel', kind: null, label: 'Channel' }, terms: [], allSelected: false }],
      outsideReason: [],
    });
    expect(page.items[0]).toMatchObject({
      title: null,
      tags: [],
      scope: [],
      version: null,
      upcomingVersion: null,
      inFootprint: false,
      outsideReason: [
        { dimension: { key: 'service_type', kind: null, label: 'Service' }, terms: [{ key: 'advice', kind: null, label: 'Advice' }] },
        { dimension: { key: 'channel', kind: null, label: 'Channel' }, terms: [] },
      ],
      lastVerifiedAt: null,
      pendingApplicability: true,
      complianceStatus: { key: 'gap', kind: 'gap', label: 'Gap' },
    });
  });

  it('keeps a kind the server left out as null', () => {
    expect(library.refOf({ key: 'conduct', label: 'Conduct' } as { key: string; kind: string | null; label: string })).toEqual({ key: 'conduct', kind: null, label: 'Conduct' });
  });
});
