import { renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import type { ChangeDetail } from './api';
import {
  CHANGE_PAGE,
  useAcceptCaseObligationLink,
  useCanWorkCase,
  useChange,
  useChangeFeed,
  useConfirmSoWhat,
  useObligationChanges,
  useRemoveCaseObligationLink,
  useSaveSoWhat,
  useScopeTerms,
  useTriageCount,
  watchKeys,
} from './hooks';

// The feed's paging, its tab counts and its cache keys. A filter is part of
// the key, so narrowing re-reads rather than reuses. And this bank's own
// writes on its case: each one re-reads what the watch screens show.

const page = (items: number, total: number) => ({ items: Array.from({ length: items }, (_, i) => ({ id: `c-${i}` })), total });

describe('watch hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the first page with the list default', async () => {
    const sent = installAdapter(() => ({ status: 200, data: page(0, 0) }));
    const { wrapper } = queryWrapper();
    const feed = renderHook(() => useChangeFeed({ tab: 'new' }), { wrapper });
    await waitFor(() => expect(feed.result.current.data).toBeDefined());
    expect(sent[0]?.params).toEqual({ tab: 'new', limit: CHANGE_PAGE, offset: 0 });
  });

  it('the next page begins where the pages read so far end, and stops at the total', async () => {
    const sent: Sent[] = installAdapter((_, index) => ({ status: 200, data: index === 0 ? page(CHANGE_PAGE, 25) : page(5, 25) }));
    const { wrapper } = queryWrapper();
    const feed = renderHook(() => useChangeFeed({}), { wrapper });
    await waitFor(() => expect(feed.result.current.hasNextPage).toBe(true));
    await feed.result.current.fetchNextPage();
    await waitFor(() => expect(feed.result.current.hasNextPage).toBe(false));
    expect(sent.map((s) => (s.params as { offset: number }).offset)).toEqual([0, CHANGE_PAGE]);
  });

  it('counts the triage tab through the route the rows come from, asking for the smallest page', async () => {
    const sent = installAdapter(() => ({ status: 200, data: page(0, 3) }));
    const { wrapper } = queryWrapper();
    const count = renderHook(() => useTriageCount({ footprint: 'in' }, true), { wrapper });
    await waitFor(() => expect(count.result.current.data?.total).toBe(3));
    expect(sent.map((s) => s.params)).toEqual([{ footprint: 'in', tab: 'new', limit: 1, offset: 0 }]);
  });

  it('does not ask for the count the feed already carries', async () => {
    const sent = installAdapter(() => ({ status: 200, data: page(0, 3) }));
    const { wrapper } = queryWrapper();
    renderHook(() => useTriageCount({ footprint: 'in' }, false), { wrapper });
    await waitFor(() => expect(sent).toHaveLength(0));
  });

  it('reads one change and one obligation’s changes', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'c-1', items: [], total: 0, openCount: 0 } }));
    const { wrapper } = queryWrapper();
    const change = renderHook(() => useChange('c-1'), { wrapper });
    const related = renderHook(() => useObligationChanges('ob-1'), { wrapper });
    await waitFor(() => expect(change.result.current.data).toBeDefined());
    await waitFor(() => expect(related.result.current.data).toBeDefined());
    expect(sent.map((s) => s.path).sort()).toEqual(['/api/v1/changes/c-1', '/api/v1/obligations/ob-1/changes']);
  });

  it('reads the scope terms of a dimension', async () => {
    installAdapter(() => ({ status: 200, data: { items: [{ id: 't-1', key: 'securities', label: 'Securities', kind: null, dimension: 'regime' }], total: 1 } }));
    const { wrapper } = queryWrapper();
    const terms = renderHook(() => useScopeTerms('regime'), { wrapper });
    await waitFor(() => expect(terms.result.current.data).toEqual([{ id: 't-1', key: 'securities', label: 'Securities' }]));
  });

  it('keys each set of filters separately, so narrowing the feed re-reads', () => {
    expect(watchKeys.changes({ tab: 'new' })).not.toEqual(watchKeys.changes({ tab: 'closed' }));
    expect(watchKeys.count('triage', {})).not.toEqual(watchKeys.count('closed', {}));
    expect(watchKeys.change('c-1')).toEqual(['watch', 'change', 'c-1']);
    expect(watchKeys.obligationChanges('ob-1', 20)).toEqual(['watch', 'obligation-changes', 'ob-1', { limit: 20 }]);
    expect(watchKeys.coverage).toEqual(['watch', 'coverage']);
  });

  it('each write on the case re-reads every watch read, because each moves the page, the feed and a count', async () => {
    const sent = installAdapter(() => ({ status: 200, data: {} }));
    const { wrapper, queryClient } = queryWrapper();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const save = renderHook(() => useSaveSoWhat('c-1'), { wrapper });
    const confirm = renderHook(() => useConfirmSoWhat('c-1'), { wrapper });
    const accept = renderHook(() => useAcceptCaseObligationLink('c-1'), { wrapper });
    const remove = renderHook(() => useRemoveCaseObligationLink('c-1'), { wrapper });

    await save.result.current.mutateAsync('Ours.');
    await confirm.result.current.mutateAsync();
    await accept.result.current.mutateAsync('ob-1');
    await remove.result.current.mutateAsync('ob-2');

    expect(sent.map((s) => [s.method, s.path])).toEqual([
      ['put', '/api/v1/changes/c-1/so-what'],
      ['post', '/api/v1/changes/c-1/so-what/confirm'],
      ['post', '/api/v1/changes/c-1/case/obligation-links'],
      ['delete', '/api/v1/changes/c-1/case/obligation-links/ob-2'],
    ]);
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([watchKeys.all, watchKeys.all, watchKeys.all, watchKeys.all]);
  });

  it('a write the server refuses re-reads nothing', async () => {
    installAdapter(() => ({ status: 403, data: { code: 'permission_denied', detail: '', requiredPermission: 'cases.work' } }));
    const { wrapper, queryClient } = queryWrapper();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const confirm = renderHook(() => useConfirmSoWhat('c-1'), { wrapper });
    await expect(confirm.result.current.mutateAsync()).rejects.toBeDefined();
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('offers the case controls only with cases.work and a case to write to', () => {
    const withCase = { case: { id: 'case-1' } } as unknown as ChangeDetail;
    const without = { case: null } as unknown as ChangeDetail;
    const as = (permissions: string[] | null) => ({ children }: { children: ReactNode }) => createElement(PermissionsProvider, { permissions, children });
    expect(renderHook(() => useCanWorkCase(withCase), { wrapper: as(['cases.work']) }).result.current).toBe(true);
    expect(renderHook(() => useCanWorkCase(without), { wrapper: as(['cases.work']) }).result.current).toBe(false);
    expect(renderHook(() => useCanWorkCase(withCase), { wrapper: as(['watch.read']) }).result.current).toBe(false);
    // No session known yet is never a grant.
    expect(renderHook(() => useCanWorkCase(withCase), { wrapper: as(null) }).result.current).toBe(false);
  });
});
