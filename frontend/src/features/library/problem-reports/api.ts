import { api } from '@/shared/utils/api-client';

import type { Page, ProblemReport, ProblemReportClose, RecordReportsQuery } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). A report is the bank's
// own content: nothing here logs it.

const PROBLEM_REPORTS = '/api/v1/problem-reports';

export async function listProblemReports(query: RecordReportsQuery): Promise<Page<ProblemReport>> {
  return (await api.get<Page<ProblemReport>>(PROBLEM_REPORTS, { params: query })).data;
}

export async function closeProblemReport(reportId: string, body: ProblemReportClose): Promise<ProblemReport> {
  return (await api.patch<ProblemReport>(`${PROBLEM_REPORTS}/${reportId}`, body)).data;
}
