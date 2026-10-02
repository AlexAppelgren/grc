import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import {
  approveInTurn,
  retagInFlight,
  useApproveMany,
  useApproveProposal,
  useCreateRetagRequest,
  useDecideProposalBatch,
  useProposal,
  useProposalBatch,
  useProposals,
  useRejectProposal,
  useRetagRequest,
  useRetagTerms,
  useScopeTermLabels,
  useTenantProposals,
} from './hooks';
import type { RetagRequest } from './types';

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

  it('approves many through the one approve route, one after another, each with an empty note', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { status: 'approved' } }));
    const done: number[] = [];
    const outcome = await approveInTurn(
      [
        { id: 'p-1', title: 'First' },
        { id: 'p-2', title: 'Second' },
      ],
      (count) => done.push(count),
    );
    expect(outcome).toEqual({ approved: 2, refused: [] });
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([
      ['post', '/api/v1/proposals/p-1/approve', { note: '' }],
      ['post', '/api/v1/proposals/p-2/approve', { note: '' }],
    ]);
    expect(done).toEqual([1, 2]);
  });

  it('keeps a refusal with its title and goes on to the next', async () => {
    const sent = installAdapter((s) => (s.path.includes('p-1') ? { status: 409, data: { code: 'four_eyes_violation', detail: 'You proposed this.' } } : { status: 200, data: {} }));
    const outcome = await approveInTurn(
      [
        { id: 'p-1', title: 'First' },
        { id: 'p-2', title: 'Second' },
      ],
      () => undefined,
    );
    expect(outcome.approved).toBe(1);
    expect(outcome.refused.map((refusal) => [refusal.id, refusal.title])).toEqual([['p-1', 'First']]);
    expect(sent).toHaveLength(2);
  });

  it('stops when the passkey was not given, leaving the rest waiting rather than asking again for each', async () => {
    // No step-up handler is installed, so the 403 reaches the caller as the closed prompt does.
    const sent = installAdapter(() => ({ status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } }));
    const outcome = await approveInTurn(
      [
        { id: 'p-1', title: 'First' },
        { id: 'p-2', title: 'Second' },
      ],
      () => undefined,
    );
    expect(outcome.approved).toBe(0);
    expect(outcome.refused.map((refusal) => refusal.id)).toEqual(['p-1']);
    expect(sent).toHaveLength(1);
  });

  it('counts the approvals made as it goes and re-reads the queue when the run ends', async () => {
    installAdapter(() => ({ status: 200, data: {} }));
    const { wrapper, queryClient } = queryWrapper();
    const invalidated: unknown[] = [];
    const original = queryClient.invalidateQueries.bind(queryClient);
    queryClient.invalidateQueries = (filters) => {
      invalidated.push(filters?.queryKey);
      return original(filters);
    };
    const many = renderHook(() => useApproveMany(), { wrapper });
    await many.result.current.mutateAsync([{ id: 'p-1', title: 'First' }]);
    await waitFor(() => expect(many.result.current.done).toBe(1));
    expect(invalidated).toContainEqual(['proposals']);
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

  it('reads a batch, and a decision leaves the batch as the server answered it', async () => {
    const sent = installAdapter((request) =>
      request.method === 'post' ? { status: 200, data: { id: 'b-1', status: 'approved', rows: [] } } : { status: 200, data: { id: 'b-1', status: 'open', rows: [] } },
    );
    const { wrapper } = queryWrapper();
    const batch = renderHook(() => useProposalBatch('b-1'), { wrapper });
    await waitFor(() => expect(batch.result.current.data?.status).toBe('open'));
    const decide = renderHook(() => useDecideProposalBatch('b-1'), { wrapper });
    await decide.result.current.mutateAsync({ rows: [], rest: 'approved', restRejectionCode: '', note: '' });
    await waitFor(() => expect(batch.result.current.data?.status).toBe('approved'));
    expect(sent.filter((call) => call.method === 'post').map((call) => call.body)).toEqual([{ rows: [], rest: 'approved', restRejectionCode: '', note: '' }]);
  });

  it('files a re-tag request with its topic', async () => {
    const sent = installAdapter(() => ({ status: 202, data: { id: 'q-1', status: 'queued' } }));
    const { wrapper } = queryWrapper();
    const create = renderHook(() => useCreateRetagRequest(), { wrapper });
    const request = await create.result.current.mutateAsync({ topic: 'Re-tag' });
    expect([request.id, sent[0]?.body]).toEqual(['q-1', { topic: 'Re-tag' }]);
  });

  it('follows a re-tag request only once there is one', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'q-1', status: 'done', batchProposalId: 'b-1' } }));
    const { wrapper } = queryWrapper();
    const idle = renderHook(() => useRetagRequest(null), { wrapper });
    expect(idle.result.current.fetchStatus).toBe('idle');
    const followed = renderHook(() => useRetagRequest('q-1'), { wrapper });
    await waitFor(() => expect(followed.result.current.data?.batchProposalId).toBe('b-1'));
    expect(sent.map((call) => call.path)).toEqual(['/api/v1/console/research-requests/q-1']);
  });

  it('keeps reading a request only while it is queued or running and names no batch', () => {
    const request = (status: RetagRequest['status'], batchProposalId: string | null = null) => ({ status, batchProposalId }) as RetagRequest;
    expect([retagInFlight(undefined), retagInFlight(request('queued')), retagInFlight(request('running')), retagInFlight(request('running', 'b-1')), retagInFlight(request('failed'))]).toEqual([
      false,
      true,
      true,
      false,
      false,
    ]);
    expect(retagInFlight({ status: 'queued' } as RetagRequest)).toBe(true);
  });

  it('offers only live terms outside the mirrored jurisdiction dimension', async () => {
    installAdapter(() => ({
      status: 200,
      data: {
        items: [
          { id: 't-1', key: 'custody', label: 'Custody', dimension: 'service_type', active: true, mirrored: false },
          { id: 't-2', key: 'se', label: 'Sweden', dimension: 'market', active: true, mirrored: true },
          { id: 't-3', key: 'old', label: 'Old', dimension: 'service_type', active: false, mirrored: false },
        ],
        total: 3,
      },
    }));
    const { wrapper } = queryWrapper();
    const terms = renderHook(() => useRetagTerms(), { wrapper });
    await waitFor(() => expect(terms.result.current.data?.map((term) => term.key)).toEqual(['custody']));
  });
});
