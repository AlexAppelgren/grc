import { describe, expect, it } from 'vitest';

import type { RegisterGap } from '@/features/register/types';
import { createT } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

import { gapActions, gapKind, gapPills, gapProblemCopy, ownerName, statusKeyOf, targetLine, waitingPill } from './gap-view';

// The gap's pills, its way out and its target line (design/screens/tenant-gaps.html).
// Tones come from the row's kind, in either language, whatever the bank calls the row.

const en = createT('en');
const sv = createT('sv');

const SARA = { id: 'u-sara', name: 'Sara Lindqvist' };
const MARIA = { id: 'u-maria', name: 'Maria Svensson' };

function gap(overrides: Partial<RegisterGap> = {}): RegisterGap {
  return {
    id: 'g-1',
    obligationId: 'ob-1',
    orgUnitId: null,
    unitId: null,
    title: 'Currency exchange cost is missing',
    description: null,
    severity: { key: 'high', kind: 'high', label: 'High' },
    source: { key: 'assessment', kind: null, label: 'Self-assessment' },
    status: { key: 'open', kind: 'open', label: 'Open' },
    owner: SARA,
    ownerTeam: null,
    targetDate: '2026-11-30',
    remediation: null,
    identifiedAt: '2026-09-12T08:00:00Z',
    identifiedBy: SARA,
    riskAcceptance: null,
    version: 1,
    ...overrides,
  };
}

const waiting = { reason: { key: 'compensating_control', kind: null, label: 'A compensating control covers it' }, note: null, requestedBy: SARA, requestedAt: '2026-09-22T09:00:00Z', approvedBy: null, approvedAt: null };

describe('gap pills', () => {
  it.each([
    ['open', 'negative'],
    ['remediating', 'warning'],
    ['risk_accepted', 'information'],
    ['closed', 'positive'],
  ] as const)('a %s status reads %s from its kind, in en and sv labels alike', (kind, tone) => {
    for (const label of ['Whatever the bank calls it', 'Vad banken än kallar den']) {
      const [status] = gapPills(gap({ status: { key: `custom_${kind}`, kind, label } }));
      expect(status).toMatchObject({ label, tone });
    }
  });

  it.each([
    ['high', 'negative'],
    ['medium', 'warning'],
    ['low', 'information'],
  ] as const)('a %s severity reads %s', (kind, tone) => {
    expect(gapPills(gap({ severity: { key: kind, kind, label: kind } }))[1]?.tone).toBe(tone);
  });

  it('orders status, severity, then the source in its slot tone', () => {
    expect(gapPills(gap()).map((pill) => [pill.label, pill.tone])).toEqual([
      ['Open', 'negative'],
      ['High', 'negative'],
      ['Self-assessment', 'information'],
    ]);
  });

  it('reads a status without a kind as open work rather than guessing from its label', () => {
    expect(gapKind(gap({ status: { key: 'closed', kind: null, label: 'Closed' } }))).toBe('open');
  });

  it('says "Waiting for approval" in the warning tone, in both languages', () => {
    expect(waitingPill(en)).toMatchObject({ label: 'Waiting for approval', tone: 'warning' });
    expect(waitingPill(sv).tone).toBe('warning');
    expect(waitingPill(sv).label).not.toBe('Waiting for approval');
  });
});

describe('the way out', () => {
  const editor = ['register.read', 'gaps.edit'];
  const officer = ['register.read', 'gaps.edit', 'risk.accept.approve'];
  const approver = ['register.read', 'risk.accept.approve'];

  it('offers Start remediation and Accept the risk on open work to someone who edits gaps', () => {
    expect(gapActions(gap(), SARA.id, editor)).toMatchObject({ edit: true, startRemediation: true, close: false, acceptRisk: true, approve: false, reopen: false });
  });

  it('offers Close once remediation is under way', () => {
    expect(gapActions(gap({ status: { key: 'remediating', kind: 'remediating', label: 'Remediating' } }), SARA.id, editor)).toMatchObject({ startRemediation: false, close: true, acceptRisk: true });
  });

  it('never offers the requester an Approve, and says someone else approves', () => {
    const actions = gapActions(gap({ riskAcceptance: waiting }), SARA.id, officer);
    expect(actions).toMatchObject({ approve: false, ownRequest: true, acceptRisk: false, startRemediation: false });
  });

  it('offers Approve to a different holder of risk.accept.approve, and to nobody without it', () => {
    expect(gapActions(gap({ riskAcceptance: waiting }), MARIA.id, approver)).toMatchObject({ approve: true, ownRequest: false });
    expect(gapActions(gap({ riskAcceptance: waiting }), MARIA.id, editor).approve).toBe(false);
  });

  it('offers Reopen on an accepted or closed gap, and nothing to a reader', () => {
    const accepted = gap({ status: { key: 'risk_accepted', kind: 'risk_accepted', label: 'Risk accepted' }, riskAcceptance: { ...waiting, approvedBy: MARIA, approvedAt: '2026-09-23T09:00:00Z' } });
    expect(gapActions(accepted, SARA.id, editor)).toMatchObject({ reopen: true, edit: false, approve: false });
    expect(Object.values(gapActions(gap(), SARA.id, ['register.read'])).some(Boolean)).toBe(false);
  });

  it('moves by the key of the first active row in a category', () => {
    const rows = [
      { key: 'open', kind: 'open' },
      { key: 'old_fix', kind: 'remediating', active: false },
      { key: 'in_progress', kind: 'remediating' },
    ];
    expect(statusKeyOf(rows, 'remediating')).toBe('in_progress');
    expect(statusKeyOf(rows, 'closed')).toBeNull();
  });
});

describe('the target line', () => {
  const today = new Date('2026-09-25T10:00:00Z');

  it('counts the days left, and the days overdue on open work only', () => {
    expect(targetLine(gap(), today, en, defaultFormatContext)).toEqual({ text: 'Target 30 Nov 2026, in 66 days', overdue: false });
    const late = targetLine(gap({ targetDate: '2026-09-15' }), today, en, defaultFormatContext);
    expect(late.overdue).toBe(true);
    expect(late.text).toMatch(/^Target 15 Sept? 2026, 10 days overdue$/);
    expect(targetLine(gap({ targetDate: '2026-09-15', status: { key: 'closed', kind: 'closed', label: 'Closed' } }), today, en, defaultFormatContext).overdue).toBe(false);
    expect(targetLine(gap({ targetDate: null }), today, en, defaultFormatContext).text).toBe('No target date');
  });

  it('names a team that owns the gap, or says nobody does yet', () => {
    expect(ownerName(gap({ owner: null, ownerTeam: { key: 'retail', kind: null, label: 'Retail compliance' } }), en)).toBe('Retail compliance');
    expect(ownerName(gap({ owner: null }), en)).toBe('No owner yet');
  });
});

describe('refusals', () => {
  it('renders the four-eyes refusal from its code, and the missing approval grant only when approving', () => {
    expect(gapProblemCopy(en).four_eyes_violation).toBe('You asked for this, so someone else has to approve it.');
    expect(gapProblemCopy(en).permission_denied).toBeUndefined();
    expect(gapProblemCopy(en, true).permission_denied).toBe('Only someone who may accept risk can approve this.');
    expect(gapProblemCopy(sv).four_eyes_violation).toBe('Du bad om detta, så någon annan måste godkänna det.');
  });
});
