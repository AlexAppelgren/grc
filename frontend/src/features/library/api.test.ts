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

const serverDetail = {
  id: '11111111-1111-4111-8111-111111111111',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: true, isMachine: false },
  instrument: {
    key: 'fffs-2017-2',
    shortName: 'FFFS 2017:2',
    officialRef: 'FFFS 2017:2',
    name: { text: 'FFFS 2017:2 om värdepappersrörelse', language: 'sv', isOriginal: true, isMachine: false },
    implementsNote: 'MiFID II delegated directive (EU) 2017/593',
  },
  regime: { key: 'securities', kind: null, label: 'Securities' },
  bindingLevel: { key: 'authority_regulation', kind: null, label: 'FI regulation' },
  binding: true,
  dutyType: { key: 'governance', kind: null, label: 'Governance' },
  productScope: 'Third-party research',
  triggerFrequency: 'Annual assessment from 1 October 2026',
  retention: '5 years',
  sanctionExposure: 'FI remark, warning or sanction fee',
  tags: [{ key: 'research', kind: null, label: 'Research' }],
  scope: [{ dimension: { key: 'service_type', kind: null, label: 'Service' }, terms: [{ key: 'advice', kind: null, label: 'Advice' }], allSelected: false }],
  provisions: [{ id: 'pr-1', refLabel: '9 kap. 6 §', path: 'FFFS 2017:2 > 9 kap. > 6 §' }],
  inFootprint: true,
  outsideReason: [],
  summary: { text: 'Research from third parties may be received only if…', language: 'en', isOriginal: false, isMachine: true },
  translations: [
    { text: 'Investeringsanalys från tredje part…', language: 'sv', isOriginal: true, isMachine: false },
    { text: 'Research from third parties may be received only if…', language: 'en', isOriginal: false, isMachine: true },
  ],
  version: { versionNumber: 1, effectiveFrom: null, effectiveTo: { date: '2026-09-30', precision: 'day' }, approvedAt: null },
  versions: [
    { versionNumber: 1, effectiveFrom: null, effectiveTo: { date: '2026-09-30', precision: 'day' }, approvedAt: null },
    { versionNumber: 2, effectiveFrom: { date: '2026-10-01', precision: 'day' }, effectiveTo: null, approvedAt: '2026-09-17T14:02:11Z' },
  ],
  related: [
    {
      id: '22222222-2222-4222-8222-222222222222',
      title: { text: 'Disclose all costs and charges', language: 'en', isOriginal: true, isMachine: false },
      instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
      relation: { key: 'related', kind: null, label: 'Related' },
      binding: true,
    },
  ],
  provenance: {
    sourceUrl: 'https://www.fi.se/',
    sourceLabel: 'FFFS 2017:2, 9 kap. 6 §',
    lastVerifiedAt: '2026-06-30T07:12:44Z',
    verifiedBy: null,
    createdAt: '2026-03-12T08:45:03Z',
    createdOrigin: 'agent',
    createdModel: 'agent pipeline 0.3',
  },
};

// The detail the screen uses: the same facts, with each legal date read as a
// date plus its precision and the provisions left to the instrument's tree.
const screenDetail = {
  id: serverDetail.id,
  stableKey: serverDetail.stableKey,
  refLabel: serverDetail.refLabel,
  title: serverDetail.title,
  instrument: serverDetail.instrument,
  regime: serverDetail.regime,
  bindingLevel: serverDetail.bindingLevel,
  binding: true,
  dutyType: serverDetail.dutyType,
  productScope: serverDetail.productScope,
  triggerFrequency: serverDetail.triggerFrequency,
  retention: serverDetail.retention,
  sanctionExposure: serverDetail.sanctionExposure,
  tags: serverDetail.tags,
  scope: serverDetail.scope,
  inFootprint: true,
  outsideReason: [],
  summary: serverDetail.summary,
  translations: serverDetail.translations,
  version: serverDetail.versions[0],
  versions: serverDetail.versions,
  related: serverDetail.related,
  provenance: serverDetail.provenance,
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


  it('reads one obligation as of a date, with its versions, translations, lineage and provenance', async () => {
    const sent = installAdapter(() => ({ status: 200, data: serverDetail }));
    expect(await library.getObligation('ob-1', '2026-06-30')).toEqual(screenDetail);
    expect(await library.getObligation('ob-1')).toEqual(screenDetail);
    // An empty "as of" is today in the bank's own time zone, which the server decides.
    expect(await library.getObligation('ob-1', '')).toEqual(screenDetail);
    expect(sent.map((s) => [s.method, s.path, s.params])).toEqual([
      ['get', '/api/v1/obligations/ob-1', { asOf: '2026-06-30' }],
      ['get', '/api/v1/obligations/ob-1', {}],
      ['get', '/api/v1/obligations/ob-1', {}],
    ]);
  });

  it('reads a record with no regime, no version in force, no lineage and nobody named as verifier', async () => {
    installAdapter(() => ({
      status: 200,
      data: {
        ...serverDetail,
        regime: null,
        summary: null,
        translations: undefined,
        version: null,
        versions: undefined,
        related: undefined,
        tags: undefined,
        scope: undefined,
        outsideReason: undefined,
        provenance: { ...serverDetail.provenance, lastVerifiedAt: null, verifiedBy: null },
      },
    }));
    expect(await library.getObligation('ob-1')).toMatchObject({
      regime: null,
      summary: null,
      translations: [],
      version: null,
      versions: [],
      related: [],
      tags: [],
      scope: [],
      outsideReason: [],
      provenance: { lastVerifiedAt: null, verifiedBy: null },
    });
  });

  it('reads the diff and keeps an operation it has no colour for as plain text', async () => {
    const sent = installAdapter(() => ({
      status: 200,
      data: {
        fromVersion: 1,
        toVersion: 2,
        fromEffective: null,
        toEffective: { date: '2026-10-01', precision: 'day' },
        language: 'en',
        isMachine: true,
        segments: [{ op: 'equal', text: 'One.' }, { op: 'insert', text: 'Two.' }, { op: 'delete', text: 'Three.' }, { op: 'reworded', text: 'Four.' }],
      },
    }));
    expect(await library.getObligationDiff('ob-1', 'en')).toEqual({
      fromVersion: 1,
      toVersion: 2,
      fromEffective: null,
      toEffective: { date: '2026-10-01', precision: 'day' },
      language: 'en',
      isMachine: true,
      segments: [{ op: 'equal', text: 'One.' }, { op: 'insert', text: 'Two.' }, { op: 'delete', text: 'Three.' }, { op: 'equal', text: 'Four.' }],
    });
    installAdapter(() => ({ status: 200, data: { fromVersion: 1, toVersion: 2, fromEffective: null, toEffective: null, language: 'sv', isMachine: false, segments: undefined } }));
    expect((await library.getObligationDiff('ob-1')).segments).toEqual([]);
    expect(sent.map((s) => [s.path, s.params])).toEqual([['/api/v1/obligations/ob-1/diff', { lang: 'en' }]]);
  });

  it('files a problem report with what was on screen', async () => {
    const sent = installAdapter(() => ({ status: 201, data: { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' } }));
    expect(await library.reportObligationProblem('ob-1', { description: 'The English says annually.', versionNumber: 2, language: 'en' })).toEqual({
      id: 'rep-1',
      status: 'open',
      createdAt: '2026-09-21T09:00:00Z',
    });
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([
      ['post', '/api/v1/obligations/ob-1/problem-reports', { description: 'The English says annually.', versionNumber: 2, language: 'en' }],
    ]);
  });

  it('keeps a kind the server left out as null', () => {
    expect(library.refOf({ key: 'conduct', label: 'Conduct' } as { key: string; kind: string | null; label: string })).toEqual({ key: 'conduct', kind: null, label: 'Conduct' });
  });
});
