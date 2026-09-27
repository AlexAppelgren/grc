'use client';

import { useInfiniteQuery, useMutation, useQueryClient, type UseInfiniteQueryResult, type UseMutationResult } from '@tanstack/react-query';

import * as supportAccess from '@/features/support-access/api';
import type { SupportAccessGrant, SupportAccessPage } from '@/features/support-access/types';

export const supportAccessKeys = { list: ['support-access'] as const };

/** The server's largest page (CLAUDE.md section 6): pending and live grants are always on the first. */
export const SUPPORT_ACCESS_PAGE = 100;

/** Every request the bank has had, newest first, one page at a time. */
export function useSupportAccess(): UseInfiniteQueryResult<{ pages: SupportAccessPage[] }> {
  return useInfiniteQuery({
    queryKey: supportAccessKeys.list,
    queryFn: ({ pageParam }) => supportAccess.listSupportAccess({ limit: SUPPORT_ACCESS_PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last: SupportAccessPage, pages: SupportAccessPage[]) => {
      const read = pages.reduce((sum, page) => sum + page.items.length, 0);
      return read < last.total ? read : undefined;
    },
  });
}

export type SupportDecision = 'approve' | 'decline' | 'revoke';

const decide: Record<SupportDecision, (grantId: string) => Promise<SupportAccessGrant>> = {
  approve: supportAccess.approveSupportAccess,
  decline: supportAccess.declineSupportAccess,
  revoke: supportAccess.revokeSupportAccess,
};

/**
 * Approve, decline or revoke one grant. The list reloads whatever the answer,
 * so a request another admin decided, or one that lapsed, shows where it stands.
 */
export function useDecideSupportAccess(decision: SupportDecision): UseMutationResult<SupportAccessGrant, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (grantId) => decide[decision](grantId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: supportAccessKeys.list }),
  });
}
