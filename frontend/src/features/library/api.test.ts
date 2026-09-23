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
  jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
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
  jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
  inFootprint: true,
  outsideReason: [],
  lastVerifiedAt: '2026-06-30',
  openChangeCount: 1,
  pendingApplicability: null,
  complianceStatus: null,
};

// A seeded version nobody approved, and the provenance of one in force.
const nobody = { verifiedOrigin: '', confirmedByAgent: null, proposedByAgent: null };

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
  version: { versionNumber: 1, effectiveFrom: null, effectiveTo: { date: '2026-09-30', precision: 'day' }, approvedAt: null, ...nobody },
  versions: [
    { versionNumber: 1, effectiveFrom: null, effectiveTo: { date: '2026-09-30', precision: 'day' }, approvedAt: null, ...nobody },
    // Proposed by one agent and confirmed by an independent one: both are named (INV-05).
    {
      versionNumber: 2,
      effectiveFrom: { date: '2026-10-01', precision: 'day' },
      effectiveTo: null,
      approvedAt: '2026-09-17T14:02:11Z',
      verifiedOrigin: 'agent',
      confirmedByAgent: { id: 'ag-2', key: 'library-confirmer' },
      proposedByAgent: { id: 'ag-1', key: 'watch-sweeper' },
    },
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
    ...nobody,
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
    expect(library.serializeQuery({ asOf: undefined, instrument: null, footprint: 'all', offset: 0 })).toBe('footprint=all&offset=0');
    expect(library.serializeQuery({})).toBe('');
  });

  it('reads a version, a legal date and a compliance status only when the server sent one it knows', () => {
    expect(library.versionOf(null)).toBeNull();
    expect(library.versionOf(undefined)).toBeNull();
    expect(library.versionOf({ versionNumber: 3, effectiveFrom: null, ...nobody })).toEqual({ versionNumber: 3, effectiveFrom: null });
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
    const page = await library.listObligations({ footprint: 'all' });
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

  it('reads a record with no version in force, no lineage and nobody named as verifier', async () => {
    installAdapter(() => ({
      status: 200,
      data: {
        ...serverDetail,
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

const serverInstrumentRow = {
  id: 'in-1',
  stableKey: 'fffs-2017-2',
  shortName: 'FFFS 2017:2',
  name: { text: 'FFFS 2017:2 om värdepappersrörelse', language: 'sv', isOriginal: true, isMachine: false },
  level: { key: 'authority_regulation', kind: null, label: 'Supervisory regulation' },
  binding: true,
  jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
  authority: { key: 'fi', name: 'Finansinspektionen', shortName: 'FI', url: 'https://www.fi.se/' },
  regime: { key: 'securities', kind: null, label: 'Securities' },
  officialRef: 'FFFS 2017:2',
  inForceFrom: { date: '2018-01-03', precision: 'day' },
  inForceTo: null,
  implementsNote: 'MiFID II delegated directive (EU) 2017/593',
  obligationCount: 2,
  inFootprint: true,
  lastVerifiedAt: '2026-06-30T07:12:44Z',
  sourceUrl: 'https://www.fi.se/en/published/regulations/2017/fffs-20172/',
};

const serverInstrumentDetail = {
  ...serverInstrumentRow,
  eliUri: '',
  verifiedBy: null,
  lineage: [
    {
      relation: { key: 'amends', kind: null, label: 'Amends' },
      direction: 'incoming',
      instrument: { key: 'fffs-2026-11', shortName: 'FFFS 2026:11' },
      note: 'Amends FFFS 2017:2, in force 1 October 2026.',
      toRef: '',
    },
  ],
};

describe('library instruments api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('lists instruments and reads the page into the shape the screen uses', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [serverInstrumentRow], total: 1 } }));
    expect(await library.listInstruments({ regime: 'securities', footprint: 'watched', limit: 20, offset: 0 })).toEqual({
      items: [
        {
          id: 'in-1',
          stableKey: 'fffs-2017-2',
          shortName: 'FFFS 2017:2',
          name: serverInstrumentRow.name,
          level: serverInstrumentRow.level,
          binding: true,
          jurisdiction: serverInstrumentRow.jurisdiction,
          authority: serverInstrumentRow.authority,
          regime: serverInstrumentRow.regime,
          officialRef: 'FFFS 2017:2',
          inForceFrom: { date: '2018-01-03', precision: 'day' },
          inForceTo: null,
          implementsNote: 'MiFID II delegated directive (EU) 2017/593',
          obligationCount: 2,
          inFootprint: true,
          lastVerifiedAt: '2026-06-30T07:12:44Z',
          sourceUrl: serverInstrumentRow.sourceUrl,
        },
      ],
      total: 1,
    });
    expect(sent.map((s) => [s.method, s.path, s.params])).toEqual([['get', '/api/v1/instruments', { regime: 'securities', footprint: 'watched', limit: 20, offset: 0 }]]);
  });

  it('reads a row with no name and no authority', async () => {
    installAdapter(() => ({
      status: 200,
      data: { items: [{ ...serverInstrumentRow, name: null, authority: null }], total: 1 },
    }));
    const page = await library.listInstruments();
    expect(page.items[0]).toMatchObject({ name: null, authority: null });
  });

  it('reads one instrument with its ELI, its authority and its lineage', async () => {
    const sent = installAdapter(() => ({ status: 200, data: serverInstrumentDetail }));
    expect(await library.getInstrument('in-1')).toEqual({
      id: 'in-1',
      stableKey: 'fffs-2017-2',
      shortName: 'FFFS 2017:2',
      name: serverInstrumentRow.name,
      level: serverInstrumentRow.level,
      binding: true,
      jurisdiction: serverInstrumentRow.jurisdiction,
      authority: serverInstrumentRow.authority,
      regime: serverInstrumentRow.regime,
      officialRef: 'FFFS 2017:2',
      eliUri: '',
      inForceFrom: { date: '2018-01-03', precision: 'day' },
      inForceTo: null,
      implementsNote: 'MiFID II delegated directive (EU) 2017/593',
      sourceUrl: serverInstrumentRow.sourceUrl,
      lastVerifiedAt: '2026-06-30T07:12:44Z',
      verifiedBy: null,
      lineage: [
        {
          relation: { key: 'amends', kind: null, label: 'Amends' },
          direction: 'incoming',
          instrument: { key: 'fffs-2026-11', shortName: 'FFFS 2026:11' },
          note: 'Amends FFFS 2017:2, in force 1 October 2026.',
          toRef: '',
        },
      ],
    });
    expect(sent.map((s) => [s.method, s.path])).toEqual([['get', '/api/v1/instruments/in-1']]);
  });

  it('reads a card with no lineage, an unknown direction and someone named as verifier', async () => {
    installAdapter(() => ({
      status: 200,
      data: {
        ...serverInstrumentDetail,
        lineage: [{ ...serverInstrumentDetail.lineage[0], direction: 'sideways' }],
        verifiedBy: { id: 'u-1', name: 'Johan Ek' },
      },
    }));
    const record = await library.getInstrument('in-1');
    expect(record.verifiedBy).toEqual({ id: 'u-1', name: 'Johan Ek' });
    // A direction the screen has no rule for reads as incoming, never as a crash.
    expect(record.lineage[0]?.direction).toBe('incoming');
    installAdapter(() => ({ status: 200, data: { ...serverInstrumentDetail, lineage: undefined } }));
    expect((await library.getInstrument('in-1')).lineage).toEqual([]);
  });

  it('files a problem report against an instrument', async () => {
    const sent = installAdapter(() => ({ status: 201, data: { id: 'rep-2', status: 'open', createdAt: '2026-09-21T09:00:00Z' } }));
    expect(await library.reportInstrumentProblem('in-1', { description: 'The in-force date looks wrong.' })).toEqual({
      id: 'rep-2',
      status: 'open',
      createdAt: '2026-09-21T09:00:00Z',
    });
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([['post', '/api/v1/instruments/in-1/problem-reports', { description: 'The in-force date looks wrong.' }]]);
  });
});

const serverProvisionNode = {
  id: 'pr-6',
  stableKey: 'fffs-2017-2/9-6',
  kind: { key: 'section', kind: 'unit', label: 'Section' },
  refLabel: '6 §',
  heading: 'Betalning för analys',
  path: 'FFFS 2017:2 > 9 kap. > 6 §',
  children: [],
  versions: [
    {
      versionNumber: 1,
      effectiveFrom: { date: '2018-01-03', precision: 'day' },
      effectiveTo: { date: '2026-09-30', precision: 'day' },
      transitionalNote: '',
      text: { text: 'Research payment under the earlier rules.', language: 'en', isOriginal: false, isMachine: true },
    },
  ],
  inForceVersion: 1,
  obligations: [{ id: 'ob-1', title: null, refLabel: 'Third-party payments' }],
};

describe('library provisions api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the provision tree, recursively, into the shape the screen uses', async () => {
    const chapterRow = { ...serverProvisionNode, id: 'pr-9', stableKey: 'fffs-2017-2/9', refLabel: '9 kap.', versions: [], obligations: [], children: [serverProvisionNode] };
    const sent = installAdapter(() => ({ status: 200, data: [chapterRow] }));
    const nodes = await library.listInstrumentProvisions('in-1', '2026-09-16');
    expect(nodes).toHaveLength(1);
    expect(nodes[0]?.children[0]).toEqual({
      id: 'pr-6',
      stableKey: 'fffs-2017-2/9-6',
      // A provision's own `kind` names its structural kind (`unit`, `division`, `annex`)
      // rather than being null, because a screen groups by it (INV-02).
      kind: { key: 'section', kind: 'unit', label: 'Section' },
      refLabel: '6 §',
      heading: 'Betalning för analys',
      path: 'FFFS 2017:2 > 9 kap. > 6 §',
      children: [],
      versions: [
        {
          versionNumber: 1,
          effectiveFrom: { date: '2018-01-03', precision: 'day' },
          effectiveTo: { date: '2026-09-30', precision: 'day' },
          transitionalNote: '',
          text: { text: 'Research payment under the earlier rules.', language: 'en', isOriginal: false, isMachine: true },
        },
      ],
      inForceVersion: 1,
      obligations: [{ id: 'ob-1', title: null, refLabel: 'Third-party payments' }],
    });
    expect(sent.map((s) => [s.method, s.path, s.params])).toEqual([['get', '/api/v1/instruments/in-1/provisions', { asOf: '2026-09-16' }]]);
  });

  it('reads an empty tree, and a node with no children, no versions and no citing obligation', async () => {
    installAdapter(() => ({ status: 200, data: [] }));
    expect(await library.listInstrumentProvisions('in-1')).toEqual([]);
    installAdapter(() => ({ status: 200, data: [{ ...serverProvisionNode, children: undefined, versions: undefined, obligations: undefined }] }));
    const bare = await library.listInstrumentProvisions('in-1');
    expect(bare[0]).toMatchObject({ children: [], versions: [], obligations: [] });
  });

  it('reads the diff between two provision versions', async () => {
    const sent = installAdapter(() => ({
      status: 200,
      data: { fromVersion: 1, toVersion: 2, fromEffective: null, toEffective: { date: '2026-10-01', precision: 'day' }, language: 'en', isMachine: true, segments: [] },
    }));
    expect(await library.getProvisionDiff('pr-6', 'en')).toMatchObject({ fromVersion: 1, toVersion: 2, language: 'en' });
    expect(sent.map((s) => [s.path, s.params])).toEqual([['/api/v1/provisions/pr-6/diff', { lang: 'en' }]]);
  });
});
