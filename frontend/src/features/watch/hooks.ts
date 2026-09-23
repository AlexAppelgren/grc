'use client';

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type UseInfiniteQueryResult,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { usePermissions } from '@/shared/navigation/require-permission';

import * as watch from './api';
import type { CaseObligationLink, CaseSoWhat, ChangeDetail, ChangePage, ChangeQuery, ObligationChangePage, ScopeTerm, SourceCoverage } from './api';

// Query keys, paging and cache keys for the watch screens (playbook 6.1).
// The filters are part of the key, so narrowing the feed re-reads rather than
// reuses: a filtered feed is a different answer, not a trimmed one.

export const watchKeys = {
  all: ['watch'] as const,
  changes: (query: ChangeQuery) => ['watch', 'changes', query] as const,
  count: (tab: TabKey, query: ChangeQuery) => ['watch', 'changes', 'count', tab, query] as const,
  change: (changeId: string) => ['watch', 'change', changeId] as const,
  obligationChanges: (obligationId: string, limit: number) => ['watch', 'obligation-changes', obligationId, { limit }] as const,
  coverage: ['watch', 'coverage'] as const,
};

/** Playbook 10: the list default. The head states the total, so a longer feed is visibly longer than the page. */
export const CHANGE_PAGE = 20;

/**
 * The tabs the feed offers, each a case category the route filters on.
 * "In progress" is `assigned` because the route takes one category and R1
 * creates every case as `new`; the three categories after `assigned`
 * (`assessing`, `implementing`, `signoff`) are only reachable once chunk 9
 * builds triage, which is also when this tab grows to span them.
 */
export const TAB_CATEGORY = {
  triage: 'new',
  inProgress: 'assigned',
  closed: 'closed',
  dismissed: 'dismissed',
} as const;

export type TabKey = keyof typeof TAB_CATEGORY;
export const TAB_KEYS: readonly TabKey[] = ['triage', 'inProgress', 'closed', 'dismissed'];

/** The feed, one page at a time: the next page begins where the pages read so far end. */
export function useChangeFeed(query: ChangeQuery, enabled = true): UseInfiniteQueryResult<{ pages: ChangePage[] }> {
  return useInfiniteQuery({
    queryKey: watchKeys.changes(query),
    queryFn: ({ pageParam }) => watch.listChanges({ ...query, limit: CHANGE_PAGE, offset: pageParam }),
    enabled,
    initialPageParam: 0,
    getNextPageParam: (last: ChangePage, pages: ChangePage[]) => {
      const read = pages.reduce((sum, page) => sum + page.items.length, 0);
      return read < last.total ? read : undefined;
    },
  });
}

/**
 * How many changes need triage, read from the route the rows come from and
 * never counted in the browser: a page of twenty cannot know how many there
 * are. It asks for the smallest page the route accepts, because only the
 * total is used, and it does not ask at all while the reader is already on
 * the triage tab, whose own read carries the same total. One count per tab
 * would be four more reads of the widest query in R1, which measured over the
 * route's 250 ms budget on a seeded stack (2026-09-21); the watch card asks
 * for a count on this tab alone.
 */
export function useTriageCount(query: ChangeQuery, enabled: boolean): UseQueryResult<ChangePage> {
  return useQuery({
    queryKey: watchKeys.count('triage', query),
    queryFn: () => watch.listChanges({ ...query, tab: TAB_CATEGORY.triage, limit: 1, offset: 0 }),
    enabled,
  });
}

export function useChange(changeId: string): UseQueryResult<ChangeDetail> {
  return useQuery({ queryKey: watchKeys.change(changeId), queryFn: () => watch.getChange(changeId) });
}

export function useObligationChanges(obligationId: string): UseQueryResult<ObligationChangePage> {
  return useQuery({
    queryKey: watchKeys.obligationChanges(obligationId, CHANGE_PAGE),
    queryFn: () => watch.listObligationChanges(obligationId, { limit: CHANGE_PAGE, offset: 0 }),
  });
}

/**
 * WAT-01: the last check per source. It is read only while the Coverage tab
 * is open, because the tab beside it has no use for it.
 */
export function useSourceCoverage(enabled: boolean): UseQueryResult<SourceCoverage[]> {
  return useQuery({ queryKey: watchKeys.coverage, queryFn: watch.getSourceCoverage, enabled });
}

/** The scope terms of one dimension, for the feed's filter. They change rarely, so they are held longer. */
export function useScopeTerms(dimension: string): UseQueryResult<ScopeTerm[]> {
  return useQuery({ queryKey: ['watch', 'terms', dimension], queryFn: () => watch.listScopeTerms(dimension), staleTime: 5 * 60_000 });
}

/** The grant behind every write on a bank's own case in R1 (design/screens/tenant-change.html). */
export const CASES_WORK = 'cases.work';

/**
 * Whether this reader may decide for this bank on this change: they hold
 * `cases.work`, and the bank has a case to write to, because every case
 * route answers 404 for a change with none. A hint for the controls only;
 * the server's 403 is the enforcer.
 */
export function useCanWorkCase(change: ChangeDetail): boolean {
  const permissions = usePermissions() ?? [];
  return change.case !== null && permissions.includes(CASES_WORK);
}

/**
 * Every write here is this bank's own decision about one change. It moves
 * the change page, the feed's So what and filter, and an obligation's open
 * count, so everything the watch screens read is read again rather than
 * patched by hand.
 */
function useInvalidateWatch(): () => Promise<void> {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: watchKeys.all });
}

/** WAT-05: "Save and confirm" on the rewrite form. */
export function useSaveSoWhat(changeId: string): UseMutationResult<CaseSoWhat, unknown, string> {
  const invalidate = useInvalidateWatch();
  return useMutation({ mutationFn: (text) => watch.saveSoWhat(changeId, text), onSuccess: () => invalidate() });
}

/** WAT-05: "Confirm wording" on the drafted So what. */
export function useConfirmSoWhat(changeId: string): UseMutationResult<CaseSoWhat, unknown, void> {
  const invalidate = useInvalidateWatch();
  return useMutation({ mutationFn: () => watch.confirmSoWhat(changeId), onSuccess: () => invalidate() });
}

/** WAT-04: "Confirm link" on one suggested obligation, for this bank's case. */
export function useAcceptCaseObligationLink(changeId: string): UseMutationResult<CaseObligationLink, unknown, string> {
  const invalidate = useInvalidateWatch();
  return useMutation({ mutationFn: (obligationId) => watch.acceptCaseObligationLink(changeId, obligationId), onSuccess: () => invalidate() });
}

/** WAT-04: "Not related" on one suggested obligation, for this bank's case. */
export function useRemoveCaseObligationLink(changeId: string): UseMutationResult<CaseObligationLink, unknown, string> {
  const invalidate = useInvalidateWatch();
  return useMutation({ mutationFn: (obligationId) => watch.removeCaseObligationLink(changeId, obligationId), onSuccess: () => invalidate() });
}
