'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { adminKeys } from '@/features/tenant-admin/hooks';
import * as teams from '@/features/tenant-admin/teams/api';
import type { Team } from '@/features/tenant-admin/teams/api';
import type { Member } from '@/features/tenant-admin/types';
import { vocabularyKeys } from '@/features/vocabularies/hooks';

// Query keys and invalidation for the teams (playbook 6.1). A team added or
// renamed here is a row of the `team` list, so the list's own query and every
// picker reading it refetch too; a member's teams refetch the member list.

export const teamKeys = {
  all: ['tenant', 'teams'] as const,
};

export function useTeams(): UseQueryResult<Team[]> {
  return useQuery({ queryKey: teamKeys.all, queryFn: teams.listTeams });
}

function useInvalidateTeams(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: teamKeys.all });
    await queryClient.invalidateQueries({ queryKey: vocabularyKeys.list('team') });
  };
}

export function useCreateTeam(): UseMutationResult<void, unknown, Record<string, string>> {
  const invalidate = useInvalidateTeams();
  return useMutation({ mutationFn: (labels) => teams.createTeam(labels), onSuccess: () => invalidate() });
}

export function useRenameTeam(): UseMutationResult<void, unknown, { key: string; labels: Record<string, string>; version: number | undefined }> {
  const invalidate = useInvalidateTeams();
  // A refused rename refetches too, so a stale_write leaves the row as it now stands.
  return useMutation({ mutationFn: ({ key, labels, version }) => teams.renameTeam(key, labels, version), onSettled: () => invalidate() });
}

export function useSetMemberTeams(): UseMutationResult<Member, unknown, { userId: string; teams: readonly string[] }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, teams: keys }) => teams.setMemberTeams(userId, keys),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.members });
      await queryClient.invalidateQueries({ queryKey: teamKeys.all });
    },
  });
}

