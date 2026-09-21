'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as calendarFeeds from '@/features/calendar-feeds/api';
import type { CalendarFeed, CalendarFeedCreated } from '@/features/calendar-feeds/types';

// Query keys, invalidation (playbook 6.1). Screens call these and render;
// nothing here knows a role name.

export const calendarFeedKeys = {
  list: ['me', 'calendar-feeds'] as const,
};

export function useCalendarFeeds(): UseQueryResult<CalendarFeed[]> {
  return useQuery({ queryKey: calendarFeedKeys.list, queryFn: calendarFeeds.listCalendarFeeds });
}

export function useCreateCalendarFeed(): UseMutationResult<CalendarFeedCreated, unknown, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => calendarFeeds.createCalendarFeed(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: calendarFeedKeys.list }),
  });
}

export function useRevokeCalendarFeed(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (feedId: string) => calendarFeeds.revokeCalendarFeed(feedId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: calendarFeedKeys.list }),
  });
}
