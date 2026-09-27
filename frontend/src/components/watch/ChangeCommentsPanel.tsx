'use client';

import { CommentsPanel } from '@/features/collab/CommentsPanel';
import type { CasePanelProps } from '@/features/cases/types';
import { usePermissions } from '@/shared/navigation/require-permission';

// The comments on this bank's case (COL-01): a bank's change page is its case,
// so the comments hang on the case and not on the shared change. The change
// page mounts it only when the change has a case; a reader whose role cannot
// read cases is shown the case block but not its comments, which answer 404.
const CASES_READ = 'cases.read';

export function ChangeCommentsPanel({ workflow }: CasePanelProps) {
  const canRead = (usePermissions() ?? []).includes(CASES_READ);
  return canRead ? <CommentsPanel subject={{ subjectType: 'change_case', subjectId: workflow.id }} /> : null;
}
