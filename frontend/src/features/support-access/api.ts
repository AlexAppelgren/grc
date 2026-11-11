import type { SupportAccessGrant, SupportAccessPage } from '@/features/support-access/types';
import { api, segment } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1). Approve needs a
// passkey: a 403 step_up_required opens the api client's prompt and retries once.

const BASE = '/api/v1/tenant/support-access';

export async function listSupportAccess(query: { limit: number; offset: number }): Promise<SupportAccessPage> {
  return (await api.get<SupportAccessPage>(BASE, { params: query })).data;
}

export async function approveSupportAccess(grantId: string): Promise<SupportAccessGrant> {
  return (await api.post<SupportAccessGrant>(`${BASE}/${segment(grantId)}/approve`)).data;
}

export async function declineSupportAccess(grantId: string): Promise<SupportAccessGrant> {
  return (await api.post<SupportAccessGrant>(`${BASE}/${segment(grantId)}/decline`)).data;
}

export async function revokeSupportAccess(grantId: string): Promise<SupportAccessGrant> {
  return (await api.post<SupportAccessGrant>(`${BASE}/${segment(grantId)}/revoke`)).data;
}
