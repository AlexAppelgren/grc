import { describe, expect, it } from 'vitest';

import { pillToneNames } from '@/components/ui/pill-tones';
import { scanStateTone, slotTone } from '@/features/shared/tone-by-kind';
import { createT } from '@/shared/i18n';

import {
  closeKindOf,
  closeReasonLabel,
  daysLeftText,
  isDownloadable,
  presentCaseStatus,
  presentCaseUrgency,
  presentOverdue,
  presentScanState,
} from './case-presentation';

// The case panels' pills and computed text (design/system/pills-and-labels.md,
// "Case work"): each tone by slot or by kind, each phrase from the catalog or
// from the bank's own row.

const t = createT('en');
const sv = createT('sv');
// The tenant-local day the fixtures count from; a due date is an offset from it.
const TODAY = new Date(Date.UTC(2026, 8, 19));
const day = (offset: number) => new Date(TODAY.getTime() + offset * 86_400_000).toISOString().slice(0, 10);

describe('the status pill', () => {
  it('reads the category’s phrase in the workflow status slot’s tone', () => {
    expect(presentCaseStatus({ category: 'signoff', subStatus: null }, t)).toMatchObject({ key: 'status:signoff', label: 'Waiting for sign-off', tone: 'information' });
    expect(presentCaseStatus({ category: 'new' }, sv).label).toBe('Behöver triage');
  });

  it('a sub-status changes the words to the bank’s own label and never the tone', () => {
    const pill = presentCaseStatus({ category: 'assessing', subStatus: { key: 'waiting_for_legal', label: 'Waiting for legal' } }, t);
    expect([pill.key, pill.label, pill.tone]).toEqual(['status:assessing', 'Waiting for legal', slotTone.workflowStatus]);
  });
});

describe('the urgency pill', () => {
  it('takes its tone from the level’s own fixed row', () => {
    expect(presentCaseUrgency({ key: 'act_now', kind: null, label: 'Act now' })).toMatchObject({ label: 'Act now', tone: 'negative' });
    expect(presentCaseUrgency({ key: 'within_3_months', kind: null, label: 'Within 3 months' })?.tone).toBe('warning');
    expect(presentCaseUrgency({ key: 'no_action', kind: null, label: 'No action' })?.tone).toBe('positive');
  });

  it('shows nothing for no urgency, and for a key outside the fixed levels rather than a guessed tone', () => {
    expect(presentCaseUrgency(null)).toBeNull();
    expect(presentCaseUrgency({ key: 'someday', kind: null, label: 'Someday' })).toBeNull();
  });
});

describe('the scan state pill', () => {
  it('reads each state by its kind: being checked notice, checked positive, an unfinished scan warning, malware negative', () => {
    expect((['pending', 'clean', 'error', 'infected'] as const).map((state) => [presentScanState(state, t).label, presentScanState(state, t).tone])).toEqual([
      ['Being checked', 'notice'],
      ['Checked', 'positive'],
      ['Could not be checked', 'warning'],
      ['Refused, malware found', 'negative'],
    ]);
    expect(presentScanState('infected', sv).label).toBe('Avvisad, skadlig kod hittad');
  });

  it('offers only a checked file for download', () => {
    expect(isDownloadable({ kind: 'file', scanState: 'clean' })).toBe(true);
    expect(isDownloadable({ kind: 'file', scanState: 'pending' })).toBe(false);
    expect(isDownloadable({ kind: 'file', scanState: 'infected' })).toBe(false);
    expect(isDownloadable({ kind: 'link', scanState: 'clean' })).toBe(false);
  });

  it('takes every tone from the six', () => {
    for (const tone of [...Object.values(scanStateTone), slotTone.overdue]) expect(pillToneNames).toContain(tone);
  });
});

describe('a due date', () => {
  it('an open action past its date reads Overdue, negative, and how late', () => {
    const late = { dueDate: day(-4), done: false };
    expect(presentOverdue(late, TODAY, t)).toMatchObject({ label: 'Overdue', tone: 'negative' });
    expect(daysLeftText(late, TODAY, t)).toBe('4 days late');
    expect(daysLeftText({ dueDate: day(-1), done: false }, TODAY, t)).toBe('1 day late');
  });

  it('a date still ahead shows no pill, only the days left; today is due today', () => {
    expect(presentOverdue({ dueDate: day(11), done: false }, TODAY, t)).toBeNull();
    expect(daysLeftText({ dueDate: day(11), done: false }, TODAY, t)).toBe('11 days left');
    expect(daysLeftText({ dueDate: day(1), done: false }, TODAY, sv)).toBe('1 dag kvar');
    expect(presentOverdue({ dueDate: day(0), done: false }, TODAY, t)).toBeNull();
    expect(daysLeftText({ dueDate: day(0), done: false }, TODAY, t)).toBe('Due today');
  });

  it('a done action shows neither, however late it was', () => {
    expect(presentOverdue({ dueDate: day(-4), done: true }, TODAY, t)).toBeNull();
    expect(daysLeftText({ dueDate: day(-4), done: true }, TODAY, t)).toBeNull();
  });

  it('a date that is not one shows nothing rather than a wrong count', () => {
    expect(presentOverdue({ dueDate: 'soon', done: false }, TODAY, t)).toBeNull();
    expect(daysLeftText({ dueDate: 'soon', done: false }, TODAY, t)).toBeNull();
  });
});

describe('the close reason', () => {
  const closed = (kind: string | null) => ({
    category: 'closed' as const,
    closeReason: { key: `reason_${kind}`, kind, label: `Reason ${kind}` },
    dismissedReason: null,
  });

  it('reads how a case was closed off the reason row’s fixed kind', () => {
    expect(closeKindOf(closed('signed_off'))).toBe('signed_off');
    expect(closeKindOf(closed('no_action'))).toBe('no_action');
    expect(closeKindOf(closed('not_applicable'))).toBe('not_applicable');
  });

  it('knows no kind for an open case, a reason without one or a kind it does not know', () => {
    expect(closeKindOf({ ...closed('signed_off'), category: 'signoff' })).toBeNull();
    expect(closeKindOf(closed(null))).toBeNull();
    expect(closeKindOf(closed('archived'))).toBeNull();
    expect(closeKindOf({ ...closed(null), closeReason: null })).toBeNull();
  });

  it('labels a close or a dismissal in the bank’s own words, and an open case not at all', () => {
    expect(closeReasonLabel(closed('no_action'))).toBe('Reason no_action');
    expect(closeReasonLabel({ category: 'closed', closeReason: null, dismissedReason: null })).toBeNull();
    const dismissed = { category: 'dismissed' as const, closeReason: null, dismissedReason: { key: 'out_of_scope', kind: null, label: 'Out of scope' } };
    expect(closeReasonLabel(dismissed)).toBe('Out of scope');
    expect(closeReasonLabel({ ...dismissed, dismissedReason: null })).toBeNull();
    expect(closeReasonLabel({ ...dismissed, category: 'assessing' })).toBeNull();
  });
});
