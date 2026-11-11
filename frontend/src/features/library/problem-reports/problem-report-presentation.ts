import type { PillTone } from '@/components/ui/pill-tones';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { problemReportStatusTone } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';

import type { ProblemReport, ProblemReportClosingStatus, ProblemReportStatus } from './types';

// A problem report's pill and the facts around it (AUD-03). The status is a
// fixed kind, so its label comes from the catalog and its tone from
// tone-by-kind; nothing here reads the reporter's words.

/** The permission that reaches every report of the bank and closes any of them. */
export const CLOSE_ANY_PERMISSION = 'proposals.create';

const STATUS_LABEL: Record<ProblemReportStatus, MessageKey> = {
  open: 'inventory.reports.status.open',
  answered: 'inventory.reports.status.answered',
  fixed: 'inventory.reports.status.fixed',
  rejected: 'inventory.reports.status.rejected',
};

/** The three states a report can be closed in, in the order the form offers them. */
export const CLOSING_STATUSES: readonly ProblemReportClosingStatus[] = ['answered', 'fixed', 'rejected'];

function isStatus(value: string): value is ProblemReportStatus {
  return value in STATUS_LABEL;
}

export function statusLabel(status: string, t: Translate): string {
  return t(isStatus(status) ? STATUS_LABEL[status] : 'inventory.reports.status.other');
}

export function statusTone(status: string): PillTone {
  return isStatus(status) ? problemReportStatusTone[status] : 'information';
}

export function presentProblemReport(report: Pick<ProblemReport, 'status'>, t: Translate): PresentedPill[] {
  return [{ key: 'status', label: statusLabel(report.status, t), tone: statusTone(report.status), order: 0 }];
}

/**
 * Whether the reader may close this report: it is open, and they filed it or
 * hold the permission that closes any of the bank's. The server decides; this
 * only keeps a button from being offered that would be refused.
 */
export function canClose(report: Pick<ProblemReport, 'status' | 'reporter'>, meId: string | null, permissions: readonly string[]): boolean {
  if (report.status !== 'open') return false;
  return permissions.includes(CLOSE_ANY_PERMISSION) || (meId !== null && report.reporter.id === meId);
}

/** "Version 2, Swedish": what the reporter had on screen, or null when nothing was recorded. */
export function contextLine(report: Pick<ProblemReport, 'versionNumber' | 'language'>, languageName: (code: string) => string, t: Translate): string | null {
  const parts: string[] = [];
  if (report.versionNumber !== null) parts.push(t('inventory.reports.version', { number: report.versionNumber }));
  if (report.language !== null) parts.push(languageName(report.language));
  return parts.length === 0 ? null : parts.join(', ');
}
