import type { ConsoleSupportGrant, ConsoleSupportGrantPage, ConsoleSupportRequest, SupportSessionTokens } from '@/features/console-support-access/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1). Entering needs a
// passkey: a 403 step_up_required opens the api client's prompt and retries once.

const BASE = '/api/v1/console/support-access';

const id = (value: string) => encodeURIComponent(value);

export async function listMySupportAccess(query: { limit: number; offset: number }): Promise<ConsoleSupportGrantPage> {
  return (await api.get<ConsoleSupportGrantPage>(BASE, { params: query })).data;
}

export async function askForSupportAccess(tenantId: string, body: ConsoleSupportRequest): Promise<ConsoleSupportGrant> {
  return (await api.post<ConsoleSupportGrant>(`/api/v1/console/tenants/${id(tenantId)}/support-access`, body)).data;
}

export async function enterSupportAccess(grantId: string): Promise<SupportSessionTokens> {
  return (await api.post<SupportSessionTokens>(`${BASE}/${id(grantId)}/enter`)).data;
}
