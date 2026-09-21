import { api } from '@/shared/utils/api-client';

import type { SearchRequestBody, SearchResponse } from './types';

export type { SearchRequestBody } from './types';

// Thin typed wrapper returning `.data` (playbook 6.1). `POST /search` is a
// read: it writes no audit row and needs no idempotency key, and it is a
// POST precisely so the reader's own words never travel in a URL or reach
// browser or server access logs (playbook 4.7).

const SEARCH = '/api/v1/search';

export async function runSearch(body: SearchRequestBody): Promise<SearchResponse> {
  return (await api.post<SearchResponse>(SEARCH, body)).data;
}
