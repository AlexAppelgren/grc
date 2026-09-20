'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import * as library from './api';
import type { Obligation, ObligationQuery, Page } from './types';

// Query keys for the inventory (playbook 6.1). The filters are part of the
// key, so changing "as of" or asking to see outside the footprint re-reads
// rather than reuses: the version in force on a date is a different answer,
// not a filtered one.

export const libraryKeys = {
  obligations: (query: ObligationQuery, limit: number) => ['library', 'obligations', { ...query, limit }] as const,
};

/** Playbook 10: the list default. The head states the total, so a longer library is visibly longer than the page. */
export const OBLIGATION_PAGE = 20;

export function useObligations(query: ObligationQuery): UseQueryResult<Page<Obligation>> {
  return useQuery({
    queryKey: libraryKeys.obligations(query, OBLIGATION_PAGE),
    queryFn: () => library.listObligations({ ...query, limit: OBLIGATION_PAGE, offset: 0 }),
  });
}
