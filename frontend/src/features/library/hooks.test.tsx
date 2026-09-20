import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { libraryKeys, OBLIGATION_PAGE, useObligations } from './hooks';

// The inventory's one read: it hits /obligations with the page size and the
// filters it was given, and a different "as of" is a different query key.

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
    expect(libraryKeys.obligations({ outsideFootprint: true }, 20)).not.toEqual(libraryKeys.obligations({}, 20));
  });
});
