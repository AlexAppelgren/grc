import { api } from '@/shared/utils/api-client';

import type { LibraryUpdatesPage, LibraryUpdatesQuery } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). POST /me/visit moves
// the reader's own bookmark and answers 204 with no body.

const LIBRARY_UPDATES = '/api/v1/library-updates';
const VISIT = '/api/v1/me/visit';

export async function listLibraryUpdates(query: LibraryUpdatesQuery = {}): Promise<LibraryUpdatesPage> {
  const params: Record<string, string> = {};
  if (query.kind) params.kind = query.kind;
  if (query.outsideFootprint === true) params.outsideFootprint = 'true';
  return (await api.get<LibraryUpdatesPage>(LIBRARY_UPDATES, { params })).data;
}

export async function markVisited(): Promise<void> {
  await api.post(VISIT, {});
}
