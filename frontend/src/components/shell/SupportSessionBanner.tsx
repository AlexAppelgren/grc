'use client';

import { Button } from '@/components/ui/Button';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// A support session (TEN-06, D-49; design/screens/admin-support-access.html
// states 5 and 6). The banner sits above the page title on every tenant
// screen the session opens: it names the bank, says the session only reads
// and when it ends, and carries Leave. The shell mounts it once the session
// guard tells the client it is a support session.

export function SupportSessionBanner({ tenantName, endsAt, onLeave }: { tenantName: string; endsAt: string; onLeave: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <div role="status" data-support-banner="" className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-control bg-accent px-3 py-2">
      <p className="m-0">
        <b className="font-semibold">{t('supportAccess.banner.title', { tenant: tenantName })}</b> {t('supportAccess.banner.until', { time: formatDateTime(endsAt, ctx) })}
      </p>
      <Button variant="outline" size="small" onClick={onLeave}>
        {t('supportAccess.banner.leave')}
      </Button>
    </div>
  );
}
