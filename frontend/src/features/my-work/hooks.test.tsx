import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { MY_WORK_PAGE, myWorkKeys, useMyWork } from './hooks';

// My work is one read per view, the largest page at a time, and "Show more"
// asks for the rows after the ones already read.

const COUNTS = { overdue: 0, dueSoon: 0, aware: 0, open: 0 };

describe('useMyWork', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the view it is given, then the next page while rows remain', async () => {
    const sent = installAdapter((s) => ({
      status: 200,
      data: { scope: 'unit', unit: 'unit-1', counts: COUNTS, permissionLimited: [], items: (s.params as { offset?: number } | null)?.offset === 0 ? [{}, {}] : [{}], total: 3 },
    }));
    const { wrapper } = queryWrapper();
    const { result } = renderHook(() => useMyWork({ scope: 'unit', unit: 'unit-1' }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(true);
    await act(() => result.current.fetchNextPage());
    await waitFor(() => expect(result.current.hasNextPage).toBe(false));
    expect(sent.map((s) => [s.method, s.path, s.params])).toEqual([
      ['get', '/api/v1/me/work', { scope: 'unit', unit: 'unit-1', limit: MY_WORK_PAGE, offset: 0 }],
      ['get', '/api/v1/me/work', { scope: 'unit', unit: 'unit-1', limit: MY_WORK_PAGE, offset: 2 }],
    ]);
    expect(myWorkKeys.scope({ scope: 'mine' })).toEqual(['my-work', { scope: 'mine' }]);
  });
});
