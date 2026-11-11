import { presentGap } from '@/features/register/register-presentation';
import type { RegisterGap } from '@/features/register/types';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { gapTone, severityTone, slotTone, type GapKind, type SeverityKind } from '@/features/shared/tone-by-kind';
import { daysUntil } from '@/features/watch/change-presentation';
import type { MessageKey, Translate } from '@/shared/i18n';
import { formatPartialDate, type FormatContext } from '@/shared/utils/format';

// What the gap screens read off a gap (design/screens/tenant-gaps.html;
// REG-03). The pills are register-presentation's `presentGap`; this module
// only narrows the API's list rows to the kinds that pick a tone, and says
// which way out a person sees. The server decides every rule again: the
// four-eyes check and the step-up are its, and a refusal renders from its code.

export const GAPS_EDIT = 'gaps.edit';
export const RISK_ACCEPT_APPROVE = 'risk.accept.approve';
export const REGISTER_READ = 'register.read';

function isGapKind(kind: string | null): kind is GapKind {
  return kind !== null && kind in gapTone;
}

function isSeverityKind(kind: string | null): kind is SeverityKind {
  return kind !== null && kind in severityTone;
}

/** The gap's category; a row the API sends without one reads as open work. */
export function gapKind(gap: Pick<RegisterGap, 'status'>): GapKind {
  return isGapKind(gap.status.kind) ? gap.status.kind : 'open';
}

/** Status, severity and source, each toned by its kind or slot through `presentGap`. */
export function gapPills(gap: Pick<RegisterGap, 'status' | 'severity' | 'source'>): PresentedPill[] {
  return presentGap({
    status: { key: gap.status.key, label: gap.status.label, kind: gapKind(gap) },
    severity: { key: gap.severity.key, label: gap.severity.label, kind: isSeverityKind(gap.severity.kind) ? gap.severity.kind : 'low' },
    source: { key: gap.source.key, label: gap.source.label },
  });
}

/** The computed "Waiting for approval" pill of the Way out panel, never a header slot. */
export function waitingPill(t: Translate): PresentedPill {
  return { key: 'waiting-for-approval', label: t('pill.waitingForApproval'), tone: slotTone.waitingForApproval, order: 0 };
}

/** A risk acceptance someone asked for and nobody has approved yet. */
export function isWaiting(gap: Pick<RegisterGap, 'riskAcceptance'>): boolean {
  return gap.riskAcceptance !== null && gap.riskAcceptance.approvedBy === null;
}

export interface GapActions {
  edit: boolean;
  startRemediation: boolean;
  close: boolean;
  acceptRisk: boolean;
  approve: boolean;
  reopen: boolean;
  /** The person looking asked for the acceptance that is waiting, so someone else approves it. */
  ownRequest: boolean;
}

/**
 * The buttons a person sees on a gap, from its category and their permissions.
 * The requester sees no Approve: the server refuses them with
 * `four_eyes_violation` anyway, and the database refuses the same person in both roles.
 */
export function gapActions(gap: Pick<RegisterGap, 'status' | 'riskAcceptance'>, meId: string | null, permissions: readonly string[]): GapActions {
  const kind = gapKind(gap);
  const edits = permissions.includes(GAPS_EDIT);
  const working = kind === 'open' || kind === 'remediating';
  const waiting = working && isWaiting(gap);
  const ownRequest = waiting && gap.riskAcceptance?.requestedBy.id === meId;
  return {
    edit: edits && working,
    startRemediation: edits && kind === 'open' && !waiting,
    close: edits && kind === 'remediating' && !waiting,
    acceptRisk: edits && working && !waiting,
    approve: waiting && !ownRequest && permissions.includes(RISK_ACCEPT_APPROVE),
    reopen: edits && !working,
    ownRequest,
  };
}

/** The key of the bank's first status row in a category: a move sends the key, never a label. */
export function statusKeyOf(rows: readonly { key: string; kind: string | null; active?: boolean }[], kind: GapKind): string | null {
  return rows.find((row) => row.kind === kind && row.active !== false)?.key ?? null;
}

export interface TargetLine {
  text: string;
  overdue: boolean;
}

/** "Target 30 Nov 2026, in 66 days", overdue once the day has passed for open work. */
export function targetLine(gap: Pick<RegisterGap, 'targetDate' | 'status'>, today: Date, t: Translate, ctx: FormatContext): TargetLine {
  if (gap.targetDate === null) return { text: t('gaps.target.none'), overdue: false };
  const date = formatPartialDate(gap.targetDate, 'day', ctx);
  const days = daysUntil(gap.targetDate, today) ?? 0;
  const kind = gapKind(gap);
  if ((kind === 'open' || kind === 'remediating') && days < 0) {
    return { text: t('gaps.target.overdue', { date, days: -days }), overdue: true };
  }
  if (days > 0) return { text: t('gaps.target.future', { date, days }), overdue: false };
  return { text: days === 0 ? t('gaps.target.today', { date }) : date, overdue: false };
}

/** The person or the team that owns the gap. */
export function ownerName(gap: Pick<RegisterGap, 'owner' | 'ownerTeam'>, t: Translate): string {
  return gap.owner?.name ?? gap.ownerTeam?.label ?? t('gaps.owner.none');
}

/** The server's refusals the gap screens say in their own words; any other code shows its `detail`. */
export const GAP_PROBLEMS: Readonly<Record<string, MessageKey>> = {
  four_eyes_violation: 'gaps.problem.fourEyes',
  stale_write: 'gaps.problem.stale',
  invalid_transition: 'gaps.problem.movedOn',
  request_pending: 'gaps.problem.pending',
  step_up_required: 'gaps.problem.stepUp',
  does_not_apply: 'gaps.problem.doesNotApply',
};

/** Approving adds the one refusal only an approval can meet: a caller without `risk.accept.approve`. */
export function gapProblemCopy(t: Translate, approving = false): Record<string, string> {
  const copy = Object.fromEntries(Object.entries(GAP_PROBLEMS).map(([code, key]) => [code, t(key)]));
  return approving ? { ...copy, permission_denied: t('gaps.problem.notApprover') } : copy;
}

