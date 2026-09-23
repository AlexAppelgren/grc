'use client';

import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type UseInfiniteQueryResult, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import type { ProposalRef } from '@/features/vocabularies/types';

import * as footprint from './api';
import type {
  Footprint,
  FootprintChangeRequest,
  FootprintPreview,
  FootprintRejectBody,
  FootprintRequestCreate,
  JurisdictionRef,
  Market,
  Page,
  TaxonomyDimension,
  TaxonomyTerm,
  TermSuggest,
} from './types';

// Query keys and invalidation for the footprint screen (playbook 6.1). The
// footprint and its requests are read in parallel, never chained; a decision
// refreshes both, because an approval changes the footprint itself. Watching a
// market refreshes the footprint alone, whether it saved or not, so a toggle
// always shows the level the server holds.

export const footprintKeys = {
  footprint: ['tenant', 'footprint'] as const,
  requests: ['tenant', 'footprint', 'requests'] as const,
  terms: (dimension?: string) => ['taxonomy', 'terms', dimension ?? 'all'] as const,
  dimensions: ['taxonomy', 'dimensions'] as const,
  jurisdictions: ['reference', 'jurisdictions'] as const,
};

export const REQUEST_HISTORY_PAGE = 20;

export function useFootprint(): UseQueryResult<Footprint> {
  return useQuery({ queryKey: footprintKeys.footprint, queryFn: footprint.getFootprint });
}

/** The request history, one page at a time: the next page begins where the pages read so far end. */
export function useFootprintRequests(): UseInfiniteQueryResult<{ pages: Page<FootprintChangeRequest>[] }> {
  return useInfiniteQuery({
    queryKey: footprintKeys.requests,
    queryFn: ({ pageParam }) => footprint.listFootprintRequests({ limit: REQUEST_HISTORY_PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last: Page<FootprintChangeRequest>, pages: Page<FootprintChangeRequest>[]) => {
      const read = pages.reduce((sum, page) => sum + page.items.length, 0);
      return read < last.total ? read : undefined;
    },
  });
}

export function useTerms(dimension?: string): UseQueryResult<TaxonomyTerm[]> {
  return useQuery({ queryKey: footprintKeys.terms(dimension), queryFn: () => footprint.listTerms(dimension), staleTime: 5 * 60_000 });
}

export function useDimensions(): UseQueryResult<TaxonomyDimension[]> {
  return useQuery({ queryKey: footprintKeys.dimensions, queryFn: footprint.listDimensions, staleTime: 5 * 60_000 });
}

export function useJurisdictions(): UseQueryResult<JurisdictionRef[]> {
  return useQuery({ queryKey: footprintKeys.jurisdictions, queryFn: footprint.listJurisdictions, staleTime: 5 * 60_000 });
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

export function useWatchMarket(): UseMutationResult<Market, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (key) => footprint.watchMarket(key), onSettled: () => queryClient.invalidateQueries({ queryKey: footprintKeys.footprint, exact: true }) });
}

export function useUnwatchMarket(): UseMutationResult<Market, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (key) => footprint.unwatchMarket(key), onSettled: () => queryClient.invalidateQueries({ queryKey: footprintKeys.footprint, exact: true }) });
}

export function useSuggestTerm(): UseMutationResult<ProposalRef, unknown, TermSuggest> {
  return useMutation({ mutationFn: (body) => footprint.suggestTerm(body) });
}
