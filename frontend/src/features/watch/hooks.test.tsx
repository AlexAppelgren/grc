import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { CHANGE_PAGE, useChange, useChangeFeed, useObligationChanges, useScopeTerms, useTriageCount, watchKeys } from './hooks';

// The feed's paging, its tab counts and its cache keys. A filter is part of
// the key, so narrowing re-reads rather than reuses.

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
});
