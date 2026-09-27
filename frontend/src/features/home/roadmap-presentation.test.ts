import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { defaultFormatContext } from '@/shared/utils/format';

import type { RoadmapItem } from './types';

import { presentRoadmapItem, roadmapCardLine, roadmapOwner, roadmapSubjectHref, roadmapWhat, roadmapWhen } from './roadmap-presentation';

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

describe('our own deadlines', () => {
  const person = { id: 'u1', name: 'Johan Berg' };
  const team = { key: 'retail_compliance', kind: null, label: 'Retail compliance' };
  const subject = { obligationId: 'o1', gapId: null, licenceId: null, entity: { id: 'e1', name: 'Example Bank AB' } };

  it('names what produced the date, for every kind of item, in both languages', () => {
    const types: RoadmapItem['itemType'][] = ['change_date', 'review_due', 'gap_target', 'certificate_expiry', 'certificate_audit', 'internal_deadline', 'action_due'];
    expect(types.map((type) => roadmapWhat(type, t))).toEqual([
      'Regulatory date',
      'Next review',
      'Gap target date',
      'Certificate expires',
      'Certificate audit',
      'Case deadline',
      'Action due',
    ]);
    const sv = createT('sv');
    expect(new Set(types.map((type) => roadmapWhat(type, sv))).size).toBe(types.length);
  });

  it('names the owner: a person, a team, or both', () => {
    expect(roadmapOwner({ person, team: null }, t)).toBe('Johan Berg');
    expect(roadmapOwner({ person: null, team }, t)).toBe('Retail compliance');
    expect(roadmapOwner({ person, team }, t)).toBe('Johan Berg, Retail compliance');
  });

  it("a card's line says whose deadline it is, or that the date is a regulatory one", () => {
    expect(roadmapCardLine({ kind: 'internal', itemType: 'gap_target', owner: { person, team: null } }, t)).toBe('Our deadline · Gap target date · Johan Berg');
    expect(roadmapCardLine({ kind: 'regulatory', itemType: 'change_date', owner: null }, t)).toBe('Regulatory date');
  });

  it('says so when nobody owns the date yet', () => {
    expect(roadmapOwner(null, t)).toBe('Nobody yet');
    expect(roadmapOwner({ person: null, team: null }, t)).toBe('Nobody yet');
  });

  it("links a review or a gap target to the obligation it is on, and a certificate's date nowhere", () => {
    expect(roadmapSubjectHref(subject)).toBe('/inventory/obligations/o1');
    expect(roadmapSubjectHref({ ...subject, obligationId: null, licenceId: 'l1' })).toBeNull();
    expect(roadmapSubjectHref(null)).toBeNull();
  });
});
