import { describe, expect, it } from 'vitest';

import { presentChange, type ChangeFacts } from './change-presentation';

// Pins label, tone and order for the change row and header
// (design/system/pills-and-labels.md).

const change: ChangeFacts = {
  type: { key: 'adopted-rule', label: 'Adopted rule' },
  urgency: { key: 'act-now', kind: 'act_now', label: 'Act now' },
  flags: [
    { key: 'advice-perimeter', label: 'Advice perimeter' },
    { key: 'ai', label: 'AI' },
  ],
  libraryTags: [{ key: 'research', label: 'Research' }],
  tenantTags: [{ key: 'q4', label: 'Q4 review' }],
  workflowStatus: { key: 'new', label: 'Needs triage' },
};

describe('presentChange', () => {
  it('row: type, urgency, flags, library tags, tenant tags; no status', () => {
    const pills = presentChange(change, 'row');
    expect(pills.map((p) => [p.label, p.tone, p.outlined ?? false])).toEqual([
      ['Adopted rule', 'notice', false],
      ['Act now', 'negative', false],
      ['Advice perimeter', 'brand', false],
      ['AI', 'brand', false],
      ['Research', 'brand', false],
      ['Q4 review', 'information', true],
    ]);
    expect(pills.map((p) => p.order)).toEqual([10, 20, 30, 31, 40, 50]);
  });

  it('header: the same, then workflow status last', () => {
    const pills = presentChange(change, 'header');
    expect(pills.at(-1)).toEqual({ key: 'status:new', label: 'Needs triage', tone: 'information', order: 60 });
    expect(pills).toHaveLength(7);
  });

  it('urgency tone follows the kind, never the label', () => {
    const tones = (['act_now', 'within_3_months', 'six_plus_months', 'monitor', 'no_action'] as const).map(
      (kind) => presentChange({ ...change, urgency: { key: kind, kind, label: 'Any label' } }, 'row')[1]?.tone,
    );
    expect(tones).toEqual(['negative', 'warning', 'notice', 'information', 'positive']);
  });

  it('a change without flags or tags is type and urgency only', () => {
    const pills = presentChange({ type: change.type, urgency: change.urgency, flags: [] }, 'header');
    expect(pills.map((p) => p.key)).toEqual(['type:adopted-rule', 'urgency:act-now']);
  });
});
