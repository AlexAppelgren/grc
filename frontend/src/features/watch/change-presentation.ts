import { byOrder, type KindRef, type PresentedPill, type VocabularyRef } from '@/features/shared/presentation-types';
import { slotTone, urgencyTone, type UrgencyKind } from '@/features/shared/tone-by-kind';

// Change row and header (design/system/pills-and-labels.md, slot order):
// change type, urgency, flags, library tags, tenant tags, then workflow
// status on the header only. Authority and date follow as plain meta text,
// which the screen renders itself.

export interface ChangeFacts {
  type: VocabularyRef;
  urgency: KindRef<UrgencyKind>;
  flags: readonly VocabularyRef[];
  libraryTags?: readonly VocabularyRef[];
  tenantTags?: readonly VocabularyRef[];
  workflowStatus?: VocabularyRef;
}

export type ChangeView = 'row' | 'header';

export const CHANGE_SLOT_ORDER = {
  type: 10,
  urgency: 20,
  flags: 30,
  libraryTags: 40,
  tenantTags: 50,
  workflowStatus: 60,
} as const;

export function presentChange(change: ChangeFacts, view: ChangeView): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: `type:${change.type.key}`, label: change.type.label, tone: slotTone.changeType, order: CHANGE_SLOT_ORDER.type },
    {
      key: `urgency:${change.urgency.key}`,
      label: change.urgency.label,
      tone: urgencyTone[change.urgency.kind],
      order: CHANGE_SLOT_ORDER.urgency,
    },
    ...change.flags.map((flag, i) => ({
      key: `flag:${flag.key}`,
      label: flag.label,
      tone: slotTone.flag,
      order: CHANGE_SLOT_ORDER.flags + i,
    })),
    ...(change.libraryTags ?? []).map((tag, i) => ({
      key: `library-tag:${tag.key}`,
      label: tag.label,
      tone: slotTone.libraryTag,
      order: CHANGE_SLOT_ORDER.libraryTags + i,
    })),
    ...(change.tenantTags ?? []).map((tag, i) => ({
      key: `tenant-tag:${tag.key}`,
      label: tag.label,
      tone: slotTone.tenantTag,
      order: CHANGE_SLOT_ORDER.tenantTags + i,
      outlined: true,
    })),
  ];
  if (view === 'header' && change.workflowStatus !== undefined) {
    pills.push({
      key: `status:${change.workflowStatus.key}`,
      label: change.workflowStatus.label,
      tone: slotTone.workflowStatus,
      order: CHANGE_SLOT_ORDER.workflowStatus,
    });
  }
  return pills.sort(byOrder);
}
