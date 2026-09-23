import { api } from '@/shared/utils/api-client';

import type { ProposalApproveBody, ProposalPage, ProposalQuery, ProposalRejectBody, ProposalRow, TenantProposalPage, TenantProposalQuery } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1): the console queue's
// four real routes (PRO-01, PRO-02, PRO-03, AC-PRO2). GET /proposals pages
// like every list (backend/apps/proposals/api.py `list_proposals`): 20 rows
// by default and 100 at most, oldest first, with `total` counting every match.
// It filters by origin and notMine itself, so a filter reaches every page.

const PROPOSALS = '/api/v1/proposals';

export async function listProposals(query: ProposalQuery = {}): Promise<ProposalPage> {
  const params: Record<string, string> = {};
  if (query.status !== undefined && query.status !== '') params.status = query.status;
  if (query.kind !== undefined && query.kind !== '') params.kind = query.kind;
  if (query.targetList !== undefined && query.targetList !== '') params.targetList = query.targetList;
  if (query.origin !== undefined && query.origin !== '') params.origin = query.origin;
  if (query.notMine === true) params.notMine = 'true';
  if (query.limit !== undefined) params.limit = String(query.limit);
  return (await api.get<ProposalPage>(PROPOSALS, { params })).data;
}

export async function getProposal(proposalId: string): Promise<ProposalRow> {
  return (await api.get<ProposalRow>(`${PROPOSALS}/${proposalId}`)).data;
}

export async function approveProposal(proposalId: string, body: ProposalApproveBody): Promise<ProposalRow> {
  return (await api.post<ProposalRow>(`${PROPOSALS}/${proposalId}/approve`, body)).data;
}

export async function rejectProposal(proposalId: string, body: ProposalRejectBody): Promise<ProposalRow> {
  return (await api.post<ProposalRow>(`${PROPOSALS}/${proposalId}/reject`, body)).data;
}

// GET /tenant/proposals is chunk4-T10's route and is not on `main` yet (see the module
// note in types.ts on `TenantProposalRow`).
const TENANT_PROPOSALS = '/api/v1/tenant/proposals';

export async function listTenantProposals(query: TenantProposalQuery = {}): Promise<TenantProposalPage> {
  const params: Record<string, string> = {};
  if (query.status !== undefined && query.status !== '') params.status = query.status;
  if (query.kind !== undefined && query.kind !== '') params.kind = query.kind;
  if (query.targetList !== undefined && query.targetList !== '') params.targetList = query.targetList;
  return (await api.get<TenantProposalPage>(TENANT_PROPOSALS, { params })).data;
}
