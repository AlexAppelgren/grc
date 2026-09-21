import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as search from './api';

// The one search read: the route it posts to, the body it sends and the
// answer it hands back unchanged. Nothing here reshapes the server's answer,
// because the generated types are the screen's types.

describe('search api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('posts the query to POST /search and returns the ranked answer', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    const body: search.SearchRequestBody = { q: 'FFFS 2017:2', limit: 20 };
    const response = await search.runSearch(body);
    expect(response).toEqual({ items: [], asOf: '2026-09-20' });
    expect(sent[0]?.method).toBe('post');
    expect(sent[0]?.path).toBe('/api/v1/search');
    expect(sent[0]?.body).toEqual(body);
  });
});
