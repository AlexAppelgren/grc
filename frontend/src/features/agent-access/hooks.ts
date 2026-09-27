import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as access from '@/features/agent-access/api';
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

export const accessKeys = {
  all: ['tenant', 'agent-access'] as const,
  list: ['tenant', 'agent-access', 'list'] as const,
  entry: (entryId: string) => ['tenant', 'agent-access', 'entry', entryId] as const,
  calls: (entryId: string, offset: number) => ['tenant', 'agent-access', 'calls', entryId, offset] as const,
  orgUnits: ['tenant', 'org-units', 'picker'] as const,
  products: ['tenant', 'products', 'picker'] as const,
  reach: ['tenant', 'reach'] as const,
};

export function useAccessEntries(): UseQueryResult<AccessEntryPage> {
  return useQuery({ queryKey: accessKeys.list, queryFn: access.listEntries });
}

export function useAccessEntry(entryId: string): UseQueryResult<AccessEntry> {
  return useQuery({ queryKey: accessKeys.entry(entryId), queryFn: () => access.getEntry(entryId) });
}

export function useAccessCalls(entryId: string, offset: number): UseQueryResult<AccessCallPage> {
  return useQuery({ queryKey: accessKeys.calls(entryId, offset), queryFn: () => access.listCalls(entryId, offset) });
}

export function useOrgUnits(enabled: boolean): UseQueryResult<OrgUnit[]> {
  return useQuery({ queryKey: accessKeys.orgUnits, queryFn: access.listOrgUnits, enabled });
}

export function useProducts(enabled: boolean): UseQueryResult<Product[]> {
  return useQuery({ queryKey: accessKeys.products, queryFn: access.listProducts, enabled });
}

/** Tenant reach is read under security.manage; without it the state is unknown, never guessed. */
export function useTenantReach(enabled: boolean): UseQueryResult<TenantReach> {
  return useQuery({ queryKey: accessKeys.reach, queryFn: access.getReach, enabled });
}

// An entry write answers the entry: it replaces the cached one and the list refetches.
function useEntryWrite<V>(write: (vars: V) => Promise<AccessEntry>): UseMutationResult<AccessEntry, unknown, V> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: write,
    onSuccess: async (entry) => {
      queryClient.setQueryData(accessKeys.entry(entry.id), entry);
      await queryClient.invalidateQueries({ queryKey: accessKeys.list });
    },
  });
}

export function useRegisterEntry(): UseMutationResult<AccessEntry, unknown, AccessEntryInput> {
  return useEntryWrite(access.registerEntry);
}

export function useUpdateEntry(): UseMutationResult<AccessEntry, unknown, { entry: AccessEntry; body: AccessEntryUpdate }> {
  return useEntryWrite(({ entry, body }) => access.updateEntry(entry.id, entry.version, body));
}

export function useRevokeEntry(): UseMutationResult<AccessEntry, unknown, AccessEntry> {
  return useEntryWrite((entry) => access.revokeEntry(entry.id, entry.version));
}

export function useSetEntryReach(): UseMutationResult<AccessEntry, unknown, { entry: AccessEntry; enabled: boolean }> {
  return useEntryWrite(({ entry, enabled }) => access.setEntryReach(entry.id, entry.version, enabled));
}

// A key write changes the entry's credential list: the entry and the list refetch.
function useKeyWrite<V, R>(entryId: string, write: (vars: V) => Promise<R>): UseMutationResult<R, unknown, V> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: write,
    onSuccess: async () => {
      await Promise.all([queryClient.invalidateQueries({ queryKey: accessKeys.entry(entryId) }), queryClient.invalidateQueries({ queryKey: accessKeys.list })]);
    },
  });
}

export function useCreateKey(entryId: string): UseMutationResult<AccessKeyCreated, unknown, AccessKeyInput> {
  return useKeyWrite(entryId, (body: AccessKeyInput) => access.createKey(entryId, body));
}

export function useRevokeKey(entryId: string): UseMutationResult<AccessKey, unknown, string> {
  return useKeyWrite(entryId, (keyId: string) => access.revokeKey(entryId, keyId));
}

// Every reach write refetches the state: the view names who switched it and what waits.
function useReachWrite<V, R>(write: (vars: V) => Promise<R>): UseMutationResult<R, unknown, V> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: write, onSettled: () => queryClient.invalidateQueries({ queryKey: accessKeys.reach }) });
}

export function useRequestReach(): UseMutationResult<TenantReachRequest, unknown, void> {
  return useReachWrite(() => access.requestReach());
}

export function useApproveReach(): UseMutationResult<TenantReachRequest, unknown, TenantReachRequest> {
  return useReachWrite(access.approveReach);
}

export function useRejectReach(): UseMutationResult<TenantReachRequest, unknown, TenantReachRequest> {
  return useReachWrite(access.rejectReach);
}

export function useSwitchOffReach(): UseMutationResult<TenantReach, unknown, void> {
  return useReachWrite(() => access.switchOffReach());
}
