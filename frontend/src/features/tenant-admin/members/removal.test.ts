import { act, renderHook, waitFor } from '@testing-library/react';
import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it } from 'vitest';

import { adminKeys } from '@/features/tenant-admin/hooks';
import { teamKeys } from '@/features/tenant-admin/teams/hooks';
import { createT } from '@/shared/i18n';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { getOpenWork, isMoved, kindCount, kindsStillOwned, movedWork, participationCount, removalBody, removeMember, useOpenWork, useRemoveMember, type MovedKind, type OpenWork } from './removal';

// The removal's pure parts: the kinds that move, in the screen's order and
// with the server's counts; what simply ends; the body, one owner per kind;
// and a reassignment_required answer read from its code and errors.

const work: OpenWork = {
  member: { id: 'u-gustav', name: 'Gustav Sjöberg' },
  items: [
    { kind: 'action', count: 4 },
    { kind: 'participation', count: 5 },
    { kind: 'register_entry', count: 3 },
    { kind: 'team_membership', count: 2 },
    { kind: 'gap', count: 1 },
  ],
  teams: ['cards', 'legal'],
};

function problem(status: number, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  return new AxiosError('refused', String(status), config, undefined, { data, status, statusText: '', headers: {}, config });
}

describe('the removal', () => {
  it('lists the kinds that move in the screen order, and counts what ends', () => {
    expect(movedWork(work)).toEqual([
      { kind: 'register_entry', count: 3 },
      { kind: 'gap', count: 1 },
      { kind: 'action', count: 4 },
    ]);
    expect(participationCount(work)).toBe(5);
    expect(participationCount({ ...work, items: [] })).toBe(0);
  });

  it('sends one owner per kind, a team by key or a person by id', () => {
    expect(removalBody({ register_entry: { userId: 'u-sara' }, gap: { teamKey: 'cards' } })).toEqual({
      owners: [
        { kind: 'register_entry', userId: 'u-sara' },
        { kind: 'gap', teamKey: 'cards' },
      ],
    });
    expect(removalBody({})).toEqual({ owners: [] });
  });

  it('reads the kinds still owned from reassignment_required, and nothing from another refusal', () => {
    const refused = problem(422, {
      code: 'reassignment_required',
      detail: 'Anything at all.',
      errors: [
        { field: 'gap', count: 2, message: 'x' },
        { field: 'participation', count: 1, message: 'x' },
      ],
    });
    expect(kindsStillOwned(refused)).toEqual([{ kind: 'gap', count: 2 }]);
    expect(kindsStillOwned(problem(422, { code: 'unknown_member', detail: '', errors: [{ field: 'gap', count: 2 }] }))).toEqual([]);
    expect(kindsStillOwned(null)).toEqual([]);
  });
});

describe('the removal kinds', () => {
  it('moves the owned kinds and lets participations and team memberships end', () => {
    expect(isMoved('register_entry')).toBe(true);
    expect(isMoved('action')).toBe(true);
    expect(isMoved('participation')).toBe(false);
    expect(isMoved('team_membership')).toBe(false);
  });

  it('names each moved kind with its count from the catalog', () => {
    const t = createT('en');
    const named: [MovedKind, string, string][] = [
      ['register_entry', '1 obligation', '3 obligations'],
      ['register_entity', '1 obligation per legal entity', '3 obligations per legal entity'],
      ['gap', '1 gap', '3 gaps'],
      ['duty_occurrence', '1 recurring duty date', '3 recurring duty dates'],
      ['internal_item', '1 internal item', '3 internal items'],
      ['case', '1 case', '3 cases'],
      ['action', '1 action', '3 actions'],
    ];
    for (const [kind, one, many] of named) {
      expect(kindCount(kind, 1, t)).toBe(one);
      expect(kindCount(kind, 3, t)).toBe(many);
    }
  });

  it('reads nothing from reassignment_required entries that are not records with a count', () => {
    const refused = problem(422, { code: 'reassignment_required', detail: '', errors: ['gap', null, { field: 'gap', count: '2' }, { field: 'case', count: 1 }] });
    expect(kindsStillOwned(refused)).toEqual([{ kind: 'case', count: 1 }]);
    expect(kindsStillOwned(problem(422, { code: 'reassignment_required', detail: '' }))).toEqual([]);
  });
});

describe('the removal calls', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the open work and posts the removal for the member, with the id escaped', async () => {
    const sent = installAdapter(() => ({ status: 200, data: work }));
    expect(await getOpenWork('u/gustav')).toEqual(work);
    await removeMember('u/gustav', { gap: { teamKey: 'cards' } });
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([
      ['get', '/api/v1/tenant/members/u%2Fgustav/open-work', null],
      ['post', '/api/v1/tenant/members/u%2Fgustav/remove', { owners: [{ kind: 'gap', teamKey: 'cards' }] }],
    ]);
  });

  it('reads the open work only once enabled', async () => {
    const sent = installAdapter(() => ({ status: 200, data: work }));
    const { wrapper } = queryWrapper();
    const hook = renderHook(({ enabled }) => useOpenWork('u-gustav', enabled), { wrapper, initialProps: { enabled: false } });
    expect(hook.result.current.fetchStatus).toBe('idle');
    expect(sent).toEqual([]);
    hook.rerender({ enabled: true });
    await waitFor(() => expect(hook.result.current.data).toEqual(work));
    expect(sent.map((s) => s.path)).toEqual(['/api/v1/tenant/members/u-gustav/open-work']);
  });

  it('removes the member, then marks members and teams stale without refetching them', async () => {
    const sent = installAdapter(() => ({ status: 200, data: {} }));
    const { wrapper, queryClient } = queryWrapper();
    // Kept while nothing observes them, so their state can be read after the call.
    queryClient.setQueryDefaults(['tenant'], { gcTime: Infinity });
    queryClient.setQueryData(adminKeys.members, []);
    queryClient.setQueryData(teamKeys.all, []);
    const hook = renderHook(() => useRemoveMember(), { wrapper });
    await act(() => hook.result.current.mutateAsync({ userId: 'u-gustav', owners: { case: { userId: 'u-sara' } } }));
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([['post', '/api/v1/tenant/members/u-gustav/remove', { owners: [{ kind: 'case', userId: 'u-sara' }] }]]);
    expect(queryClient.getQueryState(adminKeys.members)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(teamKeys.all)?.isInvalidated).toBe(true);
  });

  it('leaves members and teams fresh when the removal is refused', async () => {
    installAdapter(() => ({ status: 422, data: { code: 'reassignment_required', detail: '', errors: [{ field: 'gap', count: 1 }] } }));
    const { wrapper, queryClient } = queryWrapper();
    // Kept while nothing observes them, so their state can be read after the call.
    queryClient.setQueryDefaults(['tenant'], { gcTime: Infinity });
    queryClient.setQueryData(adminKeys.members, []);
    const hook = renderHook(() => useRemoveMember(), { wrapper });
    await act(async () => {
      await expect(hook.result.current.mutateAsync({ userId: 'u-gustav', owners: {} })).rejects.toBeInstanceOf(AxiosError);
    });
    await waitFor(() => expect(kindsStillOwned(hook.result.current.error)).toEqual([{ kind: 'gap', count: 1 }]));
    expect(queryClient.getQueryState(adminKeys.members)?.isInvalidated).toBe(false);
  });
});
