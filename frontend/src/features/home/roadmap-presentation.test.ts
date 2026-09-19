import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { presentRoadmapItem } from './roadmap-presentation';

const t = createT('en');

describe('presentRoadmapItem', () => {
  it('a regulatory date carries the urgency', () => {
    expect(presentRoadmapItem({ urgency: { key: 'within-3', kind: 'within_3_months', label: 'Within 3 months' }, ourDeadline: false }, t)).toEqual([
      { key: 'urgency:within-3', label: 'Within 3 months', tone: 'warning', order: 0 },
    ]);
  });

  it('an internal date is Our deadline, brand', () => {
    expect(presentRoadmapItem({ ourDeadline: true }, t)).toEqual([{ key: 'our-deadline', label: 'Our deadline', tone: 'brand', order: 0 }]);
    expect(presentRoadmapItem({ ourDeadline: true }, createT('sv'))[0]?.label).toBe('Vår deadline');
  });

  it('nothing without either', () => {
    expect(presentRoadmapItem({ ourDeadline: false }, t)).toEqual([]);
  });
});
