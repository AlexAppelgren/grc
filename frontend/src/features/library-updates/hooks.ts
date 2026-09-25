'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as libraryUpdates from './api';
import type { LibraryUpdatesPage, LibraryUpdatesQuery } from './types';

// Query keys and invalidation for the library-updates screen (playbook 6.1).

export const libraryUpdatesKeys = {
  list: (query: LibraryUpdatesQuery) => ['library-updates', query] as const,
};

export function useLibraryUpdates(query: LibraryUpdatesQuery): UseQueryResult<LibraryUpdatesPage> {
  return useQuery({ queryKey: libraryUpdatesKeys.list(query), queryFn: () => libraryUpdates.listLibraryUpdates(query) });
}

/** Moves the reader's own bookmark (POST /me/visit) and re-reads the feed and `GET /me`'s count with it. */
export function useMarkVisited(): UseMutationResult<void, unknown, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => libraryUpdates.markVisited(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['library-updates'] });
      await queryClient.invalidateQueries({ queryKey: ['me'] });
    },
  });
}
