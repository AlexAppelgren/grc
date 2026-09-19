'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import type { ProposalRef } from '@/features/vocabularies/types';

import * as footprint from './api';
import type {
  Footprint,
  FootprintChangeRequest,
  FootprintPreview,
  FootprintRejectBody,
  FootprintRequestCreate,
  Page,
  TaxonomyDimension,
  TaxonomyTerm,
  TermSuggest,
} from './types';

// Query keys and invalidation for the footprint screen (playbook 6.1). The
// footprint and its requests are read in parallel, never chained; a decision
// refreshes both, because an approval changes the footprint itself.

export const footprintKeys = {
  footprint: ['tenant', 'footprint'] as const,
  requests: ['tenant', 'footprint', 'requests'] as const,
  terms: (dimension?: string) => ['taxonomy', 'terms', dimension ?? 'all'] as const,
  dimensions: ['taxonomy', 'dimensions'] as const,
};

export const REQUEST_HISTORY_PAGE = 20;

export function useFootprint(): UseQueryResult<Footprint> {
  return useQuery({ queryKey: footprintKeys.footprint, queryFn: footprint.getFootprint });
}

export function useFootprintRequests(): UseQueryResult<Page<FootprintChangeRequest>> {
  return useQuery({ queryKey: footprintKeys.requests, queryFn: () => footprint.listFootprintRequests({ limit: REQUEST_HISTORY_PAGE, offset: 0 }) });
}

export function useTerms(dimension?: string): UseQueryResult<TaxonomyTerm[]> {
  return useQuery({ queryKey: footprintKeys.terms(dimension), queryFn: () => footprint.listTerms(dimension), staleTime: 5 * 60_000 });
}

export function useDimensions(): UseQueryResult<TaxonomyDimension[]> {
  return useQuery({ queryKey: footprintKeys.dimensions, queryFn: footprint.listDimensions, staleTime: 5 * 60_000 });
}

function useInvalidateFootprint(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: footprintKeys.footprint });
    await queryClient.invalidateQueries({ queryKey: footprintKeys.requests });
  };
}

/** The counted preview before anything is stored; never invalidates, it changed nothing. */
export function usePreviewFootprintRequest(): UseMutationResult<FootprintPreview, unknown, FootprintRequestCreate> {
  return useMutation({ mutationFn: (body) => footprint.previewFootprintRequest(body) });
}

export function useCreateFootprintRequest(): UseMutationResult<FootprintChangeRequest, unknown, FootprintRequestCreate> {
  const invalidate = useInvalidateFootprint();
  return useMutation({ mutationFn: (body) => footprint.createFootprintRequest(body), onSuccess: () => invalidate() });
}

export function useApproveFootprintRequest(): UseMutationResult<FootprintChangeRequest, unknown, { requestId: string; version?: number }> {
  const invalidate = useInvalidateFootprint();
  return useMutation({ mutationFn: ({ requestId, version }) => footprint.approveFootprintRequest(requestId, version), onSuccess: () => invalidate() });
}

export function useRejectFootprintRequest(): UseMutationResult<FootprintChangeRequest, unknown, { requestId: string; body: FootprintRejectBody; version?: number }> {
  const invalidate = useInvalidateFootprint();
  return useMutation({ mutationFn: ({ requestId, body, version }) => footprint.rejectFootprintRequest(requestId, body, version), onSuccess: () => invalidate() });
}

export function useWithdrawFootprintRequest(): UseMutationResult<FootprintChangeRequest, unknown, { requestId: string; version?: number }> {
  const invalidate = useInvalidateFootprint();
  return useMutation({ mutationFn: ({ requestId, version }) => footprint.withdrawFootprintRequest(requestId, version), onSuccess: () => invalidate() });
}

export function useSuggestTerm(): UseMutationResult<ProposalRef, unknown, TermSuggest> {
  return useMutation({ mutationFn: (body) => footprint.suggestTerm(body) });
}
