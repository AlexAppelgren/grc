import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

import type { ChangeRow } from './api';
import {
  authorityAndDate,
  caseStatusLabel,
  daysUntil,
  factsOfChange,
  isMachineConfirmed,
  isSuggested,
  keyDateMeta,
  machineConfirmedBy,
  presentChange,
  presentChangeRow,
  rowUrgency,
  scopeTermLabels,
  urgencyOf,
  type ChangeFacts,
} from './change-presentation';

// Pins label, tone and order for the change row and header
// (design/system/pills-and-labels.md), and the meta text beside them.

const t = createT('en');
const ctx = defaultFormatContext;
// The prototype's anchor week, so nothing here moves with the clock.
const TODAY = new Date(Date.UTC(2026, 8, 19));

const change: ChangeFacts = {
  type: { key: 'adopted-rule', label: 'Adopted rule' },
  urgency: { key: 'act_now', kind: 'act_now', label: 'Act now' },
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
    const tones = (['act_now', 'within_3_months', 'six_months_plus', 'monitor', 'no_action'] as const).map(
      (kind) => presentChange({ ...change, urgency: { key: kind, kind, label: 'Any label' } }, 'row')[1]?.tone,
    );
    expect(tones).toEqual(['negative', 'warning', 'notice', 'information', 'positive']);
  });

  it('a change without flags or tags is type and urgency only', () => {
    const pills = presentChange({ type: change.type, urgency: change.urgency, flags: [] }, 'header');
    expect(pills.map((p) => p.key)).toEqual(['type:adopted-rule', 'urgency:act_now']);
  });

  it('a change with no urgency shows none rather than a guessed one', () => {
    const pills = presentChange({ type: change.type, flags: [] }, 'row');
    expect(pills.map((p) => p.key)).toEqual(['type:adopted-rule']);
  });

  it('the suggestion marker sits after the flags, in the catalog’s words', () => {
    const pills = presentChange({ ...change, suggested: true }, 'row', t);
    expect(pills.map((p) => p.key)).toEqual(['type:adopted-rule', 'urgency:act_now', 'flag:advice-perimeter', 'flag:ai', 'suggested', 'library-tag:research', 'tenant-tag:q4']);
    expect(pills[4]).toEqual({ key: 'suggested', label: 'Suggested by the agent', tone: 'information', order: 35 });
  });

  it('a change whose facts a person settled carries no marker', () => {
    expect(presentChange({ ...change, suggested: false }, 'row', t).some((p) => p.key === 'suggested')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// The row the API sends
// ---------------------------------------------------------------------------

const fact = (key: string, label: string, suggested: boolean) => ({ ref: { key, kind: null, label }, confidence: 0.9, suggested });

const row: ChangeRow = {
  id: 'c1',
  stableKey: 'chg-fi-2026-research-payments',
  title: 'FI adopts amended rules on paying for investment research',
  status: 'active',
  authorityId: 'a1',
  authorityLabel: 'Finansinspektionen',
  changeType: fact('adopted', 'Adopted rule', false),
  flags: [fact('ai', 'AI', false)],
  terms: [fact('securities', 'Securities', false)],
  suggestedUrgency: { key: 'act_now', kind: null, label: 'Act now' },
  publishedOn: '2026-09-15',
  publishedPrecision: 'day',
  keyDate: '2026-10-01',
  keyDateLabel: 'In force',
  keyDatePrecision: 'day',
  firstSeenAt: '2026-09-16T06:02:00Z',
  inFootprint: true,
  market: null,
  case: null,
} as ChangeRow;

const withCase = (patch: Partial<NonNullable<ChangeRow['case']>>): ChangeRow => ({
  ...row,
  case: {
    id: 'case-1',
    category: 'new',
    allowedTransitions: [],
    footprintMatch: true,
    obligationDecisions: [],
    ownerId: null,
    soWhatConfirmed: false,
    soWhatConfirmedAt: null,
    soWhatText: null,
    urgency: null,
    urgencyConfirmed: false,
    ...patch,
  } as NonNullable<ChangeRow['case']>,
});

describe('urgencyOf', () => {
  it('reads the key, because the wire carries no kind for an urgency', () => {
    expect(urgencyOf({ key: 'within_3_months', kind: null, label: 'Within 3 months' })).toEqual({
      key: 'within_3_months',
      kind: 'within_3_months',
      label: 'Within 3 months',
    });
  });

  it('a key outside the severity scale gets no pill rather than a guessed tone', () => {
    expect(urgencyOf({ key: 'next_quarter', kind: null, label: 'Next quarter' })).toBeNull();
    expect(urgencyOf(null)).toBeNull();
  });

  it('a relabelled row keeps its tone (NFR-S10)', () => {
    const relabelled = urgencyOf({ key: 'act_now', kind: null, label: 'Act immediately' });
    expect(presentChange({ type: row.changeType.ref, urgency: relabelled ?? undefined, flags: [] }, 'row')[1]).toEqual({
      key: 'urgency:act_now',
      label: 'Act immediately',
      tone: 'negative',
      order: 20,
    });
  });
});

describe('rowUrgency', () => {
  it('without a case, the library’s suggestion', () => {
    expect(rowUrgency(row)?.kind).toBe('act_now');
  });

  it('with a case that has one, the bank’s own', () => {
    expect(rowUrgency(withCase({ urgency: { key: 'monitor', kind: null, label: 'Monitor' } }))?.kind).toBe('monitor');
  });

  it('with a case that has none, the suggestion still', () => {
    expect(rowUrgency(withCase({}))?.kind).toBe('act_now');
  });
});

describe('isSuggested', () => {
  it('is true while any classification is still the agent’s', () => {
    expect(isSuggested({ ...row, flags: [fact('ai', 'AI', true)] })).toBe(true);
    expect(isSuggested({ ...row, terms: [fact('securities', 'Securities', true)] })).toBe(true);
    expect(isSuggested({ ...row, changeType: fact('adopted', 'Adopted rule', true) })).toBe(true);
  });

  it('is false once a person has settled every one of them', () => {
    expect(isSuggested(row)).toBe(false);
  });
});

describe('isMachineConfirmed', () => {
  const byAnAgent = (key: string, label: string) => ({ ...fact(key, label, false), confirmedOrigin: 'agent' as const });

  it('is true once an independent agent confirmed any classification, and never for a person’s confirmation', () => {
    expect(isMachineConfirmed({ ...row, flags: [byAnAgent('ai', 'AI')] })).toBe(true);
    expect(isMachineConfirmed({ ...row, changeType: byAnAgent('adopted', 'Adopted rule') })).toBe(true);
    expect(isMachineConfirmed({ ...row, flags: [{ ...fact('ai', 'AI', false), confirmedOrigin: 'user' }] })).toBe(false);
    expect(isMachineConfirmed(row)).toBe(false);
  });

  it('a row an agent confirmed keeps a machine label, and a suggestion still wins the slot', () => {
    const confirmed = { ...row, changeType: byAnAgent('adopted', 'Adopted rule') };
    expect(presentChangeRow(confirmed, 'row', t).map((p) => [p.label, p.tone])).toContainEqual(['Machine-confirmed', 'information']);
    const mixed = { ...confirmed, flags: [fact('ai', 'AI', true)] };
    expect(presentChangeRow(mixed, 'row', t).map((p) => p.label)).toContain('Suggested by the agent');
    expect(presentChangeRow(mixed, 'row', t).map((p) => p.label)).not.toContain('Machine-confirmed');
  });
});

describe('machineConfirmedBy', () => {
  const sweeper = { id: 'a1', key: 'watch-sweeper' };
  const confirmer = { id: 'a2', key: 'library-confirmer' };
  const sv = createT('sv');

  it('names the agent that suggested a fact and the one that confirmed it', () => {
    const facts = [{ confirmedOrigin: 'agent' as const, suggestedByAgent: sweeper, confirmedByAgent: confirmer }];
    expect(machineConfirmedBy(facts, t)).toBe('Machine-confirmed: suggested by watch-sweeper, confirmed by library-confirmer');
    expect(machineConfirmedBy(facts, sv)).toBe('Maskinbekräftad: föreslagen av watch-sweeper, bekräftad av library-confirmer');
  });

  it('names the confirming agent alone when no agent suggested it', () => {
    expect(machineConfirmedBy([{ confirmedOrigin: 'agent', suggestedByAgent: null, confirmedByAgent: confirmer }], t)).toBe('Machine-confirmed by library-confirmer');
  });

  it('says each pair once, and nothing for a suggestion or a person’s confirmation', () => {
    const byAgent = { confirmedOrigin: 'agent' as const, suggestedByAgent: sweeper, confirmedByAgent: confirmer };
    expect(machineConfirmedBy([byAgent, byAgent], t)).toBe('Machine-confirmed: suggested by watch-sweeper, confirmed by library-confirmer');
    expect(machineConfirmedBy([{ confirmedOrigin: 'user', suggestedByAgent: sweeper, confirmedByAgent: null }], t)).toBeNull();
    expect(machineConfirmedBy([{ confirmedOrigin: null, suggestedByAgent: sweeper, confirmedByAgent: null }], t)).toBeNull();
    expect(machineConfirmedBy([], t)).toBeNull();
  });
});

describe('factsOfChange', () => {
  it('reads the fact under ref, and the case category as the status', () => {
    const facts = factsOfChange(withCase({ category: 'signoff' }), t);
    expect(facts.type).toEqual({ key: 'adopted', label: 'Adopted rule' });
    expect(facts.flags).toEqual([{ key: 'ai', label: 'AI' }]);
    expect(facts.workflowStatus).toEqual({ key: 'signoff', label: 'Waiting for sign-off' });
  });

  it('a change this bank has no case for shows no status', () => {
    expect(factsOfChange(row, t).workflowStatus).toBeUndefined();
  });

  it('a change nobody has given an urgency carries none', () => {
    expect(factsOfChange({ ...row, suggestedUrgency: null }, t).urgency).toBeUndefined();
  });

  it('presents the row in slot order', () => {
    expect(presentChangeRow(withCase({}), 'header', t).map((p) => [p.label, p.tone])).toEqual([
      ['Adopted rule', 'notice'],
      ['Act now', 'negative'],
      ['AI', 'brand'],
      ['Needs triage', 'information'],
    ]);
  });
});

describe('caseStatusLabel', () => {
  it('every category reads as a phrase, never as its code', () => {
    expect((['new', 'assigned', 'assessing', 'implementing', 'signoff', 'closed', 'dismissed'] as const).map((c) => caseStatusLabel(c, t))).toEqual([
      'Needs triage',
      'Assigned',
      'Being assessed',
      'Being implemented',
      'Waiting for sign-off',
      'Closed',
      'Dismissed',
    ]);
  });
});

describe('the meta text beside the pills', () => {
  it('authority and date, or the authority alone when the source states none', () => {
    expect(authorityAndDate(row, t, ctx)).toBe('Finansinspektionen, 15 Sept 2026');
    expect(authorityAndDate({ ...row, publishedOn: null }, t, ctx)).toBe('Finansinspektionen');
  });

  it('a month-precision date reads as a month', () => {
    expect(authorityAndDate({ ...row, publishedOn: '2025-12-01', publishedPrecision: 'month' }, t, ctx)).toBe('Finansinspektionen, December 2025');
  });

  it('a date whose precision the source did not state reads as the day it carries', () => {
    expect(authorityAndDate({ ...row, publishedPrecision: null }, t, ctx)).toBe('Finansinspektionen, 15 Sept 2026');
  });

  it('the key date carries its label and the days left', () => {
    expect(keyDateMeta(row, t, ctx, TODAY)).toEqual(['In force 1 Oct 2026', 'in 12 days']);
  });

  it('a key date already past carries no days left', () => {
    expect(keyDateMeta({ ...row, keyDate: '2026-01-01' }, t, ctx, TODAY)).toEqual(['In force 1 Jan 2026']);
  });

  it('a date the source has not set says so in its own words', () => {
    expect(keyDateMeta({ ...row, keyDate: null, keyDateLabel: 'Report date' }, t, ctx, TODAY)).toEqual(['Report date Date not set']);
    expect(keyDateMeta({ ...row, keyDate: null, keyDateLabel: null }, t, ctx, TODAY)).toEqual(['Date not set']);
  });

  it('a key date with no label is the date alone', () => {
    expect(keyDateMeta({ ...row, keyDateLabel: null, keyDatePrecision: null }, t, ctx, TODAY)).toEqual(['1 Oct 2026', 'in 12 days']);
  });

  it('days are whole days, and an unparseable date has none', () => {
    expect(daysUntil('2026-09-20', TODAY)).toBe(1);
    expect(daysUntil('not a date', TODAY)).toBeNull();
  });

  it('the scope terms are the ones the change carries', () => {
    expect(scopeTermLabels(row)).toEqual(['Securities']);
    expect(scopeTermLabels({ ...row, terms: [] })).toEqual([]);
  });
});
