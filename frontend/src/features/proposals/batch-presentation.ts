import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { proposalStatusTone, slotTone } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';

import type { BatchRowDecision, ProposalBatch, ProposalBatchRow } from './types';

// Pills and derived facts for a batch proposal (design/screens/console-queue-batch.html;
// PRO-04, ADM-02). A row names its record's instrument in the instrument slot (brand);
// its decision takes the queue status's own tones (waiting warning, approved positive,
// rejected information), and while it waits the pill says what approving would do. A
// row previewed against a scope the record no longer has is `stale`, a fact that needs
// attention (warning), never a person's choice.

/** A decision the reviewer has made on a row in this screen and not yet sent. */
export interface RowDraft {
  decision: Exclude<BatchRowDecision, 'pending'>;
  rejectionCode: string;
}

const SLOT_ORDER = { instrument: 10, decision: 20, stale: 30 } as const;

/** What approving the row would do to its record's scope, in the words the pill uses. */
export function previewKey(row: Pick<ProposalBatchRow, 'before' | 'after'>): MessageKey {
  const before = new Set(row.before.terms ?? []);
  const after = new Set(row.after.terms ?? []);
  const adds = [...after].some((term) => !before.has(term));
  const removes = [...before].some((term) => !after.has(term));
  if (adds && !removes) return 'console.batch.row.added';
  if (removes && !adds) return 'console.batch.row.removed';
  return 'console.batch.row.changed';
}

/** The row's decision as the screen shows it: the server's once decided, else the reviewer's draft. */
export function shownDecision(row: Pick<ProposalBatchRow, 'decision'>, draft: RowDraft | undefined): BatchRowDecision {
  if (row.decision === 'approved' || row.decision === 'rejected') return row.decision;
  return draft?.decision ?? 'pending';
}

export function batchRowPills(row: ProposalBatchRow, draft: RowDraft | undefined, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [];
  const instrument = row.target?.instrumentShortName ?? '';
  if (instrument !== '') pills.push({ key: 'instrument', label: instrument, tone: slotTone.instrument, order: SLOT_ORDER.instrument });
  const decision = shownDecision(row, draft);
  if (decision === 'pending') {
    pills.push({ key: 'decision', label: t(previewKey(row)), tone: proposalStatusTone.open, order: SLOT_ORDER.decision });
  } else {
    pills.push({ key: 'decision', label: t(decision === 'approved' ? 'console.batch.row.approved' : 'console.batch.row.rejected'), tone: proposalStatusTone[decision], order: SLOT_ORDER.decision });
  }
  if (row.stale === true && row.decision === 'pending') pills.push({ key: 'stale', label: t('console.batch.row.stale'), tone: slotTone.stale, order: SLOT_ORDER.stale });
  return pills.sort(byOrder);
}

/** The record a row changes, by its own title; its reference when it has no title. */
export function batchRowTitle(row: Pick<ProposalBatchRow, 'target' | 'subjectId'>): string {
  const target = row.target ?? null;
  if (target === null) return row.subjectId;
  return target.title !== '' ? target.title : target.referenceLabel;
}

export interface BatchTally {
  approved: number;
  rejected: number;
  pending: number;
}

/** How many rows stand approved, rejected and undecided, counting the reviewer's drafts. */
export function batchTally(rows: readonly ProposalBatchRow[], drafts: ReadonlyMap<string, RowDraft>): BatchTally {
  const tally: BatchTally = { approved: 0, rejected: 0, pending: 0 };
  for (const row of rows) tally[shownDecision(row, drafts.get(row.id))] += 1;
  return tally;
}

/** Every row is decided on the server: the batch shows its result. */
export function batchDecided(batch: Pick<ProposalBatch, 'rows'>): boolean {
  const rows = batch.rows ?? [];
  return rows.length > 0 && rows.every((row) => row.decision !== 'pending');
}

/** The last row decision, which names who applied the batch and when. */
export function lastDecision(rows: readonly ProposalBatchRow[]): ProposalBatchRow | null {
  let last: ProposalBatchRow | null = null;
  let lastAt = '';
  for (const row of rows) {
    if (typeof row.decidedAt === 'string' && row.decidedAt > lastAt) {
      last = row;
      lastAt = row.decidedAt;
    }
  }
  return last;
}
