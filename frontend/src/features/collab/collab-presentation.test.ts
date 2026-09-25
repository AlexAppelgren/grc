import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { pillToneNames } from '@/components/ui/pill-tones';
import { notificationKindTone } from '@/features/shared/tone-by-kind';
import { createT } from '@/shared/i18n';
import { formatDateTime, type FormatContext } from '@/shared/utils/format';

import {
  NOTIFICATION_KIND_LABEL,
  NOTIFICATION_SWITCHES,
  formatCollabTime,
  notificationKindLabel,
  notificationTone,
  notNotifiedLine,
  permissionLimitedLines,
  presentComment,
  presentNotification,
} from './collab-presentation';
import type { Comment } from './types';

// A notification's pill reads its kind, never a person's choice; a comment's
// line reads its author, its time in the bank's timezone and whether it was
// edited, never its text.

const t = createT('en');
const sv = createT('sv');
const stockholm: FormatContext = { locale: 'en', timeZone: 'Europe/Stockholm' };

// The kinds the published contract names, read from the committed OpenAPI
// export rather than restated here: a kind the backend adds fails this test
// until it has a tone and a label.
function contractKinds(): string[] {
  const spec = JSON.parse(readFileSync(join(import.meta.dirname, '..', '..', '..', '..', 'openapi.json'), 'utf8')) as {
    components: { schemas: { CollabNotification: { properties: { kind: { enum: string[] } } } } };
  };
  return spec.components.schemas.CollabNotification.properties.kind.enum;
}

describe('a notification kind', () => {
  it('has a tone from the six and a label in both languages for every kind the contract names', () => {
    const kinds = contractKinds();
    expect(kinds.length).toBeGreaterThan(0);
    for (const kind of kinds) {
      expect(Object.keys(notificationKindTone), `no tone for ${kind}`).toContain(kind);
      expect(Object.keys(NOTIFICATION_KIND_LABEL), `no label for ${kind}`).toContain(kind);
      expect(pillToneNames).toContain(notificationTone(kind));
      expect(notificationKindLabel(kind, t)).not.toBe(t('collab.notification.kind.other'));
      expect(notificationKindLabel(kind, sv)).not.toBe(notificationKindLabel(kind, t));
    }
    expect(Object.keys(notificationKindTone).sort()).toEqual([...kinds].sort());
  });

  it('reads the tone the card draws: a neutral fact, something waiting on the reader, the overdue end, a kind of change', () => {
    expect(notificationKindTone).toEqual({
      mention: 'information',
      assigned: 'information',
      participant_added: 'information',
      signoff_requested: 'warning',
      approval_requested: 'warning',
      due_soon: 'warning',
      review_due: 'warning',
      proposal_waiting: 'warning',
      overdue: 'negative',
      escalation: 'negative',
      involved_item_changed: 'notice',
      saved_search_hit: 'notice',
    });
  });

  it('becomes one pill with its label and tone', () => {
    expect(presentNotification({ kind: 'escalation' }, t)).toEqual([{ key: 'kind', label: 'Escalated', tone: 'negative', order: 0 }]);
    expect(presentNotification({ kind: 'mention' }, sv)).toEqual([{ key: 'kind', label: 'Omnämnande', tone: 'information', order: 0 }]);
    expect(notificationKindLabel('involved_item_changed', t)).toBe('Change on your item');
  });

  it('shows a kind the screen does not know yet generically, rather than failing', () => {
    expect(notificationKindLabel('follow_hit', t)).toBe('Notification');
    expect(notificationTone('follow_hit')).toBe('information');
  });
});

describe('the time on a notification or a comment', () => {
  const now = new Date('2026-09-24T12:00:00Z');

  it('says today or yesterday with the time in the bank\'s timezone, then the date', () => {
    expect(formatCollabTime('2026-09-24T06:00:00Z', now, stockholm, t)).toBe('Today 08:00');
    expect(formatCollabTime('2026-09-23T12:20:00Z', now, stockholm, t)).toBe('Yesterday 14:20');
    expect(formatCollabTime('2026-09-23T12:20:00Z', now, { locale: 'sv', timeZone: 'Europe/Stockholm' }, sv)).toBe('Igår 14:20');
    expect(formatCollabTime('2026-09-21T06:00:00Z', now, stockholm, t)).toBe(formatDateTime('2026-09-21T06:00:00Z', stockholm));
  });

  it('draws the day line in the bank\'s timezone, not the browser\'s', () => {
    // 22:30 UTC on the 23rd is already the 24th in Helsinki.
    expect(formatCollabTime('2026-09-23T22:30:00Z', now, { locale: 'en', timeZone: 'Europe/Helsinki' }, t)).toBe('Today 01:30');
    expect(formatCollabTime('2026-09-23T22:30:00Z', now, stockholm, t)).toBe('Today 00:30');
    expect(formatCollabTime('2026-09-23T22:30:00Z', now, { locale: 'en', timeZone: 'UTC' }, t)).toBe('Yesterday 22:30');
  });

  it('counts calendar days across a daylight saving change, never 24-hour steps', () => {
    // Stockholm's clocks go back on 25 October 2026, so that Sunday lasts 25 hours.
    const mondayEarly = new Date('2026-10-25T23:30:00Z'); // Monday 00:30 in Stockholm
    expect(formatCollabTime('2026-10-24T22:30:00Z', mondayEarly, stockholm, t)).toBe('Yesterday 00:30');
    // Clocks go forward on 29 March 2026, so that Sunday lasts 23 hours.
    const mondayAfterSpring = new Date('2026-03-29T22:30:00Z'); // Monday 00:30 in Stockholm
    expect(formatCollabTime('2026-03-28T22:45:00Z', mondayAfterSpring, stockholm, t)).toBe(formatDateTime('2026-03-28T22:45:00Z', stockholm));
    expect(formatCollabTime('2026-03-29T08:00:00Z', mondayAfterSpring, stockholm, t)).toBe('Yesterday 10:00');
  });
});

describe('a comment line', () => {
  const now = new Date('2026-09-24T12:00:00Z');
  const comment = {
    author: { id: 'u-erik', name: 'Erik Holm' },
    body: '@Sara can you check the custody angle?',
    createdAt: '2026-09-24T06:00:00Z',
    editedAt: null,
    deletedAt: null,
  } satisfies Pick<Comment, 'author' | 'body' | 'createdAt' | 'editedAt' | 'deletedAt'>;

  it('names the author and the time, and says nothing about an edit that did not happen', () => {
    expect(presentComment(comment, now, stockholm, t)).toEqual({ author: 'Erik Holm', time: 'Today 08:00', edited: null, deleted: null });
  });

  it('says Edited once the author corrected it', () => {
    expect(presentComment({ ...comment, editedAt: '2026-09-24T06:05:00Z' }, now, stockholm, t).edited).toBe('Edited');
    expect(presentComment({ ...comment, editedAt: '2026-09-24T06:05:00Z' }, now, stockholm, sv).edited).toBe('Redigerad');
  });

  it('keeps a deleted comment\'s author and time and marks it deleted, with no Edited', () => {
    const deleted = { ...comment, body: null, editedAt: '2026-09-24T06:05:00Z', deletedAt: '2026-09-24T07:00:00Z' };
    expect(presentComment(deleted, now, stockholm, t)).toEqual({
      author: 'Erik Holm',
      time: 'Today 08:00',
      edited: null,
      deleted: 'Comment deleted',
    });
  });

  it('never carries the text: the line is built from the author and the dates alone', () => {
    const line = presentComment(comment, now, stockholm, t);
    expect(Object.values(line).join(' ')).not.toContain('custody');
  });
});

describe('the composer and My work', () => {
  it('names the mentioned people who were not notified, by name and never why, or says nothing', () => {
    expect(notNotifiedLine([{ id: 'u-1', name: 'Johan Berg' }], t)).toBe('Not notified: Johan Berg.');
    expect(notNotifiedLine([{ id: 'u-1', name: 'Johan Berg' }, { id: 'u-2', name: 'Anna Nilsson' }], t)).toBe('Not notified: Johan Berg, Anna Nilsson.');
    expect(notNotifiedLine([], t)).toBeNull();
  });

  it('says which kinds of record were held back, one line per kind, never a record', () => {
    expect(permissionLimitedLines(['change_case', 'action'], t)).toEqual([
      'Cases are not shown here, because your role cannot open them',
      'Actions are not shown here, because your role cannot open them',
    ]);
    expect(permissionLimitedLines(['obligation', 'tenant_obligation'], sv)).toEqual([
      'Skyldigheter visas inte här, eftersom din roll inte kan öppna dem',
      'Din organisations skyldigheter visas inte här, eftersom din roll inte kan öppna dem',
    ]);
    expect(permissionLimitedLines(['reg_unit'], t)).toEqual(['Some records are not shown here, because your role cannot open them']);
    expect(permissionLimitedLines([], t)).toEqual([]);
  });
});

describe('the notification switches', () => {
  it('offers the five switches a person may turn off, in the card\'s order, each with a label and a hint', () => {
    expect(NOTIFICATION_SWITCHES.map((s) => s.key)).toEqual(['mentions', 'assignments', 'reminders', 'weeklyDigest', 'weeklyBriefing']);
    expect(NOTIFICATION_SWITCHES.map((s) => [t(s.label), t(s.hint)])[0]).toEqual(['Mentions', 'When someone mentions you in a comment.']);
    for (const s of NOTIFICATION_SWITCHES) expect(sv(s.label)).not.toBe(t(s.label));
  });
});
