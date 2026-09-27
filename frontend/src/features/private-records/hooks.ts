'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as privateRecords from './api';
import type { PrivateProposalApproveBody, PrivateProposalPage, PrivateProposalRejectBody, PrivateProposalRow } from './types';

// Query keys and invalidation for the bank's own queue (playbook 6.1). A decision
// re-reads the queue and the proposal it decided, so both show the new status.

export const privateRecordKeys = {
  all: ['private-records'] as const,
  list: (offset: number) => ['private-records', 'list', offset] as const,
  detail: (id: string) => ['private-records', 'detail', id] as const,
};

export function usePrivateProposals(offset: number): UseQueryResult<PrivateProposalPage> {
  return useQuery({ queryKey: privateRecordKeys.list(offset), queryFn: () => privateRecords.listPrivateProposals({ limit: privateRecords.PRIVATE_QUEUE_PAGE, offset }) });
}

export function usePrivateProposal(proposalId: string): UseQueryResult<PrivateProposalRow | null> {
  return useQuery({ queryKey: privateRecordKeys.detail(proposalId), queryFn: () => privateRecords.findPrivateProposal(proposalId) });
}

function useDecision<Body>(decide: (body: Body) => Promise<PrivateProposalRow>, proposalId: string): UseMutationResult<PrivateProposalRow, unknown, Body> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: decide,
    onSuccess: async (row) => {
      queryClient.setQueryData(privateRecordKeys.detail(proposalId), row);
      await queryClient.invalidateQueries({ queryKey: ['private-records', 'list'] });
    },
  });
}

/** Approve, behind the passkey step-up the API client runs on a 403 `step_up_required`. */
export function useApprovePrivateProposal(proposalId: string): UseMutationResult<PrivateProposalRow, unknown, PrivateProposalApproveBody> {
  return useDecision((body: PrivateProposalApproveBody) => privateRecords.approvePrivateProposal(proposalId, body), proposalId);
}

export function useRejectPrivateProposal(proposalId: string): UseMutationResult<PrivateProposalRow, unknown, PrivateProposalRejectBody> {
  return useDecision((body: PrivateProposalRejectBody) => privateRecords.rejectPrivateProposal(proposalId, body), proposalId);
}
