'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import * as search from './api';
import type { SearchRequestBody } from './api';
import type { SearchResponse } from './types';

// One read, keyed on the whole request: a narrowed search is a different
// answer, never a trimmed one, exactly as the watch feed's filters are part
// of its own key.

export const searchKeys = {
  results: (body: SearchRequestBody) => ['search', body] as const,
};

/**
 * `body` is `null` until the reader has asked for something: a POST body is
 * required, an empty query is not a search, and a screen must never guess at
 * one (SRC-01).
 */
export function useSearchResults(body: SearchRequestBody | null): UseQueryResult<SearchResponse> {
  return useQuery({
    queryKey: searchKeys.results(body ?? { q: '', limit: 0 }),
    queryFn: () => search.runSearch(body as SearchRequestBody),
    enabled: body !== null,
  });
}
