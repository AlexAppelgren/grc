'use client';

import { useInfiniteQuery, type InfiniteData, type UseInfiniteQueryResult } from '@tanstack/react-query';

import * as myWork from './api';
import type { WorkPage, WorkScope } from './types';

// My work's one read. Every section comes from one list in section order, so a
// page never chains a call behind another; "Show more" reads the next page.

export const myWorkKeys = {
  all: ['my-work'] as const,
  scope: (scope: WorkScope) => ['my-work', scope] as const,
};

/** The largest page the API serves: most people's whole list in one read. */
export const MY_WORK_PAGE = 100;

export function useMyWork(scope: WorkScope): UseInfiniteQueryResult<InfiniteData<WorkPage>> {
  return useInfiniteQuery({
    queryKey: myWorkKeys.scope(scope),
    queryFn: ({ pageParam }) => myWork.getMyWork({ ...scope, limit: MY_WORK_PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const read = pages.reduce((sum, page) => sum + page.items.length, 0);
      return read < last.total ? read : undefined;
    },
  });
}
