import { describe, expect, it } from 'vitest';

import { t } from '@/shared/i18n';

import { batchDecided, batchRowPills, batchRowTitle, batchTally, lastDecision, previewKey, shownDecision, type RowDraft } from './batch-presentation';
import type { ProposalBatchRow } from './types';

// A batch row's pills and the facts the review screen derives: tones come from the
// slot and the fixed decision kind, never from a person.

function row(overrides: Partial<ProposalBatchRow> = {}): ProposalBatchRow {
  return {
    id: 'r-1',
    subjectType: 'obligation',
    subjectId: 'obl-1',
    target: { id: 'obl-1', title: 'Keep client money apart', referenceLabel: '8 kap. 1 §', instrumentShortName: 'FFFS 2017:2' },
    before: { terms: ['a:x'] },
    after: { terms: ['a:x', 'a:y'] },
    source: '',
    stale: false,
    decision: 'pending',
    rejectionCode: '',
    decidedBy: null,
    decidedAt: null,
    ...overrides,
  };
}

const approve: RowDraft = { decision: 'approved', rejectionCode: '' };
const reject: RowDraft = { decision: 'rejected', rejectionCode: 'wrong_scope' };

describe('batch presentation', () => {
  it('says what approving would do: add, remove or change', () => {
    expect(previewKey(row())).toBe('console.batch.row.added');
    expect(previewKey(row({ before: { terms: ['a:x', 'a:y'] }, after: { terms: ['a:x'] } }))).toBe('console.batch.row.removed');
    expect(previewKey(row({ before: { terms: ['a:x'] }, after: { terms: ['a:y'] } }))).toBe('console.batch.row.changed');
    expect(previewKey(row({ before: {}, after: { terms: ['a:x'] } }))).toBe('console.batch.row.added');
    expect(previewKey(row({ before: { terms: ['a:x'] }, after: {} }))).toBe('console.batch.row.removed');
  });

  it('shows the server\'s decision once made, and the reviewer\'s draft only on a pending row', () => {
    expect(shownDecision(row(), undefined)).toBe('pending');
    expect(shownDecision(row(), reject)).toBe('rejected');
    expect(shownDecision(row({ decision: 'approved' }), reject)).toBe('approved');
  });

  it('puts the instrument in brand, the decision in the queue status tones, and a stale pending row in warning', () => {
    const tones = (pills: ReturnType<typeof batchRowPills>) => pills.map((pill) => [pill.label, pill.tone]);
    expect(tones(batchRowPills(row(), undefined, t))).toEqual([
      ['FFFS 2017:2', 'brand'],
      ['Added when approved', 'warning'],
    ]);
    expect(tones(batchRowPills(row(), approve, t))).toEqual([
      ['FFFS 2017:2', 'brand'],
      ['Approved', 'positive'],
    ]);
    expect(tones(batchRowPills(row({ stale: true, target: null }), reject, t))).toEqual([
      ['Rejected', 'information'],
      ['Changed since it was asked', 'warning'],
    ]);
    expect(tones(batchRowPills(row({ stale: true, decision: 'rejected' }), undefined, t)).map(([label]) => label)).not.toContain('Changed since it was asked');
  });

  it('names a row by its record\'s title, its reference, or its id when the record cannot be read', () => {
    expect(batchRowTitle(row())).toBe('Keep client money apart');
    expect(batchRowTitle(row({ target: { id: 'obl-1', title: '', referenceLabel: '8 kap. 1 §', instrumentShortName: '' } }))).toBe('8 kap. 1 §');
    expect(batchRowTitle(row({ target: null }))).toBe('obl-1');
  });

  it('counts rows with the drafts, knows when every row is decided, and finds the last decision', () => {
    const rows = [row({ id: 'r-1' }), row({ id: 'r-2' }), row({ id: 'r-3', decision: 'rejected', decidedAt: '2026-09-25T09:00:00Z' })];
    expect(batchTally(rows, new Map([['r-1', approve]]))).toEqual({ approved: 1, rejected: 1, pending: 1 });
    expect(batchDecided({ rows })).toBe(false);
    expect(batchDecided({ rows: [] })).toBe(false);
    expect(batchDecided({})).toBe(false);
    const decided = [row({ decision: 'approved', decidedAt: '2026-09-25T09:40:00Z' }), row({ id: 'r-2', decision: 'rejected', decidedAt: '2026-09-25T09:00:00Z' })];
    expect(batchDecided({ rows: decided })).toBe(true);
    expect(lastDecision(decided)?.id).toBe('r-1');
    expect(lastDecision([row()])).toBeNull();
  });
});
