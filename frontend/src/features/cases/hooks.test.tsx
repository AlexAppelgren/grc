import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { homeKeys } from '@/features/home/hooks';
import { useChange, watchKeys } from '@/features/watch/hooks';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import {
  caseKeys,
  staleWriteOf,
  useAddAction,
  useAddEvidence,
  useApproveSignoff,
  useCaseActions,
  useCaseEvidence,
  useCaseFile,
  useCloseWithoutAction,
  useDeleteAction,
  useDismissChange,
  useReloadCase,
  useRemoveEvidence,
  useRequestSignoff,
  useRestoreChange,
  useSaveAssessment,
  useSendBackSignoff,
  useStartAssessment,
  useTriageChange,
  useUpdateAction,
} from './hooks';

// The case panels' reads and writes. Every write re-reads what it can move;
// a write somebody else's overtook (409 `stale_write`) touches nothing and
// offers a reload, never a merge.

const ASSESSMENT = { applies: 'yes' as const, why: 'Ours.', whatMustChange: 'Criteria.', internalDeadline: null, effort: null, subStatus: null };

describe('cases hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the actions, the evidence and the case file of a case, and nothing while disabled', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.path.endsWith('case-file') ? 'Case file' : { items: [], total: 0 } }));
    const { wrapper } = queryWrapper();
    const actions = renderHook(() => useCaseActions('c-1'), { wrapper });
    const evidence = renderHook(() => useCaseEvidence('c-1'), { wrapper });
    const file = renderHook(() => useCaseFile('c-1'), { wrapper });
    renderHook(() => useCaseFile('c-2', false), { wrapper });
    await waitFor(() => expect(file.result.current.data).toBe('Case file'));
    await waitFor(() => expect(actions.result.current.data?.total).toBe(0));
    await waitFor(() => expect(evidence.result.current.data?.total).toBe(0));
    expect(sent.map((s) => s.path).sort()).toEqual(['/api/v1/changes/c-1/actions', '/api/v1/changes/c-1/case-file', '/api/v1/changes/c-1/evidence']);
    expect(caseKeys.actions('c-1').slice(0, 2)).toEqual(caseKeys.change('c-1'));
  });

  it('a successful move re-reads the change page, the case’s own lists and the home screens', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.method === 'get' ? { id: 'c-1', case: { version: 2 } } : { id: 'case-1', version: 3 } }));
    const { wrapper, queryClient } = queryWrapper();
    const invalidated = vi.spyOn(queryClient, 'invalidateQueries');
    const change = renderHook(() => useChange('c-1'), { wrapper });
    await waitFor(() => expect(change.result.current.data).toBeDefined());
    const triage = renderHook(() => useTriageChange('c-1', 2), { wrapper });
    await triage.result.current.mutateAsync({ urgency: 'act_now', ownerId: 'u-1' });
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/changes/c-1' && s.method === 'get')).toHaveLength(2));
    expect(invalidated.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([watchKeys.all, caseKeys.change('c-1'), homeKeys.home]);
  });

  it('a stale write is refused whole: the cache is untouched, the current version is read off the answer, and the reload re-reads', async () => {
    const sent = installAdapter((s) =>
      s.method === 'put'
        ? { status: 409, data: { status: 409, code: 'stale_write', title: 'Conflict', detail: 'Someone else saved first.', currentVersion: 5 } }
        : { status: 200, data: { id: 'c-1', case: { version: 5 } } },
    );
    const { wrapper, queryClient } = queryWrapper();
    const change = renderHook(() => useChange('c-1'), { wrapper });
    await waitFor(() => expect(change.result.current.data).toBeDefined());
    const before = queryClient.getQueryData(watchKeys.change('c-1'));

    const save = renderHook(() => useSaveAssessment('c-1', 4), { wrapper });
    const error = await save.result.current.mutateAsync(ASSESSMENT).then(
      () => null,
      (e: unknown) => e,
    );
    expect(staleWriteOf(error)).toEqual({ currentVersion: 5 });
    expect(queryClient.getQueryData(watchKeys.change('c-1'))).toBe(before);
    expect(queryClient.getQueryState(watchKeys.change('c-1'))?.isInvalidated).toBe(false);
    expect(sent.filter((s) => s.method === 'get')).toHaveLength(1);

    const reload = renderHook(() => useReloadCase('c-1'), { wrapper });
    await reload.result.current();
    expect(sent.filter((s) => s.method === 'get')).toHaveLength(2);
  });

  it('reads a stale write without a version as one, and anything else as not one', () => {
    const answer = (data: unknown) => ({ isAxiosError: true, response: { status: 409, data } });
    expect(staleWriteOf(answer({ code: 'stale_write' }))).toEqual({ currentVersion: null });
    expect(staleWriteOf(answer({ code: 'invalid_transition', currentVersion: 5 }))).toBeNull();
    expect(staleWriteOf(new Error('boom'))).toBeNull();
  });

  it('sends every other write to its own route', async () => {
    const sent = installAdapter(() => ({ status: 200, data: {} }));
    const { wrapper } = queryWrapper();
    const hooks = renderHook(
      () => ({
        dismiss: useDismissChange('c-1', 1),
        restore: useRestoreChange('c-1', 2),
        start: useStartAssessment('c-1', 2),
        close: useCloseWithoutAction('c-1', 2),
        add: useAddAction('c-1', 3),
        update: useUpdateAction('c-1'),
        remove: useDeleteAction('c-1'),
        attach: useAddEvidence('c-1'),
        detach: useRemoveEvidence('c-1'),
        request: useRequestSignoff('c-1', 4),
        approve: useApproveSignoff('c-1', 5),
        sendBack: useSendBackSignoff('c-1', 5),
      }),
      { wrapper },
    );
    const h = hooks.result.current;
    await h.dismiss.mutateAsync({ reasonKey: 'out_of_scope' });
    await h.restore.mutateAsync();
    await h.start.mutateAsync();
    await h.close.mutateAsync({ reasonKey: 'no_action', note: 'Covered.' });
    await h.add.mutateAsync({ title: 'Write the criteria', ownerId: 'u-1', dueDate: '2026-10-10' });
    await h.update.mutateAsync({ action: { id: 'a-1', version: 2 }, patch: { done: true } });
    await h.remove.mutateAsync({ id: 'a-1', version: 3 });
    await h.attach.mutateAsync({ kind: 'reference', name: 'Board minutes 2026-09' });
    await h.detach.mutateAsync('e-1');
    await h.request.mutateAsync();
    await h.approve.mutateAsync({ note: '' });
    await h.sendBack.mutateAsync({ note: 'Needs the committee date.' });
    expect(sent.map((s) => `${s.method} ${s.path}`)).toEqual([
      'post /api/v1/changes/c-1/dismiss',
      'post /api/v1/changes/c-1/restore',
      'post /api/v1/changes/c-1/assessment/start',
      'post /api/v1/changes/c-1/close',
      'post /api/v1/changes/c-1/actions',
      'patch /api/v1/actions/a-1',
      'delete /api/v1/actions/a-1',
      'post /api/v1/changes/c-1/evidence',
      'delete /api/v1/evidence/e-1',
      'post /api/v1/changes/c-1/signoff/request',
      'post /api/v1/changes/c-1/signoff/approve',
      'post /api/v1/changes/c-1/signoff/send-back',
    ]);
  });
});
