import type { RoadmapItem } from '@/features/home/types';
import type { KindRef, PresentedPill } from '@/features/shared/presentation-types';
import { slotTone, urgencyTone, type UrgencyKind } from '@/features/shared/tone-by-kind';
import { daysUntil } from '@/features/watch/change-presentation';
import type { Translate } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n/messages';
import { formatPartialDate, type FormatContext } from '@/shared/utils/format';

// Roadmap item (design/system/pills-and-labels.md, slot order): urgency or
// "Our deadline", then date and days left as plain text the screen renders.

export interface RoadmapItemFacts {
  /** A regulatory date carries the change's urgency. */
  urgency?: KindRef<UrgencyKind>;
  /** An internal date (assessment deadline, action due, review due) is ours. */
  ourDeadline: boolean;
}

export function presentRoadmapItem(item: RoadmapItemFacts, t: Translate): PresentedPill[] {
  if (item.ourDeadline) {
    return [{ key: 'our-deadline', label: t('pill.ourDeadline'), tone: slotTone.ourDeadline, order: 0 }];
  }
  if (item.urgency === undefined) return [];
  return [{ key: `urgency:${item.urgency.key}`, label: item.urgency.label, tone: urgencyTone[item.urgency.kind], order: 0 }];
}

export interface RoadmapWhen {
  date: string;
  /** Days until a date stated to the day; null for today, the past and any less exact date. */
  daysLeft: number | null;
}

// A legal date is a plain date with a precision (HOM-03, INV-S10). A date
// stated as a quarter is stored on a day of it, so it is printed as the
// quarter and never counted down to that day.
export function roadmapWhen(item: Pick<RoadmapItem, 'date' | 'datePrecision'>, ctx: FormatContext, today: Date): RoadmapWhen {
  const date = formatPartialDate(item.date, item.datePrecision, ctx);
  const days = item.datePrecision === 'day' ? daysUntil(item.date, today) : null;
  return { date, daysLeft: days !== null && days > 0 ? days : null };
}

// Our own deadlines (HOM-03, AC-TEN1): what produced the date, who answers for
// it and where its record is. Every item type has its phrase here, so a type
// the API adds fails the typecheck instead of printing a key.
const WHAT: Record<RoadmapItem['itemType'], MessageKey> = {
  change_date: 'roadmap.regulatoryDate',
  review_due: 'roadmap.what.reviewDue',
  gap_target: 'roadmap.what.gapTarget',
  certificate_expiry: 'roadmap.what.certificateExpiry',
  certificate_audit: 'roadmap.what.certificateAudit',
  internal_deadline: 'roadmap.what.internalDeadline',
  action_due: 'roadmap.what.actionDue',
};

export function roadmapWhat(itemType: RoadmapItem['itemType'], t: Translate): string {
  return t(WHAT[itemType]);
}

/** A person, a team, or both on a register entry; "Nobody yet" when neither. */
export function roadmapOwner(owner: RoadmapItem['owner'], t: Translate): string {
  const names = [owner?.person?.name, owner?.team?.label].filter((name): name is string => name !== undefined);
  return names.length === 0 ? t('roadmap.owner.nobody') : names.join(', ');
}

/** The card's line under its title: "Regulatory date", or "Our deadline · Next review · Johan Berg". */
export function roadmapCardLine(item: Pick<RoadmapItem, 'kind' | 'itemType' | 'owner'>, t: Translate): string {
  if (item.kind !== 'internal') return t('roadmap.regulatoryDate');
  return [t('pill.ourDeadline'), roadmapWhat(item.itemType, t), roadmapOwner(item.owner, t)].join(' · ');
}

/** A review or a gap target opens its obligation, whose page holds its gaps; a certificate has no page of its own here. */
export function roadmapSubjectHref(subject: RoadmapItem['subject']): string | null {
  return subject?.obligationId ? `/inventory/obligations/${subject.obligationId}` : null;
}
