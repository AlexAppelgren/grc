'use client';

// The comment thread on the obligation (COL-01); filled by c10-fe-comments-panel.
// ObligationScreen mounts it once, at its place in design/screens/tenant-obligation.html;
// the panel's own package fills this file and never edits the page. Until then it renders nothing.
export function ObligationCommentsPanel({ obligationId: _obligationId }: { obligationId: string }) {
  return null;
}
