import type { Tenant } from '@/features/tenant-admin/types';
import type { WorkflowPolicyPatch } from '@/features/workflow-policy/types';
import { api } from '@/shared/utils/api-client';

// Answers the whole tenant profile, with the policy as it now stands.
export async function updateWorkflowPolicy(body: WorkflowPolicyPatch): Promise<Tenant> {
  return (await api.patch<Tenant>('/api/v1/tenant/workflow', body)).data;
}
