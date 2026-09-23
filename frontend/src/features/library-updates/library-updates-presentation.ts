import { partialDateOf } from '@/features/library/api';
import { inForceLabel } from '@/features/library/version-presentation';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';
import type { FormatContext } from '@/shared/utils/format';

import type { LibraryUpdateRow } from './types';

// Pills and derived facts for /inventory/updates (design/screens/tenant-library-updates.html;
// PRO-03, INV-04, FP-03). The kind pill sits in the change-type slot (notice),
// the instrument or the changed list row in the brand slot, matching every
// other library-facing card (pills-and-labels.md). The API sends keys and
// labels; nothing here shows a key.

const NEW_VERSION = 'new_obligation_version';

/** The fixed kinds of a change to a shared list or to the taxonomy, which this screen reads as one "Vocabulary" kind. */
const VOCABULARY_KINDS: readonly string[] = [
  'vocabulary_create',
  'vocabulary_relabel',
  'vocabulary_retire',
  'vocabulary_restore',
  'vocabulary_merge',
  'term_create',
  'term_update',
];

/** The kind filter's values: `GET /library-updates` takes one kind or several separated by commas. */
export const KIND_FILTER = { newVersion: NEW_VERSION, vocabulary: VOCABULARY_KINDS.join(',') } as const;

export function updateKindLabel(kind: string, t: Translate): string {
  if (kind === NEW_VERSION) return t('library.updates.kind.newVersion');
  if (VOCABULARY_KINDS.includes(kind)) return t('library.updates.kind.vocabulary');
  return t('library.updates.kind.other');
}

export function presentLibraryUpdate(row: Pick<LibraryUpdateRow, 'kind' | 'target' | 'vocabulary'>, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [{ key: 'kind', label: updateKindLabel(row.kind, t), tone: slotTone.proposalKind, order: 10 }];
  const target = row.target ?? null;
  if (target !== null && target.instrumentShortName !== '') {
    pills.push({ key: 'instrument', label: target.instrumentShortName, tone: slotTone.instrument, order: 20 });
  } else if (row.vocabulary) {
    pills.push({ key: 'vocabulary', label: row.vocabulary.label, tone: slotTone.libraryTag, order: 20 });
  }
  return pills.sort(byOrder);
}

/** The duty's own title (its reference when it has none); a change to a shared list names no record, so it reads as its kind. */
export function titleOf(row: Pick<LibraryUpdateRow, 'target' | 'kind'>, t: Translate): string {
  const target = row.target ?? null;
  if (target === null) return updateKindLabel(row.kind, t);
  return target.title !== '' ? target.title : target.referenceLabel;
}

/** "In force from Q4 2026": the legal date the new wording binds from, at the precision it is known to. */
export function inForceLine(row: Pick<LibraryUpdateRow, 'effectiveFrom'>, t: Translate, ctx: FormatContext): string | null {
  const from = partialDateOf(row.effectiveFrom);
  return from === null ? null : inForceLabel(from, null, t, ctx);
}

/** "Outside our scope: Execution only": the terms that put a duty outside the footprint, only on a row shown with "Show outside our scope". */
export function outsideScopeLine(row: Pick<LibraryUpdateRow, 'inFootprint' | 'outsideReason'>, t: Translate): string | null {
  const terms = (row.outsideReason ?? []).flatMap((reason) => reason.terms);
  if (row.inFootprint || terms.length === 0) return null;
  return t('library.updates.outsideScope', { terms: terms.map((term) => term.label).join(', ') });
}
