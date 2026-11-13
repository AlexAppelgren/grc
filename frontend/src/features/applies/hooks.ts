'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { usePermissions } from '@/shared/navigation/require-permission';

import * as applies from './api';
import type { ApplicabilityCompany } from './api';

// Query keys for "What applies" (playbook 6.1).

export const appliesKeys = {
  companies: ['applies', 'companies'] as const,
};

/** The companies and their offered counts, read only by someone holding register.read; nobody else asks. */
export function useApplicabilityCompanies(): UseQueryResult<ApplicabilityCompany[]> {
  const canRead = (usePermissions() ?? []).includes('register.read');
  return useQuery({ queryKey: appliesKeys.companies, queryFn: applies.listApplicabilityCompanies, enabled: canRead });
}
