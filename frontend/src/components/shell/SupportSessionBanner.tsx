'use client';

import Link from 'next/link';

import { Button } from '@/components/ui/Button';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { CONSOLE_HOME } from '@/shared/navigation/registry';
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

/** The page a support session meets on 401 support_access_ended: the grant was revoked or its window closed. */
export function SupportAccessEnded({ tenantName }: { tenantName: string }) {
  const t = useT();
  return (
    <section role="alert" data-support-ended="" className="mx-auto max-w-[60ch] py-12 text-center">
      <h1>{t('supportAccess.ended.title')}</h1>
      <p className="mt-3 text-muted">{t('supportAccess.ended.body', { tenant: tenantName })}</p>
      <p className="mt-3 text-muted">
        <Link href={CONSOLE_HOME} className="underline">
          {t('supportAccess.ended.back')}
        </Link>
      </p>
    </section>
  );
}
