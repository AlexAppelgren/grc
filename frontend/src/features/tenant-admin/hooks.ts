'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { identityKeys } from '@/features/identity/hooks';
import * as admin from '@/features/tenant-admin/api';
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
  PermissionRef,
  RoleCreate,
  RoleUpdate,
  Tenant,
  TenantRole,
  TenantUpdate,
} from '@/features/tenant-admin/types';

// Query keys and invalidation for the tenant admin screens (playbook 6.1).

export const adminKeys = {
  tenant: ['tenant'] as const,
  members: ['tenant', 'members'] as const,
  memberSessions: (userId: string) => ['tenant', 'members', userId, 'sessions'] as const,
  invitations: ['tenant', 'invitations'] as const,
  roles: ['tenant', 'roles'] as const,
  apiKeys: ['tenant', 'api-keys'] as const,
  securityLog: (offset: number, limit: number) => ['tenant', 'security-log', offset, limit] as const,
  permissions: ['reference', 'permissions'] as const,
  languages: ['reference', 'languages'] as const,
};

export const SECURITY_LOG_PAGE = 20;
// Members, invitations and keys: one page at the server's maximum; a tenant
// with more than a hundred members gets paging in a later chunk.
export const ADMIN_LIST_PAGE = 100;

export function useTenant(): UseQueryResult<Tenant> {
  return useQuery({ queryKey: adminKeys.tenant, queryFn: admin.getTenant });
}

export function useUpdateTenant(): UseMutationResult<Tenant, unknown, TenantUpdate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => admin.updateTenant(body),
    onSuccess: async (tenant) => {
      queryClient.setQueryData(adminKeys.tenant, tenant);
      await queryClient.invalidateQueries({ queryKey: identityKeys.me });
    },
  });
}

// `enabled` is false while nobody is signed in: the shell's account menu reads
// this list, and a shell still on screen as a person signs out fetches nothing.
export function useLanguages(enabled = true): UseQueryResult<LanguageRef[]> {
  return useQuery({ queryKey: adminKeys.languages, queryFn: admin.listLanguages, staleTime: 5 * 60_000, enabled });
}

export function useMembers(): UseQueryResult<Page<Member>> {
  return useQuery({ queryKey: adminKeys.members, queryFn: () => admin.listMembers({ limit: ADMIN_LIST_PAGE, offset: 0 }) });
}

export function useInvitations(): UseQueryResult<Page<Invitation>> {
  return useQuery({ queryKey: adminKeys.invitations, queryFn: () => admin.listInvitations({ limit: ADMIN_LIST_PAGE, offset: 0 }) });
}

function useInvalidateMembers(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: adminKeys.members });
    await queryClient.invalidateQueries({ queryKey: adminKeys.invitations });
  };
}

export function useInviteMember(): UseMutationResult<Invitation, unknown, InviteBody> {
  const invalidate = useInvalidateMembers();
  return useMutation({ mutationFn: (body) => admin.inviteMember(body), onSuccess: () => invalidate() });
}

export function useUpdateMember(): UseMutationResult<Member, unknown, { userId: string; body: MemberUpdate }> {
  const invalidate = useInvalidateMembers();
  return useMutation({ mutationFn: ({ userId, body }) => admin.updateMember(userId, body), onSuccess: () => invalidate() });
}

export function useDeactivateMember(): UseMutationResult<void, unknown, string> {
  const invalidate = useInvalidateMembers();
  return useMutation({ mutationFn: (userId) => admin.deactivateMember(userId), onSuccess: () => invalidate() });
}

export function useReissueEnrolment(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateMembers();
  return useMutation({
    mutationFn: (userId) => admin.reissueEnrolment(userId),
    onSuccess: async (_result, userId) => {
      await invalidate();
      await queryClient.invalidateQueries({ queryKey: adminKeys.memberSessions(userId) });
    },
  });
}

export function useMemberSessions(userId: string): UseQueryResult<MemberSession[]> {
  return useQuery({ queryKey: adminKeys.memberSessions(userId), queryFn: () => admin.listMemberSessions(userId), retry: false });
}

export function useRevokeMemberSessions(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateMembers();
  return useMutation({
    mutationFn: (userId) => admin.revokeMemberSessions(userId),
    onSuccess: async (_result, userId) => {
      await invalidate();
      await queryClient.invalidateQueries({ queryKey: adminKeys.memberSessions(userId) });
    },
  });
}

export function useResendInvitation(): UseMutationResult<Invitation, unknown, string> {
  const invalidate = useInvalidateMembers();
  return useMutation({ mutationFn: (invitationId) => admin.resendInvitation(invitationId), onSuccess: () => invalidate() });
}

export function useRevokeInvitation(): UseMutationResult<void, unknown, string> {
  const invalidate = useInvalidateMembers();
  return useMutation({ mutationFn: (invitationId) => admin.revokeInvitation(invitationId), onSuccess: () => invalidate() });
}

export function useRoles(): UseQueryResult<TenantRole[]> {
  return useQuery({ queryKey: adminKeys.roles, queryFn: admin.listRoles });
}

export function usePermissionsReference(): UseQueryResult<PermissionRef[]> {
  return useQuery({ queryKey: adminKeys.permissions, queryFn: admin.listPermissions, staleTime: 5 * 60_000 });
}

function useInvalidateRoles(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: adminKeys.roles });
    await queryClient.invalidateQueries({ queryKey: adminKeys.members });
  };
}

export function useCreateRole(): UseMutationResult<TenantRole, unknown, RoleCreate> {
  const invalidate = useInvalidateRoles();
  return useMutation({ mutationFn: (body) => admin.createRole(body), onSuccess: () => invalidate() });
}

export function useUpdateRole(): UseMutationResult<TenantRole, unknown, { key: string; body: RoleUpdate }> {
  const invalidate = useInvalidateRoles();
  return useMutation({ mutationFn: ({ key, body }) => admin.updateRole(key, body), onSuccess: () => invalidate() });
}

export function useRetireRole(): UseMutationResult<TenantRole, unknown, string> {
  const invalidate = useInvalidateRoles();
  return useMutation({ mutationFn: (key) => admin.retireRole(key), onSuccess: () => invalidate() });
}

export function useApiKeys(): UseQueryResult<Page<ApiKey>> {
  return useQuery({ queryKey: adminKeys.apiKeys, queryFn: () => admin.listApiKeys({ limit: ADMIN_LIST_PAGE, offset: 0 }) });
}

export function useCreateApiKey(): UseMutationResult<ApiKeyCreated, unknown, ApiKeyCreate> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (body) => admin.createApiKey(body), onSuccess: () => queryClient.invalidateQueries({ queryKey: adminKeys.apiKeys }) });
}

export function useRevokeApiKey(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (keyId) => admin.revokeApiKey(keyId), onSuccess: () => queryClient.invalidateQueries({ queryKey: adminKeys.apiKeys }) });
}

export function useSecurityLog(offset: number, limit: number = SECURITY_LOG_PAGE): UseQueryResult<Page<LoginEvent>> {
  return useQuery({ queryKey: adminKeys.securityLog(offset, limit), queryFn: () => admin.listSecurityLog({ offset, limit }), placeholderData: (previous) => previous });
}
