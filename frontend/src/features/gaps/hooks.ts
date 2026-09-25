'use client';

import { useObligation } from '@/features/library/hooks';
import { useRegisterEntry } from '@/features/register/hooks';
import type { RegisterGap } from '@/features/register/types';

// Where a gap sits, for its row and its record: the obligation's title and the
// legal entity's name. A gap carries ids only, so both come from reads the
// obligation page makes too; the query cache fetches each obligation once
// however many of its gaps are on screen, and an entity is looked up only when
// the gap names one.

export interface GapPlace {
  obligationTitle: string | null;
  entityName: string | null;
}

export function useGapPlace(gap: Pick<RegisterGap, 'obligationId' | 'orgUnitId'>): GapPlace {
  const obligation = useObligation(gap.obligationId);
  const entry = useRegisterEntry(gap.obligationId, gap.orgUnitId !== null);
  const record = obligation.data;
  return {
    obligationTitle: record === undefined ? null : (record.title?.text ?? record.instrument.shortName),
    entityName: gap.orgUnitId === null ? null : (entry.data?.entities.find((row) => row.orgUnitId === gap.orgUnitId)?.orgUnitName ?? null),
  };
}
