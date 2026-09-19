import type { KindRef, PresentedPill } from '@/features/shared/presentation-types';
import { slotTone, urgencyTone, type UrgencyKind } from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';

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
