'use client';

import { useObligation } from '@/features/library/hooks';
import type { RegisterGap } from '@/features/register/types';

// The title of the obligation a gap sits on, for its row and its record. A gap
// carries the obligation's id only; the query cache fetches each obligation
// once however many of its gaps are on screen, and the obligation page has
// already read it.
export function useObligationTitle(gap: Pick<RegisterGap, 'obligationId'>): string | null {
  const record = useObligation(gap.obligationId).data;
  return record === undefined ? null : (record.title?.text ?? record.instrument.shortName);
}
