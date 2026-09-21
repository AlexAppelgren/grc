import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as libraryUpdates from './api';

describe('library-updates api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the feed with only the filters that are set', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { since: '2026-09-12', days: [], total: 0 } }));
    await libraryUpdates.listLibraryUpdates({ kind: 'new_obligation_version', outsideFootprint: true });
    expect([sent[0]?.path, sent[0]?.params]).toEqual(['/api/v1/library-updates', { kind: 'new_obligation_version', outsideFootprint: 'true' }]);
  });

  it('leaves out an unset filter rather than sending it empty', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { since: '2026-09-12', days: [], total: 0 } }));
    await libraryUpdates.listLibraryUpdates({});
    expect(sent[0]?.params).toEqual({});
  });

  it('marks the bookmark with no body', async () => {
    const sent = installAdapter(() => ({ status: 204 }));
    await libraryUpdates.markVisited();
    expect([sent[0]?.method, sent[0]?.path]).toEqual(['post', '/api/v1/me/visit']);
  });
});
