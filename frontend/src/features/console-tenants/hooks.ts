'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as consoleTenants from '@/features/console-tenants/api';
import type { ConsoleTenant, ConsoleTenantCreate, ConsoleTenantPage } from '@/features/console-tenants/types';

// Query keys and invalidation for the console tenants screen (playbook 6.1).

export const consoleTenantKeys = {
  tenants: ['console', 'tenants'] as const,
};

// One page at the server's maximum; paging joins the screen when a bank list
// outgrows it.
export const CONSOLE_TENANTS_PAGE = 100;

export function useConsoleTenants(): UseQueryResult<ConsoleTenantPage> {
  return useQuery({
    queryKey: consoleTenantKeys.tenants,
    queryFn: () => consoleTenants.listConsoleTenants({ limit: CONSOLE_TENANTS_PAGE, offset: 0 }),
  });
}

export function useCreateConsoleTenant(): UseMutationResult<ConsoleTenant, unknown, ConsoleTenantCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => consoleTenants.createConsoleTenant(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: consoleTenantKeys.tenants }),
  });
}
