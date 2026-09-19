import { byOrder, type KindRef, type PresentedPill, type VocabularyRef } from '@/features/shared/presentation-types';
import { gapTone, severityTone, slotTone, type GapKind, type SeverityKind } from '@/features/shared/tone-by-kind';

// Gap (design/system/pills-and-labels.md, slot order): gap status, severity,
// source.

export interface GapFacts {
  status: KindRef<GapKind>;
  severity: KindRef<SeverityKind>;
  source?: VocabularyRef;
}

export const GAP_SLOT_ORDER = { status: 10, severity: 20, source: 30 } as const;

export function presentGap(gap: GapFacts): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: `gap-status:${gap.status.key}`, label: gap.status.label, tone: gapTone[gap.status.kind], order: GAP_SLOT_ORDER.status },
    { key: `severity:${gap.severity.key}`, label: gap.severity.label, tone: severityTone[gap.severity.kind], order: GAP_SLOT_ORDER.severity },
  ];
  if (gap.source !== undefined) {
    pills.push({ key: `source:${gap.source.key}`, label: gap.source.label, tone: slotTone.source, order: GAP_SLOT_ORDER.source });
  }
  return pills.sort(byOrder);
}
