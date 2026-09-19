import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import {
  footprintKeys,
  REQUEST_HISTORY_PAGE,
  useApproveFootprintRequest,
  useCreateFootprintRequest,
  useDimensions,
  useFootprint,
  useFootprintRequests,
  useRejectFootprintRequest,
  useSuggestTerm,
  useTerms,
  useWithdrawFootprintRequest,
} from './hooks';

// Every hook hits its route; a decision refreshes the footprint and the
// request history together.

describe('footprint hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the footprint, the requests, the terms and the dimensions', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.path.endsWith('/footprint') ? { dimensions: [], pendingRequest: null } : s.path.endsWith('/requests') ? { items: [], total: 0 } : { items: [], total: 0 } }));
    const { wrapper } = queryWrapper();
    const fp = renderHook(() => useFootprint(), { wrapper });
    await waitFor(() => expect(fp.result.current.data).toEqual({ dimensions: [], pendingRequest: null }));
    const requests = renderHook(() => useFootprintRequests(), { wrapper });
    await waitFor(() => expect(requests.result.current.data).toEqual({ items: [], total: 0 }));
    const terms = renderHook(() => useTerms('service_type'), { wrapper });
    await waitFor(() => expect(terms.result.current.data).toEqual([]));
    const all = renderHook(() => useTerms(), { wrapper });
    await waitFor(() => expect(all.result.current.data).toEqual([]));
    const dims = renderHook(() => useDimensions(), { wrapper });
    await waitFor(() => expect(dims.result.current.data).toEqual([]));
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/tenant/footprint', null],
      ['/api/v1/tenant/footprint/requests', { limit: REQUEST_HISTORY_PAGE, offset: 0 }],
      ['/api/v1/taxonomy/terms', { dimension: 'service_type' }],
      ['/api/v1/taxonomy/terms', {}],
      ['/api/v1/taxonomy/dimensions', null],
    ]);
    expect(footprintKeys.terms()).toEqual(['taxonomy', 'terms', 'all']);
  });

  it('creates, approves, rejects and withdraws, refreshing the footprint after each', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'get' ? 200 : 201, data: s.method === 'get' ? (s.path.endsWith('/requests') ? { items: [], total: 0 } : { dimensions: [], pendingRequest: null }) : { id: 'r1', status: 'pending' } }));
    const { wrapper } = queryWrapper();
    const fp = renderHook(() => useFootprint(), { wrapper });
    await waitFor(() => expect(fp.result.current.data).toBeDefined());
    await renderHook(() => useCreateFootprintRequest(), { wrapper }).result.current.mutateAsync({ adds: [], removes: [{ dimension: 'service_type', key: 'advice' }] });
    await renderHook(() => useApproveFootprintRequest(), { wrapper }).result.current.mutateAsync({ requestId: 'r1', version: 1 });
    await renderHook(() => useRejectFootprintRequest(), { wrapper }).result.current.mutateAsync({ requestId: 'r1', body: { note: 'no' } });
    await renderHook(() => useWithdrawFootprintRequest(), { wrapper }).result.current.mutateAsync({ requestId: 'r1' });
    expect(await renderHook(() => useSuggestTerm(), { wrapper }).result.current.mutateAsync({ dimension: 'channel', labels: { en: 'Robo' } })).toEqual({ id: 'r1', kind: '', status: 'pending', title: '' });
    await waitFor(() => expect(sent.filter((s) => s.method === 'get' && s.path === '/api/v1/tenant/footprint').length).toBeGreaterThanOrEqual(2));
    expect(sent.filter((s) => s.method !== 'get').map((s) => [s.method, s.path])).toEqual([
      ['post', '/api/v1/tenant/footprint/requests'],
      ['post', '/api/v1/tenant/footprint/requests/r1/approve'],
      ['post', '/api/v1/tenant/footprint/requests/r1/reject'],
      ['post', '/api/v1/tenant/footprint/requests/r1/withdraw'],
      ['post', '/api/v1/taxonomy/terms'],
    ]);
  });
});
