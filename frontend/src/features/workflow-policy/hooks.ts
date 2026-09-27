'use client';

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { adminKeys } from '@/features/tenant-admin/hooks';
import type { Tenant } from '@/features/tenant-admin/types';
import { updateWorkflowPolicy } from '@/features/workflow-policy/api';
import type { WorkflowPolicyPatch } from '@/features/workflow-policy/types';

// The policy is read with the tenant profile (useTenant), so a save writes the
// answer back into that one cached profile rather than keeping a second copy.
export function useUpdateWorkflowPolicy(): UseMutationResult<Tenant, unknown, WorkflowPolicyPatch> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => updateWorkflowPolicy(body),
    onSuccess: (tenant) => queryClient.setQueryData(adminKeys.tenant, tenant),
  });
}
