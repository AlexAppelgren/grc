import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { defaultFormatContext } from '@/shared/utils/format';

import { presentRoadmapItem, roadmapWhen } from './roadmap-presentation';

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

describe('roadmapWhen', () => {
  const today = new Date('2026-09-21T09:00:00Z');

  it('a date stated to the day is that day, with the days left to it', () => {
    expect(roadmapWhen({ date: '2026-10-01', datePrecision: 'day' }, defaultFormatContext, today)).toEqual({ date: '1 Oct 2026', daysLeft: 10 });
  });

  it('a quarter reads as its quarter and counts no days to the day it is stored on', () => {
    expect(roadmapWhen({ date: '2026-11-15', datePrecision: 'quarter' }, defaultFormatContext, today)).toEqual({ date: 'Q4 2026', daysLeft: null });
  });

  it('a month and a year read as themselves, with no count', () => {
    expect(roadmapWhen({ date: '2026-11-15', datePrecision: 'month' }, defaultFormatContext, today)).toEqual({ date: 'November 2026', daysLeft: null });
    expect(roadmapWhen({ date: '2027-01-01', datePrecision: 'year' }, defaultFormatContext, today)).toEqual({ date: '2027', daysLeft: null });
  });

  it('today itself counts no days', () => {
    expect(roadmapWhen({ date: '2026-09-21', datePrecision: 'day' }, defaultFormatContext, today).daysLeft).toBeNull();
  });
});
