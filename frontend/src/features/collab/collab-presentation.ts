import type { PillTone } from '@/components/ui/pill-tones';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { notificationKindTone } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';
import { localeTags } from '@/shared/i18n';
import { formatDateTime, type FormatContext } from '@/shared/utils/format';

import type { Comment, NotificationKind, NotificationPrefs, PersonRef } from './types';

// The collab records on screen (COL-01, COL-02). A notification's kind turns
// into its catalog label and its tone by kind; a comment turns into its
// author, its time and whether it was edited. Nothing here reads a comment's
// text, and no component decides a tone.

export const NOTIFICATION_KIND_LABEL: Record<NotificationKind, MessageKey> = {
  mention: 'collab.notification.kind.mention',
  assigned: 'collab.notification.kind.assigned',
  participant_added: 'collab.notification.kind.participantAdded',
  signoff_requested: 'collab.notification.kind.signoffRequested',
  approval_requested: 'collab.notification.kind.approvalRequested',
  due_soon: 'collab.notification.kind.dueSoon',
  review_due: 'collab.notification.kind.reviewDue',
  overdue: 'collab.notification.kind.overdue',
  escalation: 'collab.notification.kind.escalation',
  involved_item_changed: 'collab.notification.kind.involvedItemChanged',
  proposal_waiting: 'collab.notification.kind.proposalWaiting',
  saved_search_hit: 'collab.notification.kind.savedSearchHit',
};

// The API may add a kind before the screen knows it: it then reads generically.
function isKind(value: string): value is NotificationKind {
  return Object.hasOwn(NOTIFICATION_KIND_LABEL, value);
}

export function notificationKindLabel(kind: string, t: Translate): string {
  return t(isKind(kind) ? NOTIFICATION_KIND_LABEL[kind] : 'collab.notification.kind.other');
}

export function notificationTone(kind: string): PillTone {
  return isKind(kind) ? notificationKindTone[kind] : 'information';
}

export function presentNotification(notification: { kind: string }, t: Translate): PresentedPill[] {
  return [{ key: 'kind', label: notificationKindLabel(notification.kind, t), tone: notificationTone(notification.kind), order: 0 }];
}

// The calendar day an instant falls on in the bank's timezone, as YYYY-MM-DD.
function dayOf(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone }).format(date);
}

/**
 * "Today 14:20", "Yesterday 09:02", then the date and time, in the bank's
 * timezone. Days are counted on the calendar, so a daylight saving change
 * never moves a row into the wrong day.
 */
export function formatCollabTime(value: string, now: Date, ctx: FormatContext, t: Translate): string {
  const date = new Date(value);
  const days = (Date.parse(dayOf(now, ctx.timeZone)) - Date.parse(dayOf(date, ctx.timeZone))) / 86_400_000;
  if (days !== 0 && days !== 1) return formatDateTime(date, ctx);
  const time = new Intl.DateTimeFormat(localeTags[ctx.locale], { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: ctx.timeZone }).format(date);
  return t(days === 0 ? 'collab.time.today' : 'collab.time.yesterday', { time });
}

export interface PresentedComment {
  author: string;
  time: string;
  /** "Edited" when the author corrected it, else null. */
  edited: string | null;
  /** "Comment deleted" in place of the text, else null. */
  deleted: string | null;
}

export function presentComment(comment: Pick<Comment, 'author' | 'createdAt' | 'editedAt' | 'deletedAt'>, now: Date, ctx: FormatContext, t: Translate): PresentedComment {
  const deleted = comment.deletedAt !== null;
  return {
    author: comment.author.name,
    time: formatCollabTime(comment.createdAt, now, ctx, t),
    edited: !deleted && comment.editedAt !== null ? t('collab.comments.edited') : null,
    deleted: deleted ? t('collab.comments.deleted') : null,
  };
}

/** "Not notified: Johan Berg." for the author, by name and never why; null when everyone was reached. */
export function notNotifiedLine(people: readonly PersonRef[], t: Translate): string | null {
  return people.length === 0 ? null : t('collab.comments.notNotified', { names: people.map((p) => p.name).join(', ') });
}

const LIMITED_KIND = new Map<string, MessageKey>([
  ['obligation', 'collab.comments.limited.obligation'],
  ['tenant_obligation', 'collab.comments.limited.tenantObligation'],
  ['change_case', 'collab.comments.limited.changeCase'],
  ['action', 'collab.comments.limited.action'],
]);

/** One line per kind of record My work held back, never naming a record. */
export function permissionLimitedLines(kinds: readonly string[], t: Translate): string[] {
  return kinds.map((kind) => t(LIMITED_KIND.get(kind) ?? 'collab.comments.limited.other'));
}

/** The switches a person may turn off, in the card's order. Escalations have none: the bank sets them. */
export const NOTIFICATION_SWITCHES: readonly { key: keyof NotificationPrefs; label: MessageKey; hint: MessageKey }[] = [
  { key: 'mentions', label: 'collab.prefs.mentions', hint: 'collab.prefs.mentionsHint' },
  { key: 'assignments', label: 'collab.prefs.assignments', hint: 'collab.prefs.assignmentsHint' },
  { key: 'reminders', label: 'collab.prefs.reminders', hint: 'collab.prefs.remindersHint' },
  { key: 'weeklyDigest', label: 'collab.prefs.weeklyDigest', hint: 'collab.prefs.weeklyDigestHint' },
  { key: 'weeklyBriefing', label: 'collab.prefs.weeklyBriefing', hint: 'collab.prefs.weeklyBriefingHint' },
];
