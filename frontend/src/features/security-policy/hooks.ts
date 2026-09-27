import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as securityPolicy from '@/features/security-policy/api';
import type { SecurityPolicy, SecurityPolicyBody } from '@/features/security-policy/types';

export const securityPolicyKey = ['tenant', 'security-policy'] as const;

export function useSecurityPolicy(): UseQueryResult<SecurityPolicy> {
  return useQuery({ queryKey: securityPolicyKey, queryFn: securityPolicy.getSecurityPolicy });
}

export function useSetSecurityPolicy(): UseMutationResult<SecurityPolicy, unknown, SecurityPolicyBody> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: securityPolicy.putSecurityPolicy, onSuccess: (policy) => queryClient.setQueryData(securityPolicyKey, policy) });
}
