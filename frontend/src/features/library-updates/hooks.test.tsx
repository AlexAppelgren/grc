import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { useLibraryUpdates, useMarkVisited } from './hooks';

describe('library-updates hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the feed for one query', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { since: '2026-09-12', days: [], total: 0 } }));
    const { wrapper } = queryWrapper();
    const feed = renderHook(() => useLibraryUpdates({}), { wrapper });
    await waitFor(() => expect(feed.result.current.data?.since).toBe('2026-09-12'));
    expect(sent[0]?.path).toBe('/api/v1/library-updates');
  });

  it('marking visited calls the route', async () => {
    const sent = installAdapter(() => ({ status: 204 }));
    const { wrapper } = queryWrapper();
    const visit = renderHook(() => useMarkVisited(), { wrapper });
    await visit.result.current.mutateAsync();
    expect(sent[0]?.path).toBe('/api/v1/me/visit');
  });
});
