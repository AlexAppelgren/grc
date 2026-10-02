'use client';

import { skipToken, useMutation, useQueries, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { termRowsQuery } from '@/features/footprint/hooks';
import { scopeTermsOf } from '@/features/watch/api';
import { STEP_UP_REQUIRED_CODE } from '@/shared/utils/api-client';
import { hasProblemCode } from '@/shared/utils/problem';

import * as proposals from './api';
import type {
  ProposalApproveBody,
  ProposalBatch,
  ProposalBatchDecision,
  ProposalDetail,
  ProposalPage,
  ProposalQuery,
  ProposalRejectBody,
  ProposalRow,
  RetagRequest,
  RetagRequestInput,
  TaxonomyTerm,
  TenantProposalPage,
  TenantProposalQuery,
} from './types';

// Query keys and invalidation for the console queue (playbook 6.1). The
// filters are part of the key, so narrowing the queue re-reads rather than
// filters a stale page.

export const proposalKeys = {
  all: ['proposals'] as const,
  list: (query: ProposalQuery) => ['proposals', 'list', query] as const,
  detail: (id: string) => ['proposals', 'detail', id] as const,
  batch: (id: string) => ['proposals', 'batch', id] as const,
  retag: (id: string) => ['proposals', 'retag', id] as const,
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

/** A proposal approving many could not approve, by its title, with the server's answer. */
export interface ApprovalRefusal {
  id: string;
  title: string;
  error: unknown;
}

export interface ApproveManyOutcome {
  approved: number;
  refused: ApprovalRefusal[];
}

/**
 * Approves each proposal in turn through the one approve route (PRO-02), with an empty
 * note, exactly as if it were opened alone: four eyes, the passkey step-up and the audit
 * row are that route's own, and there is no second door. The API client opens the passkey
 * prompt on the first call's `step_up_required` and retries it; the rest ride that fresh
 * assertion, and a lapse mid-way asks again. A refusal is kept with its title and the run
 * goes on, except when the prompt was closed without a passkey: every later call would ask
 * again, so the rest are left waiting. `onDone` hears how many have been tried.
 */
export async function approveInTurn(rows: readonly Pick<ProposalRow, 'id' | 'title'>[], onDone: (count: number) => void): Promise<ApproveManyOutcome> {
  const outcome: ApproveManyOutcome = { approved: 0, refused: [] };
  for (const [index, row] of rows.entries()) {
    try {
      await proposals.approveProposal(row.id, { note: '' });
      outcome.approved += 1;
    } catch (error) {
      outcome.refused.push({ id: row.id, title: row.title, error });
      if (hasProblemCode(error, STEP_UP_REQUIRED_CODE)) break;
    }
    onDone(index + 1);
  }
  return outcome;
}

/** Approve many from the queue, one call after another; the queue re-reads however it ended. `done` counts the calls made. */
export function useApproveMany(): UseMutationResult<ApproveManyOutcome, unknown, readonly Pick<ProposalRow, 'id' | 'title'>[]> & { done: number } {
  const queryClient = useQueryClient();
  const [done, setDone] = useState(0);
  const mutation = useMutation({
    mutationFn: (rows: readonly Pick<ProposalRow, 'id' | 'title'>[]) => {
      setDone(0);
      return approveInTurn(rows, setDone);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: proposalKeys.all }),
  });
  return { ...mutation, done };
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
 * `scopeTermsOf`), rather than showing the raw key. Usually one or two dimensions, held
 * for five minutes like the feed's own read, since scope terms change rarely.
 */
export function useScopeTermLabels(refs: readonly string[]): { labelOf: (ref: string) => string; isPending: boolean } {
  const dimensions = useMemo(() => [...new Set(refs.map((ref) => ref.split(':')[0]).filter((d): d is string => d !== undefined && d !== ''))], [refs]);
  const results = useQueries({
    queries: dimensions.map((dimension) => ({ ...termRowsQuery(dimension), select: scopeTermsOf })),
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

// ——— batch proposals and the console's re-tag (PRO-04, AGT-05) ——————————————————

export function useProposalBatch(batchId: string): UseQueryResult<ProposalBatch> {
  return useQuery({ queryKey: proposalKeys.batch(batchId), queryFn: () => proposals.getProposalBatch(batchId) });
}

/** Decides rows and the rest in one call; the answer is the batch as it then stands, and the queue re-reads. */
export function useDecideProposalBatch(batchId: string): UseMutationResult<ProposalBatch, unknown, ProposalBatchDecision> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => proposals.decideProposalBatch(batchId, body),
    onSuccess: async (batch) => {
      queryClient.setQueryData(proposalKeys.batch(batchId), batch);
      await queryClient.invalidateQueries({ queryKey: ['proposals', 'list'] });
    },
  });
}

export function useCreateRetagRequest(): UseMutationResult<RetagRequest, unknown, RetagRequestInput> {
  return useMutation({ mutationFn: (body) => proposals.createRetagRequest(body) });
}

/** How often a re-tag request is read again while its run works. */
export const RETAG_POLL_MS = 3000;

/** The request is still working: it names no batch yet and its run has not ended. */
export function retagInFlight(request: RetagRequest | undefined): boolean {
  return request !== undefined && (request.batchProposalId ?? null) === null && (request.status === 'queued' || request.status === 'running');
}

/** Follows a re-tag request until its run has filed the batch or ended; idle until there is a request. */
export function useRetagRequest(requestId: string | null): UseQueryResult<RetagRequest> {
  return useQuery({
    queryKey: proposalKeys.retag(requestId ?? ''),
    queryFn: requestId === null ? skipToken : () => proposals.getRetagRequest(requestId),
    refetchInterval: (query) => (retagInFlight(query.state.data) ? RETAG_POLL_MS : false),
  });
}

/** Every live term the re-tag may name: a term of a dimension that mirrors the jurisdiction list is refused by the batch. */
export function useRetagTerms(): UseQueryResult<TaxonomyTerm[]> {
  return useQuery({
    queryKey: ['proposals', 'retag-terms'],
    queryFn: async () => (await proposals.listTaxonomyTerms()).filter((term) => term.active !== false && term.mirrored !== true),
    staleTime: 5 * 60_000,
  });
}
