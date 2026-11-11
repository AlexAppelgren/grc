'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as problemReports from './api';
import type { Page, ProblemReport, ProblemReportClose, ProblemReportSubjectType } from './types';

// Query keys for a record's problem reports (playbook 6.1). Filing a report
// (features/library) and closing one both change the list, so both
// invalidate everything under `problem-reports`.

export const problemReportKeys = {
  all: ['problem-reports'] as const,
  record: (subjectType: ProblemReportSubjectType, subjectId: string) => ['problem-reports', subjectType, subjectId] as const,
};

export const RECORD_REPORTS_PAGE = 20;

export function useRecordProblemReports(subjectType: ProblemReportSubjectType, subjectId: string, enabled: boolean): UseQueryResult<Page<ProblemReport>> {
  return useQuery({
    queryKey: problemReportKeys.record(subjectType, subjectId),
    queryFn: () => problemReports.listProblemReports({ subjectType, subjectId, limit: RECORD_REPORTS_PAGE, offset: 0 }),
    enabled,
  });
}

/** Refreshes every report list, for the screen that has just filed one. */
export function useRefreshProblemReports(): () => void {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: problemReportKeys.all });
}

/**
 * Closing a report. A 409 means someone closed it first, so the list is
 * refreshed on failure too: the row then shows who closed it and why.
 */
export function useCloseProblemReport(reportId: string): UseMutationResult<ProblemReport, unknown, ProblemReportClose> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => problemReports.closeProblemReport(reportId, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: problemReportKeys.all }),
  });
}
