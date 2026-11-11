import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as library from './api';

// Each wrapper hits its route with its method, its query and its body, and
// returns `.data` as the generated shape (types.ts). The facts a screen may
// not trust as sent are narrowed by the small functions tested last.

describe('library api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('lists obligations with its keys-only query and returns the page as sent', async () => {
    const page = { items: [{ id: 'ob-1' }], total: 1 };
    const sent = installAdapter(() => ({ status: 200, data: page }));
    expect(await library.listObligations({ term: ['regime:securities', 'service_type:advice'], dutyType: 'conduct', asOf: '2026-09-16', limit: 20, offset: 0 })).toEqual(page);
    await library.listObligations();
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

  it('reads one obligation as of a date, and today where the bank is when none or an empty one is given', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'ob-1' } }));
    expect(await library.getObligation('ob-1', '2026-06-30')).toEqual({ id: 'ob-1' });
    await library.getObligation('ob-1');
    await library.getObligation('ob-1', '');
    expect(sent.map((s) => [s.method, s.path, s.params])).toEqual([
      ['get', '/api/v1/obligations/ob-1', { asOf: '2026-06-30' }],
      ['get', '/api/v1/obligations/ob-1', {}],
      ['get', '/api/v1/obligations/ob-1', {}],
    ]);
  });

  it('reads the obligation diff in the language on screen, or with none', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { segments: [] } }));
    await library.getObligationDiff('ob-1', 'en');
    await library.getObligationDiff('ob-1');
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/obligations/ob-1/diff', { lang: 'en' }],
      ['/api/v1/obligations/ob-1/diff', {}],
    ]);
  });

  it('files a problem report with what was on screen, against an obligation or an instrument', async () => {
    const created = { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' };
    const sent = installAdapter(() => ({ status: 201, data: created }));
    expect(await library.reportObligationProblem('ob-1', { description: 'The English says annually.', versionNumber: 2, language: 'en' })).toEqual(created);
    await library.reportInstrumentProblem('in-1', { description: 'The in-force date looks wrong.' });
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([
      ['post', '/api/v1/obligations/ob-1/problem-reports', { description: 'The English says annually.', versionNumber: 2, language: 'en' }],
      ['post', '/api/v1/instruments/in-1/problem-reports', { description: 'The in-force date looks wrong.' }],
    ]);
  });

  it("tags and untags one obligation with the bank's own tag and reads a tag sent without a kind as having none", async () => {
    const sent = installAdapter(() => ({ status: 200, data: { subjectType: 'obligation', subjectId: 'ob-1', tags: [{ key: 'q4', label: 'Q4' }] } }));
    expect(await library.tagObligation('ob-1', 'q4')).toEqual([{ key: 'q4', kind: null, label: 'Q4' }]);
    await library.untagObligation('ob-1', 'q4');
    const body = { tagKey: 'q4', subjectType: 'obligation', subjectId: 'ob-1' };
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([
      ['post', '/api/v1/taggings', body],
      ['post', '/api/v1/taggings/remove', body],
    ]);
  });

  it('previews and commits one tag on many obligations', async () => {
    const outcome = { subjectType: 'obligation', tag: { key: 'q4', kind: null, label: 'Q4' }, gained: { count: 1, ids: ['ob-1'] }, alreadyTagged: { count: 0, ids: [] }, skipped: { count: 2 } };
    const sent = installAdapter(() => ({ status: 200, data: outcome }));
    expect(await library.previewObligationTagging('q4', ['ob-1', 'ob-2'])).toEqual(outcome);
    await library.tagObligations('q4', ['ob-1']);
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([
      ['post', '/api/v1/taggings/preview', { tagKey: 'q4', subjectType: 'obligation', subjectIds: ['ob-1', 'ob-2'] }],
      ['post', '/api/v1/taggings/batch', { tagKey: 'q4', subjectType: 'obligation', subjectIds: ['ob-1'] }],
    ]);
  });

  it('lists instruments with their filters and reads one instrument', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    await library.listInstruments({ regime: 'securities', footprint: 'watched', limit: 20, offset: 0 });
    await library.getInstrument('in-1');
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/instruments'],
      ['get', '/api/v1/instruments/in-1'],
    ]);
    expect(sent[0]?.params).toEqual({ regime: 'securities', footprint: 'watched', limit: 20, offset: 0 });
  });

  it('reads the provision tree as of a date, and the diff between two provision versions', async () => {
    const sent = installAdapter(() => ({ status: 200, data: [] }));
    expect(await library.listInstrumentProvisions('in-1', '2026-09-16')).toEqual([]);
    await library.listInstrumentProvisions('in-1');
    await library.getProvisionDiff('pr-6', 'en');
    await library.getProvisionDiff('pr-6', '');
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/instruments/in-1/provisions', { asOf: '2026-09-16' }],
      ['/api/v1/instruments/in-1/provisions', {}],
      ['/api/v1/provisions/pr-6/diff', { lang: 'en' }],
      ['/api/v1/provisions/pr-6/diff', {}],
    ]);
  });
});

describe('the narrowings', () => {
  it('reads a compliance status as a pill only when its kind is one of the four the tone map knows', () => {
    expect(library.complianceOf(null)).toBeNull();
    expect(library.complianceOf(undefined)).toBeNull();
    expect(library.complianceOf({ key: 'partly', kind: 'partly', label: 'Partly compliant' })).toEqual({ key: 'partly', kind: 'partly', label: 'Partly compliant' });
    expect(library.complianceOf({ key: 'invented', kind: 'something_else', label: 'Invented' })).toBeNull();
    expect(library.complianceOf({ key: 'invented', kind: null, label: 'Invented' })).toBeNull();
  });

  it('keeps a diff operation it has no colour for as plain text', () => {
    expect(['equal', 'insert', 'delete', 'reworded'].map(library.diffOpOf)).toEqual(['equal', 'insert', 'delete', 'equal']);
  });

  it('reads a lineage link as outgoing only when the server says so', () => {
    expect(['outgoing', 'incoming', 'sideways'].map((direction) => library.lineageDirectionOf({ direction }))).toEqual(['outgoing', 'incoming', 'incoming']);
  });
});
