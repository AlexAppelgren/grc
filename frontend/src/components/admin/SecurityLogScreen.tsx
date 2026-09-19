'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { describeDevice } from '@/features/identity/identity-presentation';
import { SECURITY_LOG_PAGE, useSecurityLog } from '@/features/tenant-admin/hooks';
import { loginMethodText, presentLoginEvent } from '@/features/tenant-admin/members-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// The security log (design/screens/admin-security-log.html, ID-11): login
// events newest first, twenty a page, the event kind as a pill whose tone
// and label come from the kind. Nothing here can be edited.

export function SecurityLogScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const [offset, setOffset] = useState(0);
  const log = useSecurityLog(offset);

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('admin.securityLog.title')} lede={t('admin.securityLog.lede')} />
      {log.isPending ? (
        <LoadingState />
      ) : log.isError ? (
        <ErrorState title={t('admin.securityLog.errorTitle')} onRetry={() => void log.refetch()} />
      ) : log.data.items.length === 0 ? (
        <EmptyState title={t('admin.securityLog.emptyTitle')} body={t('admin.securityLog.emptyBody')} />
      ) : (
        <>
          <Panel className="px-4 py-1" data-security-log="">
            {log.data.items.map((event) => (
              <div key={event.id} className="grid gap-1 border-b border-line py-3 last:border-b-0 md:grid-cols-[170px_1fr] md:gap-x-4" data-event={event.event}>
                <time dateTime={event.occurredAt} className="block text-meta text-muted">
                  {formatDateTime(event.occurredAt, ctx)}
                </time>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <PillRow pills={presentLoginEvent(event, t)} />
                    <span>{event.email}</span>
                  </div>
                  <Meta>
                    <span>{loginMethodText(event.method, t)}</span>
                    {event.ip !== null ? <code className="font-mono">{event.ip}</code> : null}
                    {event.userAgent.length > 0 ? <span>{describeDevice(event.userAgent, t)}</span> : null}
                    {event.failureReason.length > 0 ? <span>{event.failureReason}</span> : null}
                  </Meta>
                </div>
              </div>
            ))}
          </Panel>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-meta text-muted">
            <span>{t('admin.securityLog.range', { from: offset + 1, to: Math.min(offset + log.data.items.length, log.data.total), total: log.data.total })}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - SECURITY_LOG_PAGE))}>
                {t('admin.securityLog.newer')}
              </Button>
              <Button variant="outline" size="small" disabled={offset + SECURITY_LOG_PAGE >= log.data.total} onClick={() => setOffset(offset + SECURITY_LOG_PAGE)}>
                {t('admin.securityLog.older')}
              </Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
