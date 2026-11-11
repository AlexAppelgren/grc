import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { listPeople, listTeams, listTermRows, referenceKeys, termRowsQuery, usePeople, useTeams } from './reference';

// The one home of the bank's people, teams and terms: every picker reads them
// through these wrappers and keys, so a page holding three people pickers
// sends one request.

describe('reference data', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the people picker, all members or those holding a permission', async () => {
    const sent = installAdapter(() => ({ status: 200, data: [{ id: 'u1', name: 'Karin Holm' }] }));
    expect(await listPeople()).toEqual([{ id: 'u1', name: 'Karin Holm' }]);
    await listPeople('register.read');
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/reference/people', {}],
      ['/api/v1/reference/people', { permission: 'register.read' }],
    ]);
  });

  it('reads the teams in one page at the server maximum, and the terms with their filters', async () => {
    const team = { key: 'cards', label: 'Cards' };
    const sent = installAdapter((s) => ({ status: 200, data: { items: s.path.endsWith('teams') ? [team] : [], total: 1 } }));
    expect(await listTeams()).toEqual([team]);
    await listTermRows();
    await listTermRows('regime', true);
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/tenant/teams', { limit: 100 }],
      ['/api/v1/taxonomy/terms', {}],
      ['/api/v1/taxonomy/terms', { dimension: 'regime', includeRetired: true }],
    ]);
    expect(termRowsQuery('regime').queryKey).toEqual(referenceKeys.terms('regime', false));
    expect(termRowsQuery().queryKey).not.toEqual(termRowsQuery(undefined, true).queryKey);
  });

  it('reads the picker lists only while enabled, and once for every reader of the same list', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.path.endsWith('people') ? [] : { items: [], total: 0 } }));
    const { wrapper } = queryWrapper();
    const people = renderHook(() => usePeople('register.read', false), { wrapper });
    const teams = renderHook(() => useTeams(false), { wrapper });
    expect([people.result.current.fetchStatus, teams.result.current.fetchStatus]).toEqual(['idle', 'idle']);
    renderHook(() => [usePeople('register.read', true), usePeople('register.read')], { wrapper });
    renderHook(() => useTeams(true), { wrapper });
    await waitFor(() => expect(sent.map((s) => s.path).sort()).toEqual(['/api/v1/reference/people', '/api/v1/tenant/teams']));
    expect(referenceKeys.people('register.read')).not.toEqual(referenceKeys.people(null));
  });
});
