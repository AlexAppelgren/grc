import type {
  AccessCallPage,
  AccessEntry,
  AccessEntryInput,
  AccessEntryPage,
  AccessEntryUpdate,
  AccessKey,
  AccessKeyCreated,
  AccessKeyInput,
  OrgUnit,
  Product,
  TenantReach,
  TenantReachRequest,
} from '@/features/agent-access/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1) over the agent access
// routes (docs/plans/briefs/AGENT_ACCESS.md) and tenant reach (ACC-08). Every
// write asks for a passkey: the api client opens the prompt on the server's
// step_up_required and retries once. `version` goes out as If-Match.

const ACCESS = '/api/v1/agent-access';
const REACH = '/api/v1/tenant/reach';
const TENANT = '/api/v1/tenant';

/** The route maximum: an organisation's units, products and entries fit one page. */
export const MAX_PAGE = 100;
/** The access log's page (design/screens/admin-agent-access.html, "1 to 20 of 146"). */
export const CALLS_PAGE = 20;

const id = (value: string) => encodeURIComponent(value);
const versioned = (version: number) => ({ version });

export async function listEntries(): Promise<AccessEntryPage> {
  return (await api.get<AccessEntryPage>(ACCESS, { params: { limit: MAX_PAGE, offset: 0 } })).data;
}

export async function getEntry(entryId: string): Promise<AccessEntry> {
  return (await api.get<AccessEntry>(`${ACCESS}/${id(entryId)}`)).data;
}

export async function registerEntry(body: AccessEntryInput): Promise<AccessEntry> {
  return (await api.post<AccessEntry>(ACCESS, body)).data;
}

export async function updateEntry(entryId: string, version: number, body: AccessEntryUpdate): Promise<AccessEntry> {
  return (await api.patch<AccessEntry>(`${ACCESS}/${id(entryId)}`, body, versioned(version))).data;
}

export async function revokeEntry(entryId: string, version: number): Promise<AccessEntry> {
  return (await api.post<AccessEntry>(`${ACCESS}/${id(entryId)}/revoke`, {}, versioned(version))).data;
}

export async function setEntryReach(entryId: string, version: number, enabled: boolean): Promise<AccessEntry> {
  return (await api.put<AccessEntry>(`${ACCESS}/${id(entryId)}/tenant-reach`, { enabled }, versioned(version))).data;
}

export async function createKey(entryId: string, body: AccessKeyInput): Promise<AccessKeyCreated> {
  return (await api.post<AccessKeyCreated>(`${ACCESS}/${id(entryId)}/keys`, body)).data;
}

export async function revokeKey(entryId: string, keyId: string): Promise<AccessKey> {
  return (await api.post<AccessKey>(`${ACCESS}/${id(entryId)}/keys/${id(keyId)}/revoke`, {})).data;
}

export async function listCalls(entryId: string, offset: number): Promise<AccessCallPage> {
  return (await api.get<AccessCallPage>(`${ACCESS}/${id(entryId)}/calls`, { params: { limit: CALLS_PAGE, offset } })).data;
}

export async function listOrgUnits(): Promise<OrgUnit[]> {
  return (await api.get<{ items: OrgUnit[] }>(`${TENANT}/org-units`, { params: { limit: MAX_PAGE, offset: 0 } })).data.items;
}

export async function listProducts(): Promise<Product[]> {
  return (await api.get<{ items: Product[] }>(`${TENANT}/products`, { params: { limit: MAX_PAGE, offset: 0 } })).data.items;
}

export async function getReach(): Promise<TenantReach> {
  return (await api.get<TenantReach>(REACH)).data;
}

export async function requestReach(): Promise<TenantReachRequest> {
  return (await api.post<TenantReachRequest>(`${REACH}/requests`, {})).data;
}

export async function approveReach(request: TenantReachRequest): Promise<TenantReachRequest> {
  return (await api.post<TenantReachRequest>(`${REACH}/requests/${id(request.id)}/approve`, {}, versioned(request.version))).data;
}

export async function rejectReach(request: TenantReachRequest): Promise<TenantReachRequest> {
  return (await api.post<TenantReachRequest>(`${REACH}/requests/${id(request.id)}/reject`, {}, versioned(request.version))).data;
}

export async function switchOffReach(): Promise<TenantReach> {
  return (await api.post<TenantReach>(`${REACH}/off`, {})).data;
}
