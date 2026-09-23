import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import type { ChangeRow } from '@/features/watch/api';

import { presentLead } from './today-presentation';

const t = createT('en');

function fact(key: string, label: string, suggested: boolean) {
  return { ref: { key, kind: null, label }, confidence: suggested ? 0.8 : null, suggested };
}

const row: ChangeRow = {
  id: 'c1',
  stableKey: 'chg-fi-2026-research-payments',
  title: 'FI adopts amended rules on paying for investment research',
  status: 'active',
  authorityId: 'a1',
  authorityLabel: 'Finansinspektionen',
  changeType: fact('adopted', 'Adopted rule', false),
  flags: [],
  terms: [],
  suggestedUrgency: { key: 'act_now', kind: null, label: 'Act now' },
  publishedOn: '2026-09-15',
  publishedPrecision: 'day',
  keyDate: '2026-10-01',
  keyDateLabel: 'In force',
  keyDatePrecision: 'day',
  firstSeenAt: '2026-09-16T06:02:00Z',
  inFootprint: true,
  market: null,
  case: {
    id: 'case-1',
    category: 'new',
    allowedTransitions: [],
    footprintMatch: true,
    obligationDecisions: [],
    ownerId: null,
    soWhatConfirmed: false,
    soWhatConfirmedAt: null,
    soWhatText: 'Confirm the annual assessment criteria.',
    urgency: { key: 'act_now', kind: null, label: 'Act now' },
    urgencyConfirmed: true,
  },
} as ChangeRow;

describe('presentLead', () => {
  it('the brand pill "Lead" comes first, then the row\'s own pills in slot order', () => {
    const pills = presentLead(row, t);
    expect(pills[0]).toEqual({ key: 'lead', label: 'Lead', tone: 'brand', order: -1 });
    expect(pills.map((p) => p.label)).toEqual(['Lead', 'Adopted rule', 'Act now']);
    expect(pills[1]?.tone).toBe('notice');
    expect(pills[2]?.tone).toBe('negative');
  });

  it('a change still carrying suggested facts also carries the "Suggested by the agent" marker', () => {
    const suggested: ChangeRow = { ...row, changeType: fact('adopted', 'Adopted rule', true) };
    const pills = presentLead(suggested, t);
    expect(pills.map((p) => p.label)).toContain('Suggested by the agent');
  });
});
