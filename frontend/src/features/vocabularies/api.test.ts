import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as vocab from './api';

// Each wrapper hits its route with its method, body or query and returns
// `.data`; a 202 becomes a `proposed` outcome carrying the proposal.

const row = { key: 'custody', kind: null, label: 'Custody', labels: { en: 'Custody' }, usageNote: '', sortOrder: 1, active: true, isSystem: false, isDefault: false, usageCount: 4, extra: {} };

describe('vocabularies api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('itemsOf accepts a page or a bare array', () => {
    expect(vocab.itemsOf({ items: [1, 2], total: 2 })).toEqual([1, 2]);
    expect(vocab.itemsOf([3])).toEqual([3]);
    expect(vocab.itemsOf(null)).toEqual([]);
    expect(vocab.itemsOf(undefined)).toEqual([]);
  });

  it('lists the lists and one list, with the retired flag as a query', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.path === '/api/v1/vocab' ? { items: [{ list: 'tenant_tag', tier: 3, kind: null, kinds: [], count: 6, retiredCount: 1, proposable: false }], total: 1 } : [row] }));
    expect(await vocab.listVocabularies()).toEqual([{ list: 'tenant_tag', tier: 'tenant', kind: null, count: 6, retiredCount: 1 }]);
    expect(vocab.tierOf(2)).toBe('library');
    expect(vocab.tierOf('library')).toBe('library');
    expect(vocab.tierOf(3)).toBe('tenant');
    expect(await vocab.listValues('tenant_tag')).toEqual([row]);
    expect(await vocab.listValues('tenant_tag', { includeRetired: true })).toEqual([row]);
    expect(sent.map((s) => [s.method, s.path, s.params, s.authorization])).toEqual([
      ['get', '/api/v1/vocab', null, 'Bearer tok'],
      ['get', '/api/v1/vocab/tenant_tag', {}, 'Bearer tok'],
      ['get', '/api/v1/vocab/tenant_tag', { includeRetired: true }, 'Bearer tok'],
    ]);
  });

  it('creates, updates with If-Match, reorders, retires and merges a tenant value', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'post' && s.path === '/api/v1/vocab/tenant_tag' ? 201 : 200, data: s.path.endsWith('/merge') ? { from: 'custody_svcs', into: 'custody', repointed: 1, usageCount: 1, dryRun: s.params !== null } : s.path.endsWith('/retire') ? { key: 'legacy', active: false, usageCount: 2 } : row }));
    expect(await vocab.createValue('tenant_tag', { labels: { en: 'Custody' }, usageNote: 'x' })).toEqual({ outcome: 'applied', result: row });
    expect(await vocab.updateValue('tenant_tag', 'custody', { labels: { en: 'Custody services' } }, 3)).toEqual({ outcome: 'applied', result: row });
    await vocab.updateValue('tenant_tag', 'custody', { usageNote: 'y' });
    await vocab.reorderValues('tenant_tag', ['custody', 'advice']);
    expect(await vocab.retireValue('tenant_tag', 'legacy', true)).toEqual({ outcome: 'applied', result: { key: 'legacy', active: false, usageCount: 2 } });
    expect(await vocab.previewMerge('tenant_tag', 'custody_svcs', 'custody')).toEqual({ from: 'custody_svcs', into: 'custody', moved: 1 });
    expect(await vocab.mergeValue('tenant_tag', 'custody_svcs', 'custody')).toEqual({ outcome: 'applied', result: { from: 'custody_svcs', into: 'custody', moved: 1 } });
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['post', '/api/v1/vocab/tenant_tag'],
      ['patch', '/api/v1/vocab/tenant_tag/custody'],
      ['patch', '/api/v1/vocab/tenant_tag/custody'],
      ['post', '/api/v1/vocab/tenant_tag/reorder'],
      ['post', '/api/v1/vocab/tenant_tag/legacy/retire'],
      ['post', '/api/v1/vocab/tenant_tag/custody_svcs/merge'],
      ['post', '/api/v1/vocab/tenant_tag/custody_svcs/merge'],
    ]);
    expect(sent[0]?.body).toEqual({ labels: { en: 'Custody' }, usageNote: 'x' });
    expect(sent[3]?.body).toEqual({ keys: ['custody', 'advice'] });
    expect(sent[4]?.body).toEqual({ confirm: true });
    expect(sent[5]?.params).toEqual({ dryRun: true });
    expect(sent[6]?.params).toBeNull();
    expect(sent[6]?.body).toEqual({ into: 'custody' });
  });

  it('turns a 202 on a library list into a proposed outcome, nested or flat', async () => {
    let flat = false;
    installAdapter(() => ({ status: 202, data: flat ? { id: 'p2', kind: 'vocabulary_relabel', status: 'open', title: 'Rename' } : { proposal: { id: 'p1', kind: 'vocabulary_create', status: 'open', title: 'Add "Client money"' } } }));
    expect(await vocab.createValue('flag', { labels: { en: 'Client money' } })).toEqual({ outcome: 'proposed', proposal: { id: 'p1', kind: 'vocabulary_create', status: 'open', title: 'Add "Client money"' } });
    flat = true;
    expect(await vocab.updateValue('flag', 'ai', { labels: { en: 'Artificial intelligence' } })).toEqual({ outcome: 'proposed', proposal: { id: 'p2', kind: 'vocabulary_relabel', status: 'open', title: 'Rename' } });
    expect(await vocab.retireValue('flag', 'ai', true)).toMatchObject({ outcome: 'proposed' });
    expect(await vocab.mergeValue('flag', 'ai', 'ml')).toMatchObject({ outcome: 'proposed' });
  });

  it('suggests a value and reads the proposal back, tolerating an empty body', async () => {
    const sent = installAdapter((s) => ({ status: 201, data: s.path.endsWith('/suggest') ? { proposal: { id: 'p3', kind: 'term_create', status: 'open', title: 'T+1' } } : null }));
    expect(await vocab.suggestValue('flag', { labels: { en: 'T+1' } })).toEqual({ id: 'p3', kind: 'term_create', status: 'open', title: 'T+1' });
    expect(sent[0]?.body).toEqual({ labels: { en: 'T+1' } });
    installAdapter(() => ({ status: 202, data: 'accepted' }));
    expect(await vocab.createValue('flag', { labels: { en: 'X' } })).toEqual({ outcome: 'proposed', proposal: { id: '', kind: '', status: '', title: '' } });
  });
});
