// A bank's own problem reports on library records (AUD-03, INV-06). The wire
// shapes are the generated components['schemas'][…]; nothing is reshaped here.

import type { Page } from '@/features/tenant-admin/types';
import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type { Page };

export type ProblemReport = Schemas['ProblemReportRow'];

export type ProblemReportStatus = ProblemReport['status'];

/** The record a report is about: an obligation or an instrument (a provision is reported through its instrument). */
export type ProblemReportSubjectType = ProblemReport['subjectType'];

/** PATCH /problem-reports/{id}: the state it ends in and why. */
export type ProblemReportClose = Schemas['ProblemReportClose'];

export type ProblemReportClosingStatus = ProblemReportClose['status'];

/** GET /problem-reports on one record: the list the record's own screen shows. */
export interface RecordReportsQuery {
  subjectType: ProblemReportSubjectType;
  subjectId: string;
  limit: number;
  offset: number;
}
