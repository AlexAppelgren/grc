'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as outOfOffice from './api';
import type { OutOfOffice, OutOfOfficeBody, Person } from './api';

export const outOfOfficeKeys = {
  mine: ['me', 'out-of-office'] as const,
  people: ['reference', 'people'] as const,
};

export function useOutOfOffice(): UseQueryResult<OutOfOffice> {
  return useQuery({ queryKey: outOfOfficeKeys.mine, queryFn: outOfOffice.getOutOfOffice });
}

export function usePeople(): UseQueryResult<Person[]> {
  return useQuery({ queryKey: outOfOfficeKeys.people, queryFn: outOfOffice.listPeople });
}

/** Sets or ends the absence; the answer is the absence as it now stands. */
export function useSetOutOfOffice(): UseMutationResult<OutOfOffice, unknown, OutOfOfficeBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: outOfOffice.putOutOfOffice,
    onSuccess: (answer) => queryClient.setQueryData(outOfOfficeKeys.mine, answer),
  });
}
