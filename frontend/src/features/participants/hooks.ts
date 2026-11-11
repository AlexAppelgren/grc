'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as participants from './api';
import type { Participant, ParticipantInput, ParticipantPage } from './types';

// Query keys and invalidation for participants (playbook 6.1). Every write,
// a refused one included, refetches the list: a 409 means somebody else
// changed it first, and the list then shows what they did.

export const participantKeys = {
  all: ['participants'] as const,
  obligation: (obligationId: string) => ['participants', 'obligation', obligationId] as const,
  case: (changeId: string) => ['participants', 'case', changeId] as const,
};

export function useObligationParticipants(obligationId: string): UseQueryResult<ParticipantPage> {
  return useQuery({ queryKey: participantKeys.obligation(obligationId), queryFn: () => participants.listObligationParticipants(obligationId) });
}

function useParticipantWrite<T, V>(listKey: readonly string[], write: (variables: V) => Promise<T>): UseMutationResult<T, unknown, V> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: write,
    onSettled: () => queryClient.invalidateQueries({ queryKey: listKey }),
  });
}

export function useAddObligationParticipant(obligationId: string): UseMutationResult<Participant, unknown, ParticipantInput> {
  return useParticipantWrite(participantKeys.obligation(obligationId), (body: ParticipantInput) => participants.addObligationParticipant(obligationId, body));
}

/** Leaving one's own row and removing anyone else's are the same call; the server tells them apart. */
export function useRemoveObligationParticipant(obligationId: string): UseMutationResult<void, unknown, string> {
  return useParticipantWrite(participantKeys.obligation(obligationId), (participantId: string) =>
    participants.removeObligationParticipant(obligationId, participantId),
  );
}

// c9-fe-case-participants: the case's participants, whose teams are also the
// assessment's contributor teams, so both panels read and refetch one list.
export function useCaseParticipants(changeId: string): UseQueryResult<ParticipantPage> {
  return useQuery({ queryKey: participantKeys.case(changeId), queryFn: () => participants.listCaseParticipants(changeId) });
}

export function useAddCaseParticipant(changeId: string): UseMutationResult<Participant, unknown, ParticipantInput> {
  return useParticipantWrite(participantKeys.case(changeId), (body: ParticipantInput) => participants.addCaseParticipant(changeId, body));
}

/** Leave, Remove and taking a contributor team off are the same call; the server tells them apart. */
export function useRemoveCaseParticipant(changeId: string): UseMutationResult<void, unknown, string> {
  return useParticipantWrite(participantKeys.case(changeId), (participantId: string) => participants.removeCaseParticipant(changeId, participantId));
}
