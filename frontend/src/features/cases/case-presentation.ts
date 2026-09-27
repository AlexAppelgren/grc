import type { PresentedPill } from '@/features/shared/presentation-types';
import { scanStateTone, slotTone, urgencyTone } from '@/features/shared/tone-by-kind';
import { CHANGE_SLOT_ORDER, daysUntil, urgencyOf, workflowStatusOf, type CaseStatusFacts } from '@/features/watch/change-presentation';
import type { LibraryRef } from '@/features/watch/api';
import type { MessageKey, Translate } from '@/shared/i18n';

import type { CaseAction, CaseWorkflow, CloseReasonKind, ScanState } from './types';

// The case panels' pills and computed text (design/system/pills-and-labels.md,
// "Case work"). Every tone comes from tone-by-kind.ts, by slot or by kind;
// every phrase from the catalog or from the bank's own vocabulary row. The
// API sends keys, kinds and facts, never a phrase.

/**
 * The status pill: the workflow status slot's tone for every category, with
 * the bank's sub-status label where the case carries one (CAS-S13). A
 * sub-status changes the words, never the tone.
 */
export function presentCaseStatus(caseFacts: CaseStatusFacts, t: Translate): PresentedPill {
  const status = workflowStatusOf(caseFacts, t);
  return { key: `status:${status.key}`, label: status.label, tone: slotTone.workflowStatus, order: CHANGE_SLOT_ORDER.workflowStatus };
}

/**
 * The urgency pill, its tone from the level's own fixed row (D-48). A key
 * outside the five fixed levels gets no pill rather than a guessed tone.
 */
export function presentCaseUrgency(urgency: LibraryRef | null | undefined): PresentedPill | null {
  const level = urgencyOf(urgency);
  if (level === null) return null;
  return { key: `urgency:${level.key}`, label: level.label, tone: urgencyTone[level.kind], order: CHANGE_SLOT_ORDER.urgency };
}

const SCAN_STATE_KEY = {
  pending: 'cases.scan.pending',
  clean: 'cases.scan.clean',
  error: 'cases.scan.error',
  infected: 'cases.scan.infected',
} as const satisfies Record<ScanState, MessageKey>;

/** Where a piece of evidence stands with the malware scan, its tone by the state's kind. */
export function presentScanState(state: ScanState, t: Translate): PresentedPill {
  return { key: `scan:${state}`, label: t(SCAN_STATE_KEY[state]), tone: scanStateTone[state], order: 0 };
}

/** Only a file that passed the scan is offered for download. */
export function isDownloadable(evidence: { kind: string; scanState: ScanState }): boolean {
  return evidence.kind === 'file' && evidence.scanState === 'clean';
}

type Due = Pick<CaseAction, 'dueDate' | 'done'>;

/**
 * "Overdue" for an open action whose due date is before today; nothing for a
 * due date still ahead or for a done action. `today` is the tenant-local day,
 * passed in rather than read from the clock.
 */
export function presentOverdue(action: Due, today: Date, t: Translate): PresentedPill | null {
  const days = daysUntil(action.dueDate, today);
  if (action.done || days === null || days >= 0) return null;
  return { key: 'overdue', label: t('cases.due.overdue'), tone: slotTone.overdue, order: 0 };
}

/** "11 days left", "Due today" or "4 days late" for an open action; nothing once it is done. */
export function daysLeftText(action: Due, today: Date, t: Translate): string | null {
  const days = daysUntil(action.dueDate, today);
  if (action.done || days === null) return null;
  if (days === 0) return t('cases.due.today');
  return days > 0 ? t('cases.due.daysLeft', { count: days }) : t('cases.due.daysLate', { count: -days });
}

type Closing = Pick<CaseWorkflow, 'category' | 'closeReason' | 'dismissedReason'>;

const CLOSE_REASON_KINDS: readonly CloseReasonKind[] = ['signed_off', 'no_action', 'not_applicable'];

/**
 * How a closed case was closed, read off its close reason row's fixed kind:
 * signed off by a second person, or closed by one person because it needs no
 * work or does not apply. Null for an open case and for a kind this screen
 * does not know, which then shows no close controls rather than guessed ones.
 */
export function closeKindOf(caseFacts: Closing): CloseReasonKind | null {
  if (caseFacts.category !== 'closed') return null;
  const kind = caseFacts.closeReason?.kind;
  return (CLOSE_REASON_KINDS as readonly (string | null | undefined)[]).includes(kind) ? (kind as CloseReasonKind) : null;
}

/** Why a case was closed or dismissed, in the bank's own words from its list; null while it is open. */
export function closeReasonLabel(caseFacts: Closing): string | null {
  if (caseFacts.category === 'closed') return caseFacts.closeReason?.label ?? null;
  if (caseFacts.category === 'dismissed') return caseFacts.dismissedReason?.label ?? null;
  return null;
}
