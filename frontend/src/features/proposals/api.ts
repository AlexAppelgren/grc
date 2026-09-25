import { api } from '@/shared/utils/api-client';

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
  TaxonomyTermPage,
  TenantProposalPage,
  TenantProposalQuery,
} from './types';

// Thin typed wrappers returning `.data` (playbook 6.1): the console queue's
// four real routes (PRO-01, PRO-02, PRO-03, AC-PRO2). GET /proposals pages
// like every list (backend/apps/proposals/api.py `list_proposals`): 20 rows
// by default and 100 at most, oldest first unless `order` asks for the newest,
// with `total` counting every match. It filters by origin and notMine itself,
// so a filter reaches every page.

const PROPOSALS = '/api/v1/proposals';

export async function listProposals(query: ProposalQuery = {}): Promise<ProposalPage> {
  const params: Record<string, string> = {};
  if (query.status !== undefined && query.status !== '') params.status = query.status;
  if (query.kind !== undefined && query.kind !== '') params.kind = query.kind;
  if (query.targetList !== undefined && query.targetList !== '') params.targetList = query.targetList;
  if (query.origin !== undefined && query.origin !== '') params.origin = query.origin;
  if (query.notMine === true) params.notMine = 'true';
  if (query.order !== undefined) params.order = query.order;
  if (query.limit !== undefined) params.limit = String(query.limit);
  if (query.offset !== undefined && query.offset > 0) params.offset = String(query.offset);
  return (await api.get<ProposalPage>(PROPOSALS, { params })).data;
}

export async function getProposal(proposalId: string): Promise<ProposalDetail> {
  return (await api.get<ProposalDetail>(`${PROPOSALS}/${proposalId}`)).data;
}

export async function approveProposal(proposalId: string, body: ProposalApproveBody): Promise<ProposalRow> {
  return (await api.post<ProposalRow>(`${PROPOSALS}/${proposalId}/approve`, body)).data;
}

export async function rejectProposal(proposalId: string, body: ProposalRejectBody): Promise<ProposalRow> {
  return (await api.post<ProposalRow>(`${PROPOSALS}/${proposalId}/reject`, body)).data;
}

// What this tenant itself proposed on a library list (GET /tenant/proposals).
const TENANT_PROPOSALS = '/api/v1/tenant/proposals';

export async function listTenantProposals(query: TenantProposalQuery = {}): Promise<TenantProposalPage> {
  const params: Record<string, string> = {};
  if (query.status !== undefined && query.status !== '') params.status = query.status;
  if (query.kind !== undefined && query.kind !== '') params.kind = query.kind;
  if (query.targetList !== undefined && query.targetList !== '') params.targetList = query.targetList;
  return (await api.get<TenantProposalPage>(TENANT_PROPOSALS, { params })).data;
}

// A batch proposal (PRO-04): one queue entry with a row per record. Deciding it
// asks for a fresh passkey assertion, which the client's step-up handler supplies.
const BATCHES = '/api/v1/proposal-batches';

export async function getProposalBatch(batchId: string): Promise<ProposalBatch> {
  return (await api.get<ProposalBatch>(`${BATCHES}/${batchId}`)).data;
}

export async function decideProposalBatch(batchId: string, body: ProposalBatchDecision): Promise<ProposalBatch> {
  return (await api.post<ProposalBatch>(`${BATCHES}/${batchId}/decide`, body)).data;
}

// The console's re-tag (AGT-05): a job whose status names the batch it produced.
const RETAG_REQUESTS = '/api/v1/console/research-requests';

export async function createRetagRequest(body: RetagRequestInput): Promise<RetagRequest> {
  return (await api.post<RetagRequest>(RETAG_REQUESTS, body)).data;
}

export async function getRetagRequest(requestId: string): Promise<RetagRequest> {
  return (await api.get<RetagRequest>(`${RETAG_REQUESTS}/${requestId}`)).data;
}

/** Every live taxonomy term, across dimensions, for the re-tag form's near match. */
export async function listTaxonomyTerms(): Promise<TaxonomyTerm[]> {
  return (await api.get<TaxonomyTermPage>('/api/v1/taxonomy/terms')).data.items;
}
