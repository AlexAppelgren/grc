'use client';

// "How we read this rule" and the assessment history (REG-04).
// ObligationScreen mounts it once, at its place in design/screens/tenant-obligation.html;
// the panel's own package fills this file and never edits the page. Until then it renders nothing.
export function ObligationHistoryPanel({ obligationId: _obligationId }: { obligationId: string }) {
  return null;
}
