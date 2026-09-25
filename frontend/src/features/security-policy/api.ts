import type { SecurityPolicy, SecurityPolicyBody } from '@/features/security-policy/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1). Step-up is the api
// client's business: a 403 step_up_required opens the prompt and retries once.

const PATH = '/api/v1/tenant/security-policy';

export async function getSecurityPolicy(): Promise<SecurityPolicy> {
  return (await api.get<SecurityPolicy>(PATH)).data;
}

export async function putSecurityPolicy(body: SecurityPolicyBody): Promise<SecurityPolicy> {
  return (await api.put<SecurityPolicy>(PATH, body)).data;
}
