import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as libraryUpdates from './api';
import { KIND_FILTER } from './library-updates-presentation';

const EMPTY = { since: '2026-09-12T07:00:00Z', days: [], total: 0 };

describe('library-updates api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the feed with only the filters that are set', async () => {
    const sent = installAdapter(() => ({ status: 200, data: EMPTY }));
    await libraryUpdates.listLibraryUpdates({ kind: 'new_obligation_version', outsideFootprint: true });
    expect([sent[0]?.path, sent[0]?.params]).toEqual(['/api/v1/library-updates', { kind: 'new_obligation_version', outsideFootprint: 'true' }]);
  });

  it('sends the vocabulary filter as one comma list, which the route splits', async () => {
    const sent = installAdapter(() => ({ status: 200, data: EMPTY }));
    await libraryUpdates.listLibraryUpdates({ kind: KIND_FILTER.vocabulary });
    expect(sent[0]?.params).toEqual({ kind: 'vocabulary_create,vocabulary_relabel,vocabulary_retire,vocabulary_restore,vocabulary_merge,term_create,term_update' });
  });

  it('leaves out an unset filter rather than sending it empty', async () => {
    const sent = installAdapter(() => ({ status: 200, data: EMPTY }));
    await libraryUpdates.listLibraryUpdates({});
    await libraryUpdates.listLibraryUpdates({ kind: '', outsideFootprint: false });
    await libraryUpdates.listLibraryUpdates({ kind: null });
    expect(sent.map((request) => request.params)).toEqual([{}, {}, {}]);
  });

  it('marks the bookmark with no body', async () => {
    const sent = installAdapter(() => ({ status: 204 }));
    await libraryUpdates.markVisited();
    expect([sent[0]?.method, sent[0]?.path]).toEqual(['post', '/api/v1/me/visit']);
  });
});
