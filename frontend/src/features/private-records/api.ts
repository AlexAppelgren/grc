import { api } from '@/shared/utils/api-client';

import type { PrivateProposalApproveBody, PrivateProposalPage, PrivateProposalRejectBody, PrivateProposalRow } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1) over the bank's own queue
// (backend/apps/proposals/api.py, "The bank's own queue"). GET /private-proposals pages
// like every list: 20 rows by default and 100 at most, oldest first, `total` counting
// every row. There is no read of one proposal, so the detail finds its row in the queue.

const PRIVATE_PROPOSALS = '/api/v1/private-proposals';

/** The queue screen's page, the route's default. */
export const PRIVATE_QUEUE_PAGE = 20;

/** The route's largest page (API_PAGE_SIZE_MAX). */
export const PRIVATE_QUEUE_PAGE_MAX = 100;

export async function listPrivateProposals(query: { limit?: number; offset?: number } = {}): Promise<PrivateProposalPage> {
  const params: Record<string, string> = {};
  if (query.limit !== undefined) params.limit = String(query.limit);
  if (query.offset !== undefined && query.offset > 0) params.offset = String(query.offset);
  return (await api.get<PrivateProposalPage>(PRIVATE_PROPOSALS, { params })).data;
}

/** The proposal `proposalId` from the bank's own queue, or null when the queue holds no such row. */
export async function findPrivateProposal(proposalId: string): Promise<PrivateProposalRow | null> {
  for (let offset = 0; ; offset += PRIVATE_QUEUE_PAGE_MAX) {
    const page = await listPrivateProposals({ limit: PRIVATE_QUEUE_PAGE_MAX, offset });
    const row = page.items.find((item) => item.id === proposalId);
    if (row !== undefined) return row;
    if (page.items.length === 0 || offset + page.items.length >= page.total) return null;
  }
}

export async function approvePrivateProposal(proposalId: string, body: PrivateProposalApproveBody): Promise<PrivateProposalRow> {
  return (await api.post<PrivateProposalRow>(`${PRIVATE_PROPOSALS}/${proposalId}/approve`, body)).data;
}

export async function rejectPrivateProposal(proposalId: string, body: PrivateProposalRejectBody): Promise<PrivateProposalRow> {
  return (await api.post<PrivateProposalRow>(`${PRIVATE_PROPOSALS}/${proposalId}/reject`, body)).data;
}
