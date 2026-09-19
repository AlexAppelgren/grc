import type {
  ApiKey,
  ApiKeyCreate,
  ApiKeyCreated,
  Invitation,
  InviteBody,
  LanguageRef,
  LoginEvent,
  Member,
  MemberSession,
  MemberUpdate,
  Page,
  PageQuery,
  PermissionRef,
  RoleCreate,
  RoleUpdate,
  Tenant,
  TenantRole,
  TenantUpdate,
} from '@/features/tenant-admin/types';
import { api } from '@/shared/utils/api-client';

// Thin typed wrappers returning `.data` (playbook 6.1). Paths are the tenant
// admin routes under /api/v1 (CHUNK1_BRIEF.md). Step-up is the api client's
// business: a 403 step_up_required opens the prompt and retries once.

const TENANT = '/api/v1/tenant';
const REFERENCE = '/api/v1/reference';

const id = (value: string) => encodeURIComponent(value);

export async function getTenant(): Promise<Tenant> {
  return (await api.get<Tenant>(TENANT)).data;
}

export async function updateTenant(body: TenantUpdate): Promise<Tenant> {
  return (await api.patch<Tenant>(TENANT, body)).data;
}

export async function listMembers(query: PageQuery): Promise<Page<Member>> {
  return (await api.get<Page<Member>>(`${TENANT}/members`, { params: query })).data;
}

export async function inviteMember(body: InviteBody): Promise<Invitation> {
  return (await api.post<Invitation>(`${TENANT}/members`, body)).data;
}

export async function updateMember(userId: string, body: MemberUpdate): Promise<Member> {
  return (await api.patch<Member>(`${TENANT}/members/${id(userId)}`, body)).data;
}

export async function deactivateMember(userId: string): Promise<void> {
  await api.delete(`${TENANT}/members/${id(userId)}`);
}

export async function reissueEnrolment(userId: string): Promise<void> {
  await api.post(`${TENANT}/members/${id(userId)}/reissue-enrolment`, {});
}

export async function listMemberSessions(userId: string): Promise<MemberSession[]> {
  return (await api.get<MemberSession[]>(`${TENANT}/members/${id(userId)}/sessions`)).data;
}

export async function revokeMemberSessions(userId: string): Promise<void> {
  await api.delete(`${TENANT}/members/${id(userId)}/sessions`);
}

export async function listInvitations(query: PageQuery): Promise<Page<Invitation>> {
  return (await api.get<Page<Invitation>>(`${TENANT}/invitations`, { params: query })).data;
}

export async function resendInvitation(invitationId: string): Promise<Invitation> {
  return (await api.post<Invitation>(`${TENANT}/invitations/${id(invitationId)}/resend`, {})).data;
}

export async function revokeInvitation(invitationId: string): Promise<void> {
  await api.delete(`${TENANT}/invitations/${id(invitationId)}`);
}

export async function listRoles(): Promise<TenantRole[]> {
  return (await api.get<TenantRole[]>(`${TENANT}/roles`)).data;
}

export async function createRole(body: RoleCreate): Promise<TenantRole> {
  return (await api.post<TenantRole>(`${TENANT}/roles`, body)).data;
}

export async function updateRole(key: string, body: RoleUpdate): Promise<TenantRole> {
  return (await api.patch<TenantRole>(`${TENANT}/roles/${id(key)}`, body)).data;
}

export async function retireRole(key: string): Promise<TenantRole> {
  return (await api.post<TenantRole>(`${TENANT}/roles/${id(key)}/retire`, {})).data;
}

export async function listPermissions(): Promise<PermissionRef[]> {
  return (await api.get<PermissionRef[]>(`${REFERENCE}/permissions`)).data;
}

export async function listLanguages(): Promise<LanguageRef[]> {
  return (await api.get<LanguageRef[]>(`${REFERENCE}/languages`)).data;
}

export async function listApiKeys(query: PageQuery): Promise<Page<ApiKey>> {
  return (await api.get<Page<ApiKey>>(`${TENANT}/api-keys`, { params: query })).data;
}

export async function createApiKey(body: ApiKeyCreate): Promise<ApiKeyCreated> {
  return (await api.post<ApiKeyCreated>(`${TENANT}/api-keys`, body)).data;
}

export async function revokeApiKey(keyId: string): Promise<void> {
  await api.delete(`${TENANT}/api-keys/${id(keyId)}`);
}

export async function listSecurityLog(query: PageQuery): Promise<Page<LoginEvent>> {
  return (await api.get<Page<LoginEvent>>(`${TENANT}/security-log`, { params: query })).data;
}
