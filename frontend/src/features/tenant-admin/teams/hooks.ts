'use client';

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { adminKeys } from '@/features/tenant-admin/hooks';
import * as teams from '@/features/tenant-admin/teams/api';
import type { TeamDraft } from '@/features/tenant-admin/teams/api';
import type { Member } from '@/features/tenant-admin/types';
import { vocabularyKeys } from '@/features/vocabularies/hooks';
import { referenceKeys } from '@/features/shared/reference';

// Query keys and invalidation for the teams (playbook 6.1). A team added,
// renamed or moved here is a row of the `team` list, so the list's own query and every
// picker reading it refetch too; a member's teams refetch the member list.

export const teamKeys = {
  all: referenceKeys.teams,
};

function useInvalidateTeams(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: teamKeys.all });
    await queryClient.invalidateQueries({ queryKey: vocabularyKeys.list('team') });
  };
}

export function useCreateTeam(): UseMutationResult<void, unknown, TeamDraft> {
  const invalidate = useInvalidateTeams();
  return useMutation({ mutationFn: (draft) => teams.createTeam(draft), onSuccess: () => invalidate() });
}

export function useUpdateTeam(): UseMutationResult<void, unknown, { key: string; draft: TeamDraft; version: number | undefined }> {
  const invalidate = useInvalidateTeams();
  // A refused change refetches too, so a stale_write leaves the row as it now stands.
  return useMutation({ mutationFn: ({ key, draft, version }) => teams.updateTeam(key, draft, version), onSettled: () => invalidate() });
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

