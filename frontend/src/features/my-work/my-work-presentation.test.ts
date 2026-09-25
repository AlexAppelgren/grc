import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import type { FormatContext } from '@/shared/utils/format';

import {
  SECTIONS,
  kindLabel,
  myCommentHref,
  permissionLimitedLines,
  presentWorkItem,
  tenantToday,
  workHref,
  workReasons,
  workWhen,
} from './my-work-presentation';
import type { WorkDate, WorkItem, WorkReason } from './types';

// Every section, reason and date kind has its words in both languages, and a
// day count is taken against the bank's own today, never the browser's.

const en = createT('en');
const sv = createT('sv');
const ctx: FormatContext = { locale: 'en', timeZone: 'Europe/Stockholm' };
const svCtx: FormatContext = { locale: 'sv', timeZone: 'Europe/Stockholm' };
const TODAY = '2026-09-19';

const ANNA = { id: 'u-anna', name: 'Anna Nilsson' };
const RETAIL = { key: 'retail_compliance', kind: null, label: 'Retail compliance' };

function reason(kind: WorkReason['reason'], who: 'person' | 'team', via: WorkReason['via'] = null): WorkReason {
  return { reason: kind, who: who === 'person' ? { person: ANNA, team: null } : { person: null, team: RETAIL }, via };
}

function dated(bucket: WorkItem['bucket'], value: string, kind: WorkDate['kind'] = 'review', precision: WorkDate['precision'] = 'day') {
  return { bucket, date: { value, kind, precision } };
}

describe('the sections', () => {
  it('are the four buckets in the page order, each titled and with an empty line in en and sv', () => {
    expect(SECTIONS.map((s) => s.bucket)).toEqual(['overdue', 'due_soon', 'aware', 'open']);
    expect(SECTIONS.map((s) => en(s.title))).toEqual(['Overdue', 'Due soon', 'Changes on your items', "Everything you're responsible for"]);
    expect(SECTIONS.map((s) => sv(s.title))).toEqual(['Försenat', 'Snart dags', 'Förändringar i det du ansvarar för', 'Allt du ansvarar för']);
    for (const section of SECTIONS) {
      expect(en(section.empty)).not.toBe(section.empty);
      expect(sv(section.empty)).not.toBe(en(section.empty));
    }
  });
});

describe('workWhen', () => {
  it('counts an overdue date back from the bank today, singular and plural', () => {
    expect(workWhen(dated('overdue', '2026-09-07'), TODAY, ctx, en)).toEqual({ date: 'Review 7 Sept 2026', days: '12 days overdue' });
    expect(workWhen(dated('overdue', '2026-09-18'), TODAY, ctx, en).days).toBe('1 day overdue');
    expect(workWhen(dated('overdue', '2026-09-07'), TODAY, svCtx, sv)).toEqual({ date: 'Granskning 7 sep. 2026', days: '12 dagar försenad' });
  });

  it('counts a date ahead, and says today on the day', () => {
    expect(workWhen(dated('due_soon', '2026-09-28', 'gap_target'), TODAY, ctx, en)).toEqual({ date: 'Gap target 28 Sept 2026', days: 'in 9 days' });
    expect(workWhen(dated('due_soon', '2026-09-20'), TODAY, ctx, en).days).toBe('in 1 day');
    expect(workWhen(dated('due_soon', '2026-09-28'), TODAY, svCtx, sv).days).toBe('om 9 dagar');
    expect(workWhen(dated('due_soon', TODAY), TODAY, ctx, en).days).toBe('Today');
    expect(workWhen(dated('due_soon', TODAY), TODAY, svCtx, sv).days).toBe('Idag');
  });

  it('counts a change on an item back as days ago', () => {
    expect(workWhen(dated('aware', '2026-09-15', 'version_applied'), TODAY, ctx, en)).toEqual({ date: 'New version applied 15 Sept 2026', days: '4 days ago' });
    expect(workWhen(dated('aware', '2026-09-15', 'version_applied'), TODAY, svCtx, sv).days).toBe('för 4 dagar sedan');
    expect(workWhen(dated('aware', '2026-09-18', 'linked'), TODAY, ctx, en).days).toBe('1 day ago');
  });

  it('never counts days on a date the source gave only to the month', () => {
    expect(workWhen(dated('open', '2026-12-01', 'key_date', 'month'), TODAY, ctx, en)).toEqual({ date: 'Key date December 2026', days: null });
  });

  it('says there is no date on an undated row', () => {
    expect(workWhen({ bucket: 'open', date: null }, TODAY, ctx, en)).toEqual({ date: 'No date', days: null });
    expect(workWhen({ bucket: 'open', date: null }, TODAY, svCtx, sv).date).toBe('Inget datum');
  });

  it('names every date kind in en and sv', () => {
    const kinds: WorkDate['kind'][] = ['review', 'gap_target', 'duty_due', 'internal_deadline', 'action_due', 'key_date', 'linked', 'version_applied', 'commented'];
    const enLabels = kinds.map((kind) => workWhen(dated('open', '2026-10-01', kind), TODAY, ctx, en).date);
    const svLabels = kinds.map((kind) => workWhen(dated('open', '2026-10-01', kind), TODAY, svCtx, sv).date);
    expect(enLabels).toEqual([
      'Review 1 Oct 2026',
      'Gap target 1 Oct 2026',
      'Duty due 1 Oct 2026',
      'Our deadline 1 Oct 2026',
      'Action due 1 Oct 2026',
      'Key date 1 Oct 2026',
      'Linked 1 Oct 2026',
      'New version applied 1 Oct 2026',
      'Commented 1 Oct 2026',
    ]);
    expect(new Set(svLabels).size).toBe(kinds.length);
    for (const label of svLabels) expect(label).toContain('1 okt. 2026');
  });
});

describe('tenantToday', () => {
  it('is the date in the bank time zone, not UTC', () => {
    // 23:30 UTC on 18 September is already 19 September in Stockholm.
    expect(tenantToday(new Date('2026-09-18T23:30:00Z'), 'Europe/Stockholm')).toBe('2026-09-19');
    expect(tenantToday(new Date('2026-09-18T23:30:00Z'), 'UTC')).toBe('2026-09-18');
  });
});

describe('workReasons', () => {
  it('speaks to the reader in their own view, in en and sv', () => {
    const all = [reason('owner', 'person'), reason('owner', 'team'), reason('participant', 'person'), reason('participant', 'team')];
    expect(all.map((r) => workReasons({ reasons: [r] }, 'mine', en)[0])).toEqual([
      "You're responsible",
      'Your team is responsible',
      'You take part',
      'Your team takes part',
    ]);
    expect(all.map((r) => workReasons({ reasons: [r] }, 'mine', sv)[0])).toEqual(['Du ansvarar', 'Ditt team ansvarar', 'Du deltar', 'Ditt team deltar']);
  });

  it('names the person or the team in a department view', () => {
    expect(workReasons({ reasons: [reason('owner', 'person'), reason('participant', 'team')] }, 'unit', en)).toEqual([
      'Anna Nilsson is responsible',
      'Retail compliance takes part',
    ]);
    expect(workReasons({ reasons: [reason('owner', 'team')] }, 'unit', sv)).toEqual(['Retail compliance ansvarar']);
  });

  it('names the obligation a change is linked through, once', () => {
    const via = { obligationId: 'ob-1', title: 'Pay for third-party research only under the permitted models' };
    const reasons = [reason('owner', 'person', via), reason('owner', 'team', via)];
    expect(workReasons({ reasons }, 'mine', en)).toEqual(['Linked to Pay for third-party research only under the permitted models']);
    expect(workReasons({ reasons }, 'mine', sv)).toEqual(['Kopplad till Pay for third-party research only under the permitted models']);
  });
});

describe('the kinds', () => {
  it('have a name and a permission-limited line in en and sv', () => {
    const kinds = ['tenant_obligation', 'internal_item', 'change_case'] as const;
    expect(kinds.map((kind) => kindLabel(kind, en))).toEqual(['Obligation', 'Internal item', 'Change']);
    expect(kinds.map((kind) => kindLabel(kind, sv))).toEqual(['Skyldighet', 'Internt underlag', 'Förändring']);
    expect(permissionLimitedLines(['tenant_obligation'], en)).toEqual([
      'Obligations are not shown here, and are left out of the counts, because your role cannot open them.',
    ]);
    expect(permissionLimitedLines([...kinds], sv)).toHaveLength(3);
    expect(permissionLimitedLines([], en)).toEqual([]);
  });
});

describe('presentWorkItem', () => {
  it('draws an obligation status by its kind and a change urgency by its key, nothing else', () => {
    expect(presentWorkItem({ status: { key: 'partly_ok', kind: 'partly', label: 'Partly compliant' }, urgency: null })).toEqual([
      expect.objectContaining({ label: 'Partly compliant', tone: 'warning' }),
    ]);
    expect(presentWorkItem({ status: null, urgency: { key: 'act_now', kind: null, label: 'Act now' } })).toEqual([
      expect.objectContaining({ label: 'Act now', tone: 'negative' }),
    ]);
    expect(presentWorkItem({ status: null, urgency: null })).toEqual([]);
  });
});

describe('links', () => {
  it('open the obligation or the change page, and nothing for an internal item', () => {
    const subject = { obligationId: null, changeId: null, internalItemId: null, title: 'Complaints procedure' };
    expect(workHref({ subject: { ...subject, obligationId: 'ob-1' } })).toBe('/inventory/obligations/ob-1');
    expect(workHref({ subject: { ...subject, changeId: 'ch-1' } })).toBe('/watch/ch-1');
    expect(workHref({ subject: { ...subject, internalItemId: 'ii-1' } })).toBeNull();
  });

  it('send a comment to the record it was written on', () => {
    expect(myCommentHref({ subjectType: 'obligation', subjectId: 'ob-1', changeId: null })).toBe('/inventory/obligations/ob-1');
    expect(myCommentHref({ subjectType: 'change_case', subjectId: 'case-1', changeId: 'ch-1' })).toBe('/watch/ch-1');
  });
});
