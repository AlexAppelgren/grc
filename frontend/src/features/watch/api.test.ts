import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as watch from './api';

// The watch reads: the routes they call, the query they send and the page
// they hand back. Nothing here reshapes the server's answer, because the
// generated types are the screens' types.

describe('watch api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the feed with its filters, repeating termId rather than sending an array', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    const page = await watch.listChanges({ tab: 'new', footprint: 'in', termId: ['t-1', 't-2'], q: 'research', limit: 20, offset: 0 });
    expect(page).toEqual({ items: [], total: 0 });
    expect(sent[0]?.path).toBe('/api/v1/changes');
    expect(watch.serializeQuery({ tab: 'new', termId: ['t-1', 't-2'], q: 'research' })).toBe('tab=new&termId=t-1&termId=t-2&q=research');
  });

  it('leaves out a filter that is not set, so an empty box never narrows the feed', () => {
    expect(watch.serializeQuery({ urgency: '', changeType: null, week: undefined, tab: 'all' })).toBe('tab=all');
  });

  it('reads one change by its id', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'c-1' } }));
    await watch.getChange('c-1');
    expect(sent[0]?.path).toBe('/api/v1/changes/c-1');
  });

  it('reads the changes related to an obligation, paginated', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0, openCount: 0 } }));
    const page = await watch.listObligationChanges('ob-1', { limit: 20, offset: 0 });
    expect(page.openCount).toBe(0);
    expect([sent[0]?.path, sent[0]?.params]).toEqual(['/api/v1/obligations/ob-1/changes', { limit: 20, offset: 0 }]);
  });

  it('reads the coverage log, and an empty registry is an empty list', async () => {
    const sent = installAdapter(() => ({ status: 200, data: [] }));
    expect(await watch.getSourceCoverage()).toEqual([]);
    expect(sent[0]?.path).toBe('/api/v1/sources/coverage');
  });

  it('reads the scope terms of one dimension with the ids the feed filters on', async () => {
    const sent = installAdapter(() => ({
      status: 200,
      data: { items: [{ id: 'term-1', key: 'securities', label: 'Securities', kind: null, dimension: 'regime' }], total: 1 },
    }));
    expect(await watch.listScopeTerms('regime')).toEqual([{ id: 'term-1', key: 'securities', label: 'Securities' }]);
    expect([sent[0]?.path, sent[0]?.params]).toEqual(['/api/v1/taxonomy/terms', { dimension: 'regime' }]);
  });
});
