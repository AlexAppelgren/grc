import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { useApproveProposal, useProposal, useProposals, useRejectProposal, useScopeTermLabels, useTenantProposals } from './hooks';

describe('proposals hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the queue for one status', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [{ id: 'p-1' }], total: 1 } }));
    const { wrapper } = queryWrapper();
    const list = renderHook(() => useProposals({ status: 'open' }), { wrapper });
    await waitFor(() => expect(list.result.current.data?.total).toBe(1));
    expect(sent[0]?.params).toEqual({ status: 'open' });
  });

  it('reads one proposal by id', async () => {
    installAdapter(() => ({ status: 200, data: { id: 'p-1', status: 'open' } }));
    const { wrapper } = queryWrapper();
    const detail = renderHook(() => useProposal('p-1'), { wrapper });
    await waitFor(() => expect(detail.result.current.data?.id).toBe('p-1'));
  });

  it('approving invalidates the queue and the proposal it decided', async () => {
    const sent = installAdapter((_, index) => (index === 0 ? { status: 200, data: { id: 'p-1', status: 'approved' } } : { status: 200, data: { id: 'p-1', status: 'approved' } }));
    const { wrapper } = queryWrapper();
    const approve = renderHook(() => useApproveProposal('p-1'), { wrapper });
    await approve.result.current.mutateAsync({ note: '' });
    expect(sent[0]?.path).toBe('/api/v1/proposals/p-1/approve');
  });

  it('rejecting sends the reason and the note', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'p-1', status: 'rejected' } }));
    const { wrapper } = queryWrapper();
    const reject = renderHook(() => useRejectProposal('p-1'), { wrapper });
    await reject.result.current.mutateAsync({ rejectionCode: 'wrong_fact', note: 'Not right' });
    expect(sent[0]?.body).toEqual({ rejectionCode: 'wrong_fact', note: 'Not right' });
  });

  it('resolves scope term labels per dimension, and leaves the ref as its own label until they answer', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [{ id: 't-1', key: 'advice', label: 'Advice', kind: null, dimension: 'service_type' }], total: 1 } }));
    const { wrapper } = queryWrapper();
    const scope = renderHook(() => useScopeTermLabels(['service_type:advice']), { wrapper });
    expect(scope.result.current.labelOf('service_type:advice')).toBe('service_type:advice');
    await waitFor(() => expect(scope.result.current.isPending).toBe(false));
    expect(scope.result.current.labelOf('service_type:advice')).toBe('Advice');
    expect(sent[0]?.params).toEqual({ dimension: 'service_type' });
  });

  it('asks for no dimension, and answers every ref unresolved, when there are no refs', () => {
    installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    const { wrapper } = queryWrapper();
    const scope = renderHook(() => useScopeTermLabels([]), { wrapper });
    expect(scope.result.current.isPending).toBe(false);
    expect(scope.result.current.labelOf('x:y')).toBe('x:y');
  });

  it('reads this tenant\'s own pending proposals when enabled, and not when it is not', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [{ id: 'p-1' }], total: 1 } }));
    const { wrapper } = queryWrapper();
    const disabled = renderHook(() => useTenantProposals({ targetList: 'flag' }, false), { wrapper });
    expect(disabled.result.current.fetchStatus).toBe('idle');
    const enabled = renderHook(() => useTenantProposals({ targetList: 'flag' }, true), { wrapper });
    await waitFor(() => expect(enabled.result.current.data?.total).toBe(1));
    expect(sent[0]?.path).toBe('/api/v1/tenant/proposals');
  });
});
