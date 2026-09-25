'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as participants from './api';
import type { Participant, ParticipantInput, ParticipantPage, PersonRef, TeamPage } from './types';

// Query keys and invalidation for participants (playbook 6.1). Every write,
// a refused one included, refetches the list: a 409 means somebody else
// changed it first, and the list then shows what they did.

export const participantKeys = {
  all: ['participants'] as const,
  obligation: (obligationId: string) => ['participants', 'obligation', obligationId] as const,
  people: (permission: string) => ['participants', 'people', permission] as const,
  teams: ['participants', 'teams'] as const,
};

export function useObligationParticipants(obligationId: string): UseQueryResult<ParticipantPage> {
  return useQuery({ queryKey: participantKeys.obligation(obligationId), queryFn: () => participants.listObligationParticipants(obligationId) });
}

/** The picker's lists, read only while the picker is open. */
export function usePeople(permission: string, enabled: boolean): UseQueryResult<PersonRef[]> {
  return useQuery({ queryKey: participantKeys.people(permission), queryFn: () => participants.listPeople(permission), enabled });
}

export function useTeams(enabled: boolean): UseQueryResult<TeamPage> {
  return useQuery({ queryKey: participantKeys.teams, queryFn: participants.listTeams, enabled });
}

function useParticipantWrite<T, V>(obligationId: string, write: (variables: V) => Promise<T>): UseMutationResult<T, unknown, V> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: write,
    onSettled: () => queryClient.invalidateQueries({ queryKey: participantKeys.obligation(obligationId) }),
  });
}

export function useAddObligationParticipant(obligationId: string): UseMutationResult<Participant, unknown, ParticipantInput> {
  return useParticipantWrite(obligationId, (body: ParticipantInput) => participants.addObligationParticipant(obligationId, body));
}

/** Leaving one's own row and removing anyone else's are the same call; the server tells them apart. */
export function useRemoveObligationParticipant(obligationId: string): UseMutationResult<void, unknown, string> {
  return useParticipantWrite(obligationId, (participantId: string) => participants.removeObligationParticipant(obligationId, participantId));
}
