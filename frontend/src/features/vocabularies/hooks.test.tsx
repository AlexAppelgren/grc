import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { useCreateValue, useDeclineSuggestion, useMergeValue, usePreviewMerge, useReorderValues, useRetireValue, useSuggestValue, useUpdateValue, useVocabularies, useVocabularyValues, vocabularyKeys } from './hooks';

// Every hook hits its route and invalidates the list it changed, so pickers
// and the admin screen read the same rows next.

const SUGGESTION = { id: 's1', list: 'tenant_tag', key: 'c', labels: { en: 'C' }, usageNote: '', suggestedBy: null, status: 'pending', createdAt: '2026-09-17T08:00:00Z' };

describe('vocabularies hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the lists and one list, active or with retired values, and can be disabled', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.path === '/api/v1/vocab' ? { items: [{ list: 'flag', tier: 2, kind: null, kinds: [], count: 6, retiredCount: 0, proposable: true }], total: 1 } : { items: [{ key: 'ai' }], total: 1 } }));
    const { wrapper } = queryWrapper();
    const lists = renderHook(() => useVocabularies(), { wrapper });
    await waitFor(() => expect(lists.result.current.data).toEqual([{ list: 'flag', tier: 'library', kind: null, count: 6, retiredCount: 0 }]));
    const values = renderHook(() => useVocabularyValues('flag'), { wrapper });
    await waitFor(() => expect(values.result.current.data).toEqual([{ key: 'ai' }]));
    const all = renderHook(() => useVocabularyValues('flag', true), { wrapper });
    await waitFor(() => expect(all.result.current.data).toEqual([{ key: 'ai' }]));
    const off = renderHook(() => useVocabularyValues('flag', false, false), { wrapper });
    expect(off.result.current.fetchStatus).toBe('idle');
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/vocab', null],
      ['/api/v1/vocab/flag', {}],
      ['/api/v1/vocab/flag', { includeRetired: true }],
    ]);
    expect(vocabularyKeys.values('flag', true)).toEqual(['vocab', 'flag', 'all']);
  });

  it('writes through every mutation and refreshes the list afterwards', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'get' ? 200 : s.path.endsWith('/suggest') ? 201 : 200, data: s.method === 'get' ? [] : s.path.endsWith('/suggest') || s.path.endsWith('/decline') ? SUGGESTION : s.path.endsWith('/merge') ? { from: 'a', into: 'b', repointed: 2, usageCount: 2, dryRun: false } : { key: 'a', proposal: { id: 'p1' } } }));
    const { wrapper } = queryWrapper();
    const values = renderHook(() => useVocabularyValues('tenant_tag'), { wrapper });
    await waitFor(() => expect(values.result.current.data).toEqual([]));

    await renderHook(() => useCreateValue('tenant_tag'), { wrapper }).result.current.mutateAsync({ labels: { en: 'A' } });
    await renderHook(() => useUpdateValue('tenant_tag'), { wrapper }).result.current.mutateAsync({ key: 'a', body: { usageNote: 'n' }, version: 2 });
    await renderHook(() => useReorderValues('tenant_tag'), { wrapper }).result.current.mutateAsync(['b', 'a']);
    await renderHook(() => useRetireValue('tenant_tag'), { wrapper }).result.current.mutateAsync({ key: 'a', confirm: true });
    expect(await renderHook(() => usePreviewMerge('tenant_tag'), { wrapper }).result.current.mutateAsync({ key: 'a', into: 'b' })).toEqual({ from: 'a', into: 'b', moved: 2 });
    await renderHook(() => useMergeValue('tenant_tag'), { wrapper }).result.current.mutateAsync({ key: 'a', into: 'b' });
    expect(await renderHook(() => useSuggestValue('tenant_tag'), { wrapper }).result.current.mutateAsync({ labels: { en: 'C' } })).toEqual({ outcome: 'suggested', suggestion: expect.objectContaining({ id: 's1', key: 'c' }) });
    expect(await renderHook(() => useDeclineSuggestion('tenant_tag'), { wrapper }).result.current.mutateAsync('s1')).toEqual(expect.objectContaining({ id: 's1' }));

    await waitFor(() => expect(sent.filter((s) => s.method === 'get' && s.path === '/api/v1/vocab/tenant_tag').length).toBeGreaterThanOrEqual(2));
    expect(sent.filter((s) => s.method !== 'get').map((s) => [s.method, s.path, s.params])).toEqual([
      ['post', '/api/v1/vocab/tenant_tag', null],
      ['patch', '/api/v1/vocab/tenant_tag/a', null],
      ['post', '/api/v1/vocab/tenant_tag/reorder', null],
      ['post', '/api/v1/vocab/tenant_tag/a/retire', null],
      ['post', '/api/v1/vocab/tenant_tag/a/merge', { dryRun: true }],
      ['post', '/api/v1/vocab/tenant_tag/a/merge', null],
      ['post', '/api/v1/vocab/tenant_tag/suggest', null],
      ['post', '/api/v1/vocab/tenant_tag/suggestions/s1/decline', null],
    ]);
  });
});
