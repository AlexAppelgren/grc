import type { ChangeRow } from '@/features/watch/api';
import { presentChangeRow } from '@/features/watch/change-presentation';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';

// The lead card (design/screens/tenant-today.html, tenant-briefing.html;
// design/system/pills-and-labels.md "Computed" row): the `brand` pill "Lead"
// first, then the change's own pills in their fixed slot order. One
// presentation function, so Today's card and the briefing's card can never
// choose two different pill sets for the same change.
export function presentLead(row: ChangeRow, t: Translate): PresentedPill[] {
  const lead: PresentedPill = { key: 'lead', label: t('pill.lead'), tone: slotTone.lead, order: -1 };
  return [lead, ...presentChangeRow(row, 'row', t)];
}
