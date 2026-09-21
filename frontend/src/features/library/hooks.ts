'use client';

import { useMutation, useQuery, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as library from './api';
import type { Obligation, ObligationDetail, ObligationQuery, Page, ProblemReportBody, ProblemReportCreated, VersionDiff } from './types';

// Query keys for the inventory and the obligation card (playbook 6.1). The
// filters and the date are part of the key, so changing "as of" or asking to
// see outside the footprint re-reads rather than reuses: the version in force
// on a date is a different answer, not a filtered one.

export const libraryKeys = {
  obligations: (query: ObligationQuery, limit: number) => ['library', 'obligations', { ...query, limit }] as const,
  obligation: (obligationId: string, asOf: string) => ['library', 'obligation', obligationId, asOf] as const,
  obligationDiff: (obligationId: string, lang: string) => ['library', 'obligation', obligationId, 'diff', lang] as const,
};

/** Playbook 10: the list default. The head states the total, so a longer library is visibly longer than the page. */
export const OBLIGATION_PAGE = 20;

export function useObligations(query: ObligationQuery): UseQueryResult<Page<Obligation>> {
  return useQuery({
    queryKey: libraryKeys.obligations(query, OBLIGATION_PAGE),
    queryFn: () => library.listObligations({ ...query, limit: OBLIGATION_PAGE, offset: 0 }),
  });
}

/**
 * One obligation as of a date. The date is part of the key, so "as of" is a
 * different answer rather than a filtered one, and an empty date means today
 * in the bank's own time zone, which the server decides.
 */
export function useObligation(obligationId: string, asOf = ''): UseQueryResult<ObligationDetail> {
  return useQuery({
    queryKey: libraryKeys.obligation(obligationId, asOf),
    queryFn: () => library.getObligation(obligationId, asOf),
  });
}

/** "Show what changed", read only once the reader asks for it. */
export function useObligationDiff(obligationId: string, lang: string, enabled: boolean): UseQueryResult<VersionDiff> {
  return useQuery({
    queryKey: libraryKeys.obligationDiff(obligationId, lang),
    queryFn: () => library.getObligationDiff(obligationId, lang),
    enabled,
  });
}

/**
 * Filing a problem report changes no library record and no list this screen
 * reads, so it invalidates nothing: the report lives in the reader's own bank
 * and the console answers it later.
 */
export function useReportObligationProblem(obligationId: string): UseMutationResult<ProblemReportCreated, unknown, ProblemReportBody> {
  return useMutation({ mutationFn: (body) => library.reportObligationProblem(obligationId, body) });
}
