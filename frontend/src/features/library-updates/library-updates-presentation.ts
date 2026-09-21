import type { PillTone } from '@/components/ui/pill-tones';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';

import type { LibraryUpdateRow } from './types';

// Pills and derived facts for /inventory/updates (design/screens/tenant-library-updates.html;
// PRO-03, INV-04). The kind pill sits in the change-type slot (notice), the
// instrument or vocabulary list in the brand slot, matching every other
// library-facing card (pills-and-labels.md).

const KIND_LABEL: Readonly<Record<string, MessageKey>> = {
  new_obligation_version: 'library.updates.kind.newVersion',
  vocabulary_create: 'library.updates.kind.vocabulary',
  vocabulary_relabel: 'library.updates.kind.vocabulary',
  vocabulary_retire: 'library.updates.kind.vocabulary',
  vocabulary_restore: 'library.updates.kind.vocabulary',
  vocabulary_merge: 'library.updates.kind.vocabulary',
  term_create: 'library.updates.kind.vocabulary',
  term_update: 'library.updates.kind.vocabulary',
};

export function updateKindLabel(kind: string, t: Translate): string {
  const key = KIND_LABEL[kind];
  return key === undefined ? t('library.updates.kind.other') : t(key);
}

export function presentLibraryUpdate(row: Pick<LibraryUpdateRow, 'kind' | 'target' | 'vocabularyList'>, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [{ key: 'kind', label: updateKindLabel(row.kind, t), tone: slotTone.proposalKind, order: 10 }];
  if (row.target !== null && row.target.instrumentShortName !== '') {
    pills.push({ key: 'instrument', label: row.target.instrumentShortName, tone: slotTone.instrument, order: 20 });
  } else if (row.vocabularyList !== null) {
    pills.push({ key: 'list', label: row.vocabularyList, tone: 'brand' as PillTone, order: 20 });
  }
  return pills.sort(byOrder);
}

export function titleOf(row: Pick<LibraryUpdateRow, 'target' | 'vocabularyList' | 'kind'>, t: Translate): string {
  if (row.target !== null) return row.target.title;
  return updateKindLabel(row.kind, t);
}
