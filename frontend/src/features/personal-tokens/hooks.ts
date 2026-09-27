'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { listEntries } from '@/features/agent-access/api';
import type { AccessEntryPage } from '@/features/agent-access/types';
import { createMyToken, listMyTokens, revokeMyToken } from '@/features/personal-tokens/api';
import type { PersonalTokenCreate, PersonalTokenCreated, PersonalTokensPage } from '@/features/personal-tokens/types';

// Query keys and invalidation (playbook 6.1). Screens call these and render.

export const tokenKeys = {
  list: ['me', 'tokens'] as const,
  entries: ['me', 'tokens', 'agent-access'] as const,
};

export function useMyTokens(): UseQueryResult<PersonalTokensPage> {
  return useQuery({ queryKey: tokenKeys.list, queryFn: listMyTokens });
}

/** The bank's agent access entries a token may name; the list needs agent_access.manage. */
export function useTokenEntries(enabled: boolean): UseQueryResult<AccessEntryPage> {
  return useQuery({ queryKey: tokenKeys.entries, queryFn: listEntries, enabled });
}

export function useCreateMyToken(): UseMutationResult<PersonalTokenCreated, unknown, PersonalTokenCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createMyToken,
    // The answer carries the plain token, shown once: no grace period in the mutation cache.
    gcTime: 0,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tokenKeys.list }),
  });
}

export function useRevokeMyToken(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: revokeMyToken, onSuccess: () => queryClient.invalidateQueries({ queryKey: tokenKeys.list }) });
}
