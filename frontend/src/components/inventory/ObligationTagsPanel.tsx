'use client';

// The bank's own tags on the obligation; filled by c10-fe-obligation-tags.
// ObligationScreen mounts it once, at its place in design/screens/tenant-obligation.html;
// the panel's own package fills this file and never edits the page. Until then it renders nothing.
export function ObligationTagsPanel({ obligationId: _obligationId }: { obligationId: string }) {
  return null;
}
