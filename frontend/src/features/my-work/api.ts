import { api } from '@/shared/utils/api-client';

import type { WorkPage, WorkQuery } from './types';

// A thin typed wrapper returning `.data` (playbook 6.1). A read: it writes nothing.

export async function getMyWork(query: WorkQuery): Promise<WorkPage> {
  return (await api.get<WorkPage>('/api/v1/me/work', { params: query })).data;
}
