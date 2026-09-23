'use client';

import { useMutation, useQueries, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';
import { useMemo } from 'react';

import { listScopeTerms } from '@/features/watch/api';

import * as proposals from './api';
import type { ProposalApproveBody, ProposalDetail, ProposalPage, ProposalQuery, ProposalRejectBody, ProposalRow, TenantProposalPage, TenantProposalQuery } from './types';

// Query keys and invalidation for the console queue (playbook 6.1). The
// filters are part of the key, so narrowing the queue re-reads rather than
// filters a stale page.

export const proposalKeys = {
  all: ['proposals'] as const,
  list: (query: ProposalQuery) => ['proposals', 'list', query] as const,
  detail: (id: string) => ['proposals', 'detail', id] as const,
};

export function useProposals(query: ProposalQuery): UseQueryResult<ProposalPage> {
  return useQuery({ queryKey: proposalKeys.list(query), queryFn: () => proposals.listProposals(query) });
}

export function useProposal(proposalId: string): UseQueryResult<ProposalDetail> {
  return useQuery({ queryKey: proposalKeys.detail(proposalId), queryFn: () => proposals.getProposal(proposalId) });
}

function useInvalidateQueue(proposalId: string): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: proposalKeys.all });
    await queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
  };
}

export function useApproveProposal(proposalId: string): UseMutationResult<ProposalRow, unknown, ProposalApproveBody> {
  const invalidate = useInvalidateQueue(proposalId);
  return useMutation({
    mutationFn: (body) => proposals.approveProposal(proposalId, body),
    onSuccess: () => invalidate(),
  });
}

export function useRejectProposal(proposalId: string): UseMutationResult<ProposalRow, unknown, ProposalRejectBody> {
  const invalidate = useInvalidateQueue(proposalId);
  return useMutation({
    mutationFn: (body) => proposals.rejectProposal(proposalId, body),
    onSuccess: () => invalidate(),
  });
}

/**
 * Labels for a proposal's scope terms (`dimension:key` refs): GET /proposals answers the
 * refs only, so the console resolves each dimension the proposal touches against
 * GET /taxonomy/terms the same way the watch feed's own filter does (features/watch/api.ts
 * `listScopeTerms`), rather than showing the raw key. Usually one or two dimensions, held
 * for five minutes like the feed's own read, since scope terms change rarely.
 */
export function useScopeTermLabels(refs: readonly string[]): { labelOf: (ref: string) => string; isPending: boolean } {
  const dimensions = useMemo(() => [...new Set(refs.map((ref) => ref.split(':')[0]).filter((d): d is string => d !== undefined && d !== ''))], [refs]);
  const results = useQueries({
    queries: dimensions.map((dimension) => ({ queryKey: ['watch', 'terms', dimension], queryFn: () => listScopeTerms(dimension), staleTime: 5 * 60_000 })),
  });
  const labels = new Map<string, string>();
  dimensions.forEach((dimension, index) => {
    for (const term of results[index]?.data ?? []) labels.set(`${dimension}:${term.key}`, term.label);
  });
  return { labelOf: (ref) => labels.get(ref) ?? ref, isPending: results.some((result) => result.isPending) };
}

/** What this tenant itself proposed on one library list and is still waiting on (GET /tenant/proposals). */
export function useTenantProposals(query: TenantProposalQuery, enabled = true): UseQueryResult<TenantProposalPage> {
  return useQuery({ queryKey: ['proposals', 'tenant', query], queryFn: () => proposals.listTenantProposals(query), enabled });
}
