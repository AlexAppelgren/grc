'use client';

import { productName } from '@/shared/brand';
import { useT } from '@/shared/i18n/LocaleProvider';

// Placeholder for the signed-in user (prototype `.who`). Phase 1 replaces the
// body with the session: name, role, sign out. "Switch user" from the
// prototype never ships (design/README.md).
export function WhoPanel() {
  const t = useT();
  return (
    <div className="mx-1 mt-4 rounded-s border border-on-brand-line p-3 text-meta text-on-brand-muted">
      <span>{t('shell.notSignedIn')}</span>
      <b className="block font-semibold text-on-brand">{productName}</b>
      <p className="mt-1">{t('shell.notSignedInHint')}</p>
    </div>
  );
}
