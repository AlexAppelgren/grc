import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { searchKeys, useSearchResults } from './hooks';

describe('search hooks', () => {
  it('asks nothing while there is no query yet', async () => {
    resetApiForTests();
    tokenStore.set('tok');
    const sent = installAdapter(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    const { wrapper } = queryWrapper();
    renderHook(() => useSearchResults(null), { wrapper });
    await waitFor(() => expect(sent).toHaveLength(0));
  });

  it('reads the results once a query is given', async () => {
    resetApiForTests();
    tokenStore.set('tok');
    const sent = installAdapter(() => ({ status: 200, data: { items: [{ id: 'h-1' }], asOf: '2026-09-20' } }));
    const { wrapper } = queryWrapper();
    const result = renderHook(() => useSearchResults({ q: 'FFFS 2017:2', limit: 20 }), { wrapper });
    await waitFor(() => expect(result.result.current.data?.items).toHaveLength(1));
    expect(sent[0]?.path).toBe('/api/v1/search');
    expect(sent[0]?.body).toEqual({ q: 'FFFS 2017:2', limit: 20 });
  });

  it('keys each request by its whole body, so a narrowed search re-reads', () => {
    expect(searchKeys.results({ q: 'a', limit: 20 })).not.toEqual(searchKeys.results({ q: 'b', limit: 20 }));
    expect(searchKeys.results({ q: 'a', limit: 20 })).toEqual(searchKeys.results({ q: 'a', limit: 20 }));
  });
});
