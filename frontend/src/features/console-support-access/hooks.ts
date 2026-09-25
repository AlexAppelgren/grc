'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as supportAccess from '@/features/console-support-access/api';
import type { ConsoleSupportGrant, ConsoleSupportGrantPage, ConsoleSupportRequest, SupportSessionTokens } from '@/features/console-support-access/types';
import { tokenStore } from '@/shared/utils/api-client';

export const consoleSupportAccessKeys = { mine: ['console', 'support-access'] as const };

/** The server's largest page (CLAUDE.md section 6): a person's own open requests are always on it. */
export const CONSOLE_SUPPORT_ACCESS_PAGE = 100;

/** The caller's own requests and grants, newest first. Off once a support session replaced the console's. */
export function useMySupportAccess(enabled: boolean): UseQueryResult<ConsoleSupportGrantPage> {
  return useQuery({
    queryKey: consoleSupportAccessKeys.mine,
    queryFn: () => supportAccess.listMySupportAccess({ limit: CONSOLE_SUPPORT_ACCESS_PAGE, offset: 0 }),
    enabled,
  });
}

export function useAskForSupportAccess(): UseMutationResult<ConsoleSupportGrant, unknown, { tenantId: string; body: ConsoleSupportRequest }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ tenantId, body }) => supportAccess.askForSupportAccess(tenantId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: consoleSupportAccessKeys.mine }),
  });
}

/**
 * Enter a bank under an approved grant. The server signs the console session
 * out and answers with the support session's token, which every request from
 * here on carries; nothing is refetched, because the console's reads are no
 * longer this session's to make.
 */
export function useEnterSupportAccess(): UseMutationResult<SupportSessionTokens, unknown, string> {
  return useMutation({
    mutationFn: (grantId) => supportAccess.enterSupportAccess(grantId),
    onSuccess: (tokens) => tokenStore.set(tokens.accessToken),
  });
}
