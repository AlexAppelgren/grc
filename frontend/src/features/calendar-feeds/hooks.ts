'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import { createCalendarFeed, listCalendarFeeds, revokeCalendarFeed } from '@/features/calendar-feeds/api';
import type { CalendarFeed, CalendarFeedCreated } from '@/features/calendar-feeds/types';

// Query keys and invalidation (playbook 6.1). Screens call these and render.

export const calendarFeedKeys = {
  list: ['me', 'calendar-feeds'] as const,
};

export function useCalendarFeeds(): UseQueryResult<CalendarFeed[]> {
  return useQuery({ queryKey: calendarFeedKeys.list, queryFn: listCalendarFeeds });
}

export function useCreateCalendarFeed(): UseMutationResult<CalendarFeedCreated, unknown, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCalendarFeed,
    // The answer carries the address, a secret shown once (D-52). With no
    // grace period the mutation cache drops it the moment the screen resets
    // or leaves, instead of holding it in memory for the default five minutes.
    gcTime: 0,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: calendarFeedKeys.list }),
  });
}

export function useRevokeCalendarFeed(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: revokeCalendarFeed, onSuccess: () => queryClient.invalidateQueries({ queryKey: calendarFeedKeys.list }) });
}
