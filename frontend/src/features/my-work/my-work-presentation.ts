import type { MyComment } from '@/features/collab/types';
import { presentCompliance } from '@/features/register/register-presentation';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { urgencyTone } from '@/features/shared/tone-by-kind';
import { urgencyOf } from '@/features/watch/change-presentation';
import type { MessageKey, Translate } from '@/shared/i18n';
import { formatPartialDate, type FormatContext } from '@/shared/utils/format';

import type { WorkBucket, WorkDate, WorkItem, WorkItemKind, WorkScope } from './types';

// My work's words (HOM-05, design/screens/tenant-my-work.html). The API sends
// keys, kinds, dates and names; every phrase is built here from the catalog.
// Reasons are muted text, never pills, and the pills are the ones each record
// type already draws, so there is no new slot and no new tone.

/** The four sections, in the order the page draws them. */
export const SECTIONS: readonly { bucket: WorkBucket; title: MessageKey; empty: MessageKey; count: 'overdue' | 'dueSoon' | 'aware' | 'open' }[] = [
  { bucket: 'overdue', title: 'work.section.overdue', empty: 'work.section.emptyOverdue', count: 'overdue' },
  { bucket: 'due_soon', title: 'work.section.dueSoon', empty: 'work.section.emptyDueSoon', count: 'dueSoon' },
  { bucket: 'aware', title: 'work.section.aware', empty: 'work.section.emptyAware', count: 'aware' },
  { bucket: 'open', title: 'work.section.open', empty: 'work.section.emptyOpen', count: 'open' },
];

const KIND_LABEL: Record<WorkItemKind, MessageKey> = {
  tenant_obligation: 'work.kind.tenantObligation',
  internal_item: 'work.kind.internalItem',
  change_case: 'work.kind.changeCase',
};

const LIMITED_LABEL: Record<WorkItemKind, MessageKey> = {
  tenant_obligation: 'work.limited.tenantObligation',
  internal_item: 'work.limited.internalItem',
  change_case: 'work.limited.changeCase',
};

const DATE_LABEL: Record<WorkDate['kind'], MessageKey> = {
  review: 'work.date.review',
  gap_target: 'work.date.gapTarget',
  duty_due: 'work.date.dutyDue',
  internal_deadline: 'work.date.internalDeadline',
  action_due: 'work.date.actionDue',
  key_date: 'work.date.keyDate',
  linked: 'work.date.linked',
  version_applied: 'work.date.versionApplied',
  commented: 'work.date.commented',
};

export function kindLabel(kind: WorkItemKind, t: Translate): string {
  return t(KIND_LABEL[kind]);
}

/** One line per kind the reader's role cannot open, never how many rows it hid. */
export function permissionLimitedLines(kinds: readonly WorkItemKind[], t: Translate): string[] {
  return kinds.map((kind) => t(LIMITED_LABEL[kind]));
}

/** The bank's own today, a plain date in its time zone: every day count is against it. */
export function tenantToday(now: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone }).format(now);
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}

export interface WorkWhen {
  /** "Review 7 Sep 2026", or "No date". */
  date: string;
  /** "12 days overdue", "in 9 days", "Today" or "4 days ago"; null without a day to count from. */
  days: string | null;
}

/**
 * The date that placed the row and how far it is from the bank's today. In
 * "Changes on your items" the date is when the change happened, so it counts
 * back; everywhere else it is the next date, overdue or ahead. A date the
 * source gave only to the month or year is never counted in days.
 */
export function workWhen(item: Pick<WorkItem, 'bucket' | 'date'>, today: string, ctx: FormatContext, t: Translate): WorkWhen {
  if (item.date === null) return { date: t('work.date.none'), days: null };
  const date = t(DATE_LABEL[item.date.kind], { date: formatPartialDate(item.date.value, item.date.precision, ctx) });
  if (item.date.precision !== 'day') return { date, days: null };
  const ahead = daysBetween(today, item.date.value);
  if (ahead === 0) return { date, days: t('work.days.today') };
  if (item.bucket === 'aware') return { date, days: ahead < 0 ? t('work.days.ago', { count: -ahead }) : null };
  return { date, days: ahead < 0 ? t('work.days.overdue', { count: -ahead }) : t('work.days.ahead', { count: ahead }) };
}

/**
 * Why the row is here, each phrase once. In the reader's own view the person
 * named is the reader; in a department view the person or team is named. A
 * change is on the list through an obligation, which the phrase names.
 */
export function workReasons(item: Pick<WorkItem, 'reasons'>, scope: WorkScope['scope'], t: Translate): string[] {
  const phrases = item.reasons.map((reason) => {
    if (reason.via !== null) return t('work.reason.linkedTo', { title: reason.via.title });
    const owns = reason.reason === 'owner';
    if (scope === 'unit') {
      const name = reason.who.person?.name ?? reason.who.team?.label ?? '';
      return t(owns ? 'work.reason.namedOwns' : 'work.reason.namedTakesPart', { name });
    }
    if (reason.who.team !== null) return t(owns ? 'work.reason.yourTeamOwns' : 'work.reason.yourTeamTakesPart');
    return t(owns ? 'work.reason.youOwn' : 'work.reason.youTakePart');
  });
  return [...new Set(phrases)];
}

/** The pills the record already has elsewhere: an obligation's compliance status, a change's urgency. */
export function presentWorkItem(item: Pick<WorkItem, 'status' | 'urgency'>): PresentedPill[] {
  const pills: PresentedPill[] = [];
  if (item.status !== null) pills.push(presentCompliance({ key: item.status.key, label: item.status.label, kind: item.status.kind ?? null }));
  const urgency = urgencyOf(item.urgency);
  if (urgency !== null) pills.push({ key: `urgency:${urgency.key}`, label: urgency.label, tone: urgencyTone[urgency.kind], order: 0 });
  return pills;
}

/** Where the row's title goes: the obligation page, the change page, or nowhere for an internal item. */
export function workHref(item: Pick<WorkItem, 'subject'>): string | null {
  if (item.subject.obligationId !== null) return `/inventory/obligations/${item.subject.obligationId}`;
  if (item.subject.changeId !== null) return `/watch/${item.subject.changeId}`;
  return null;
}

/** Where a comment on My work links: the record it was written on. */
export function myCommentHref(comment: Pick<MyComment, 'subjectType' | 'subjectId' | 'changeId'>): string | null {
  if (comment.subjectType === 'obligation') return `/inventory/obligations/${comment.subjectId}`;
  if (comment.changeId !== null) return `/watch/${comment.changeId}`;
  return null;
}
