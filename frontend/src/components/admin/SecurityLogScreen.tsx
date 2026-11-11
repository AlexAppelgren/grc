'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { QueryState } from '@/components/ui/States';
import { Pager } from '@/components/ui/Pager';
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
      <QueryState query={log} errorTitle={t('admin.securityLog.errorTitle')}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title={t('admin.securityLog.emptyTitle')} body={t('admin.securityLog.emptyBody')} />
          ) : (
            <>
              <Panel className="px-4 py-1" data-security-log="">
                {data.items.map((event) => (
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
              <Pager inTime offset={offset} limit={SECURITY_LOG_PAGE} shown={data.items.length} total={data.total} onOffset={setOffset} />
            </>
          )
        }
      </QueryState>
    </>
  );
}
