'use client';

// "Gaps": what is missing, with an owner and a target date (REG-03).
// ObligationScreen mounts it once, at its place in design/screens/tenant-obligation.html;
// the panel's own package fills this file and never edits the page. Until then it renders nothing.
export function ObligationGapsPanel({ obligationId: _obligationId }: { obligationId: string }) {
  return null;
}
