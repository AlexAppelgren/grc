'use client';

import { CommentsPanel } from '@/features/collab/CommentsPanel';

// The comment thread on the obligation (COL-01). The comments are the bank's own,
// kept in its tenant zone, on the shared library record.
export function ObligationCommentsPanel({ obligationId }: { obligationId: string }) {
  return <CommentsPanel subject={{ subjectType: 'obligation', subjectId: obligationId }} />;
}
