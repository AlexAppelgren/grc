'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as agents from '@/features/agents/api';
import type {
  AgentDefinitionDetail,
  AgentDefinitionPage,
  AgentRunPage,
  AgentVersion,
  AgentVersionInput,
  PlatformAgentSettings,
  PlatformAgentSettingsInput,
} from '@/features/agents/types';

// Query keys, invalidation and the console's reads and writes (playbook 6.1).
// Screens call these and render; nothing here knows a role name. The bank's
// own agent screens add their hooks beside these when they are built.

export const agentKeys = {
  definitions: ['console', 'agents', 'definitions'] as const,
  definition: (agentKey: string) => ['console', 'agents', 'definitions', agentKey] as const,
  settings: (agentKey: string) => ['console', 'agents', 'settings', agentKey] as const,
  platformRuns: ['console', 'agents', 'platform-runs'] as const,
};

export function useAgentDefinitions(): UseQueryResult<AgentDefinitionPage> {
  return useQuery({ queryKey: agentKeys.definitions, queryFn: agents.listAgentDefinitions });
}

export function useAgentDefinition(agentKey: string): UseQueryResult<AgentDefinitionDetail> {
  return useQuery({ queryKey: agentKeys.definition(agentKey), queryFn: () => agents.getAgentDefinition(agentKey) });
}

export function usePlatformAgentSettings(agentKey: string): UseQueryResult<PlatformAgentSettings> {
  return useQuery({ queryKey: agentKeys.settings(agentKey), queryFn: () => agents.getPlatformAgentSettings(agentKey) });
}

export function useRecentPlatformRuns(): UseQueryResult<AgentRunPage> {
  return useQuery({ queryKey: agentKeys.platformRuns, queryFn: agents.listRecentPlatformRuns });
}

/** A new or retired version changes the definition and the list's current version alike. */
function useInvalidateDefinition(agentKey: string): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: agentKeys.definition(agentKey) });
    await queryClient.invalidateQueries({ queryKey: agentKeys.definitions, exact: true });
  };
}

export function usePublishAgentVersion(agentKey: string): UseMutationResult<AgentVersion, unknown, AgentVersionInput> {
  const invalidate = useInvalidateDefinition(agentKey);
  return useMutation({ mutationFn: (body) => agents.publishAgentVersion(agentKey, body), onSuccess: invalidate });
}

export function useRetireAgentVersion(agentKey: string): UseMutationResult<AgentVersion, unknown, number> {
  const invalidate = useInvalidateDefinition(agentKey);
  return useMutation({ mutationFn: (versionNo) => agents.retireAgentVersion(agentKey, versionNo), onSuccess: invalidate });
}

export function useUpdatePlatformAgentSettings(agentKey: string): UseMutationResult<PlatformAgentSettings, unknown, PlatformAgentSettingsInput> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => agents.updatePlatformAgentSettings(agentKey, body),
    onSuccess: (saved) => queryClient.setQueryData(agentKeys.settings(agentKey), saved),
  });
}
