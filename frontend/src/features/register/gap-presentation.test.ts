import { describe, expect, it } from 'vitest';

import { presentGap } from './gap-presentation';

describe('presentGap', () => {
  it('gap status, severity, source', () => {
    const pills = presentGap({
      status: { key: 'open', kind: 'open', label: 'Open' },
      severity: { key: 'high', kind: 'high', label: 'High' },
      source: { key: 'assessment', label: 'Impact assessment' },
    });
    expect(pills.map((p) => [p.label, p.tone, p.order])).toEqual([
      ['Open', 'negative', 10],
      ['High', 'negative', 20],
      ['Impact assessment', 'information', 30],
    ]);
  });

  it('tone follows the kind for every gap status and severity', () => {
    const statuses = (['open', 'remediating', 'risk_accepted', 'closed'] as const).map(
      (kind) => presentGap({ status: { key: kind, kind, label: 'x' }, severity: { key: 'low', kind: 'low', label: 'Low' } })[0]?.tone,
    );
    expect(statuses).toEqual(['negative', 'warning', 'information', 'positive']);
    const severities = (['high', 'medium', 'low'] as const).map(
      (kind) => presentGap({ status: { key: 'open', kind: 'open', label: 'Open' }, severity: { key: kind, kind, label: 'x' } })[1]?.tone,
    );
    expect(severities).toEqual(['negative', 'warning', 'information']);
  });

  it('omits a missing source', () => {
    expect(presentGap({ status: { key: 'closed', kind: 'closed', label: 'Closed' }, severity: { key: 'low', kind: 'low', label: 'Low' } })).toHaveLength(2);
  });
});
