import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import {
  participantKeys,
  useAddCaseParticipant,
  useAddObligationParticipant,
  useCaseParticipants,
  useObligationParticipants,
  usePeople,
  useRemoveCaseParticipant,
  useRemoveObligationParticipant,
  useTeams,
} from './hooks';

// The list is keyed by the obligation; every write refetches it, a refused
// one included; the picker's lists wait until the picker opens.

describe('participant hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the picker lists only while enabled', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.path.endsWith('people') ? [] : { items: [], total: 0 } }));
    const { wrapper } = queryWrapper();
    const people = renderHook(() => usePeople('register.read', false), { wrapper });
    const teams = renderHook(() => useTeams(false), { wrapper });
    expect([people.result.current.fetchStatus, teams.result.current.fetchStatus]).toEqual(['idle', 'idle']);
    renderHook(() => usePeople('register.read', true), { wrapper });
    renderHook(() => useTeams(true), { wrapper });
    await waitFor(() => expect(sent.map((s) => s.path).sort()).toEqual(['/api/v1/reference/people', '/api/v1/tenant/teams']));
    expect(participantKeys.obligation('ob1')).toEqual(['participants', 'obligation', 'ob1']);
  });

  it('refetches the list after an add, a refused add and a removal', async () => {
    let adds = 0;
    const sent = installAdapter((s) => {
      if (s.method === 'get') return { status: 200, data: { items: [], total: 0 } };
      if (s.method === 'delete') return { status: 204 };
      adds += 1;
      return adds === 1 ? { status: 201, data: { id: 'p1' } } : { status: 409, data: { code: 'already_participant' } };
    });
    const { wrapper } = queryWrapper();
    renderHook(() => useObligationParticipants('ob1'), { wrapper });
    await waitFor(() => expect(sent).toHaveLength(1));
    const add = renderHook(() => useAddObligationParticipant('ob1'), { wrapper });
    const remove = renderHook(() => useRemoveObligationParticipant('ob1'), { wrapper });
    const reads = () => sent.filter((s) => s.method === 'get').length;

    act(() => add.result.current.mutate({ userId: 'u1' }));
    await waitFor(() => expect(reads()).toBe(2));
    act(() => add.result.current.mutate({ userId: 'u1' }));
    await waitFor(() => expect(add.result.current.isError).toBe(true));
    await waitFor(() => expect(reads()).toBe(3));
    act(() => remove.result.current.mutate('p1'));
    await waitFor(() => expect(reads()).toBe(4));
    expect(sent.filter((s) => s.method !== 'get').map((s) => [s.method, s.path])).toEqual([
      ['post', '/api/v1/obligations/ob1/participants'],
      ['post', '/api/v1/obligations/ob1/participants'],
      ['delete', '/api/v1/obligations/ob1/participants/p1'],
    ]);
  });

  it('keeps a case’s list under the change and refetches it after each add and removal', async () => {
    const sent = installAdapter((s) => {
      if (s.method === 'get') return { status: 200, data: { items: [], total: 0 } };
      return s.method === 'delete' ? { status: 204 } : { status: 201, data: { id: 'p1' } };
    });
    const { wrapper } = queryWrapper();
    renderHook(() => useCaseParticipants('ch1'), { wrapper });
    await waitFor(() => expect(sent).toHaveLength(1));
    const add = renderHook(() => useAddCaseParticipant('ch1'), { wrapper });
    const remove = renderHook(() => useRemoveCaseParticipant('ch1'), { wrapper });
    const reads = () => sent.filter((s) => s.method === 'get').length;

    act(() => add.result.current.mutate({ teamKey: 'legal' }));
    await waitFor(() => expect(reads()).toBe(2));
    act(() => remove.result.current.mutate('p1'));
    await waitFor(() => expect(reads()).toBe(3));
    expect(participantKeys.case('ch1')).toEqual(['participants', 'case', 'ch1']);
    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['get', '/api/v1/changes/ch1/participants'],
      ['post', '/api/v1/changes/ch1/participants'],
      ['get', '/api/v1/changes/ch1/participants'],
      ['delete', '/api/v1/changes/ch1/participants/p1'],
      ['get', '/api/v1/changes/ch1/participants'],
    ]);
  });
});
