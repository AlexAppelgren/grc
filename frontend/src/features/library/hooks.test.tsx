import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import {
  INSTRUMENT_PAGE,
  libraryKeys,
  OBLIGATION_PAGE,
  useInstrument,
  useInstrumentProvisions,
  useInstruments,
  useObligation,
  useObligationDiff,
  useObligations,
  useProvisionDiff,
  useReportInstrumentProblem,
  useReportObligationProblem,
} from './hooks';

// The library's reads: the inventory page with its filters, one obligation as
// of a date, the diff the reader asks for, and the problem report that
// changes nothing this screen reads. A different "as of" is a different key.

const detail = {
  id: 'ob-1',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: null,
  instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2', officialRef: 'FFFS 2017:2', name: null, implementsNote: '' },
  regime: { key: 'securities', kind: null, label: 'Securities' },
  bindingLevel: { key: 'authority_regulation', kind: null, label: 'FI regulation' },
  binding: true,
  dutyType: { key: 'governance', kind: null, label: 'Governance' },
  productScope: '',
  triggerFrequency: '',
  retention: '',
  sanctionExposure: '',
  tags: [],
  scope: [],
  inFootprint: true,
  outsideReason: [],
  summary: null,
  translations: [],
  version: null,
  versions: [],
  related: [],
  provenance: { sourceUrl: 'https://www.fi.se/', sourceLabel: 'fi.se', lastVerifiedAt: null, verifiedBy: null, createdAt: '2026-03-12T08:45:03Z', createdOrigin: 'user', createdModel: '' },
};

const diff = { fromVersion: 1, toVersion: 2, fromEffective: null, toEffective: { date: '2026-10-01', precision: 'day' }, language: 'en', isMachine: false, segments: [] };

const instrumentRow = {
  id: 'in-1',
  stableKey: 'fffs-2017-2',
  shortName: 'FFFS 2017:2',
  name: null,
  level: { key: 'authority_regulation', kind: null, label: 'Supervisory regulation' },
  binding: true,
  jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
  authority: null,
  regime: { key: 'securities', kind: null, label: 'Securities' },
  officialRef: 'FFFS 2017:2',
  inForceFrom: null,
  inForceTo: null,
  implementsNote: '',
  obligationCount: 0,
  inFootprint: true,
  lastVerifiedAt: null,
  sourceUrl: 'https://www.fi.se/',
};

const instrumentDetail = { ...instrumentRow, eliUri: '', verifiedBy: null, lineage: [] };

describe('library hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the obligations page with the filters and the page size', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    const { wrapper } = queryWrapper();
    const list = renderHook(() => useObligations({ term: ['service_type:advice'], asOf: '2026-09-16' }), { wrapper });
    await waitFor(() => expect(list.result.current.data).toEqual({ items: [], total: 0 }));
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/obligations', { term: ['service_type:advice'], asOf: '2026-09-16', limit: OBLIGATION_PAGE, offset: 0 }],
    ]);
  });

  it('keys each set of filters separately, so "as of" and "outside the footprint" re-read', () => {
    expect(libraryKeys.obligations({}, 20)).toEqual(['library', 'obligations', { limit: 20 }]);
    expect(libraryKeys.obligations({ asOf: '2026-06-01' }, 20)).not.toEqual(libraryKeys.obligations({ asOf: '2026-10-01' }, 20));
    expect(libraryKeys.obligations({ footprint: 'watched' }, 20)).not.toEqual(libraryKeys.obligations({}, 20));
  });

  it('reads one obligation as of a date, and keys each date separately', async () => {
    const sent = installAdapter(() => ({ status: 200, data: detail }));
    const { wrapper } = queryWrapper();
    const card = renderHook(() => useObligation('ob-1', '2026-06-30'), { wrapper });
    await waitFor(() => expect(card.result.current.data?.stableKey).toBe('obl-research-payments'));
    expect(sent.map((s) => [s.path, s.params])).toEqual([['/api/v1/obligations/ob-1', { asOf: '2026-06-30' }]]);
    expect(libraryKeys.obligation('ob-1', '2026-06-30')).not.toEqual(libraryKeys.obligation('ob-1', '2026-10-01'));
    expect(libraryKeys.obligation('ob-1', '')).toEqual(['library', 'obligation', 'ob-1', '']);
  });

  it('reads the diff only once the reader asks for it', async () => {
    const sent = installAdapter(() => ({ status: 200, data: diff }));
    const { wrapper } = queryWrapper();
    const off = renderHook(() => useObligationDiff('ob-1', 'en', false), { wrapper });
    await waitFor(() => expect(off.result.current.fetchStatus).toBe('idle'));
    expect(sent).toEqual([]);

    const on = renderHook(() => useObligationDiff('ob-1', 'en', true), { wrapper });
    await waitFor(() => expect(on.result.current.data?.toVersion).toBe(2));
    expect(sent.map((s) => [s.path, s.params])).toEqual([['/api/v1/obligations/ob-1/diff', { lang: 'en' }]]);
    expect(libraryKeys.obligationDiff('ob-1', 'en')).not.toEqual(libraryKeys.obligationDiff('ob-1', 'sv'));
  });

  it('files a problem report and invalidates nothing, because it changed no record this screen reads', async () => {
    const sent = installAdapter(() => ({ status: 201, data: { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' } }));
    const { wrapper, queryClient } = queryWrapper();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const report = renderHook(() => useReportObligationProblem('ob-1'), { wrapper });
    report.result.current.mutate({ description: 'The English says annually.', versionNumber: 2, language: 'en' });
    await waitFor(() => expect(report.result.current.data?.status).toBe('open'));
    expect(sent.map((s) => [s.method, s.path])).toEqual([['post', '/api/v1/obligations/ob-1/problem-reports']]);
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('reads the instruments page with the filters and its own page size', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [instrumentRow], total: 1 } }));
    const { wrapper } = queryWrapper();
    const list = renderHook(() => useInstruments({ regime: 'securities' }), { wrapper });
    await waitFor(() => expect(list.result.current.data?.total).toBe(1));
    expect(sent.map((s) => [s.path, s.params])).toEqual([['/api/v1/instruments', { regime: 'securities', limit: INSTRUMENT_PAGE, offset: 0 }]]);
    expect(libraryKeys.instruments({}, 20)).toEqual(['library', 'instruments', { limit: 20 }]);
    expect(libraryKeys.instruments({ footprint: 'watched' }, 20)).not.toEqual(libraryKeys.instruments({}, 20));
  });

  it('reads one instrument, keyed by its own id', async () => {
    const sent = installAdapter(() => ({ status: 200, data: instrumentDetail }));
    const { wrapper } = queryWrapper();
    const card = renderHook(() => useInstrument('in-1'), { wrapper });
    await waitFor(() => expect(card.result.current.data?.stableKey).toBe('fffs-2017-2'));
    expect(sent.map((s) => [s.path])).toEqual([['/api/v1/instruments/in-1']]);
    expect(libraryKeys.instrument('in-1')).not.toEqual(libraryKeys.instrument('in-2'));
  });

  it('files an instrument problem report and invalidates nothing', async () => {
    const sent = installAdapter(() => ({ status: 201, data: { id: 'rep-2', status: 'open', createdAt: '2026-09-21T09:00:00Z' } }));
    const { wrapper, queryClient } = queryWrapper();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const report = renderHook(() => useReportInstrumentProblem('in-1'), { wrapper });
    report.result.current.mutate({ description: 'The in-force date looks wrong.' });
    await waitFor(() => expect(report.result.current.data?.status).toBe('open'));
    expect(sent.map((s) => [s.method, s.path])).toEqual([['post', '/api/v1/instruments/in-1/problem-reports']]);
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('reads the provision tree, keyed by the instrument and the date', async () => {
    const sent = installAdapter(() => ({ status: 200, data: [] }));
    const { wrapper } = queryWrapper();
    const tree = renderHook(() => useInstrumentProvisions('in-1', '2026-09-16'), { wrapper });
    await waitFor(() => expect(tree.result.current.data).toEqual([]));
    expect(sent.map((s) => [s.path, s.params])).toEqual([['/api/v1/instruments/in-1/provisions', { asOf: '2026-09-16' }]]);
    expect(libraryKeys.provisions('in-1', '2026-09-16')).not.toEqual(libraryKeys.provisions('in-1', ''));
  });

  it('reads the provision diff only once the reader asks for it', async () => {
    const sent = installAdapter(() => ({
      status: 200,
      data: { fromVersion: 1, toVersion: 2, fromEffective: null, toEffective: null, language: 'en', isMachine: false, segments: [] },
    }));
    const off = renderHook(() => useProvisionDiff('pr-6', 'en', false), { wrapper: queryWrapper().wrapper });
    await waitFor(() => expect(off.result.current.fetchStatus).toBe('idle'));
    expect(sent).toEqual([]);

    const on = renderHook(() => useProvisionDiff('pr-6', 'en', true), { wrapper: queryWrapper().wrapper });
    await waitFor(() => expect(on.result.current.data?.toVersion).toBe(2));
    expect(sent.map((s) => [s.path, s.params])).toEqual([['/api/v1/provisions/pr-6/diff', { lang: 'en' }]]);
    expect(libraryKeys.provisionDiff('pr-6', 'en')).not.toEqual(libraryKeys.provisionDiff('pr-6', 'sv'));
  });
});
