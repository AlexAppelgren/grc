'use client';

import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { useFormatContext, useRevokeSession, useSessions } from '@/features/identity/hooks';
import { describeDevice, presentSession } from '@/features/identity/identity-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// My sessions (design/screens/me-sessions.html, ID-04): every device,
// "This device" on the current one, sign out the others.

export function SessionsScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const sessions = useSessions();
  const revoke = useRevokeSession();

  return (
    <>
      <PageHead title={t('me.sessions.title')} lede={t('me.sessions.lede')} />
      {sessions.isPending ? (
        <LoadingState />
      ) : sessions.isError ? (
        <ErrorState title={t('me.sessions.errorTitle')} onRetry={() => void sessions.refetch()} />
      ) : sessions.data.length === 0 ? (
        <EmptyState title={t('me.sessions.emptyTitle')} body={t('me.sessions.emptyBody')} />
      ) : (
        <Rows>
          {sessions.data.map((session) => (
            <Row key={session.id} data-session-id={session.id} data-current={session.current ? '' : undefined}>
              <div className="grid gap-2 md:grid-cols-[1fr_auto] md:items-center">
                <div>
                  <h3 className="mb-1 font-semibold">{describeDevice(session.userAgent, t)}</h3>
                  <Meta>
                    <PillRow pills={presentSession(session, t)} />
                    <span>{t('me.sessions.signedIn', { date: formatDateTime(session.createdAt, ctx) })}</span>
                    <span>{t('me.sessions.lastSeen', { date: formatDateTime(session.lastSeenAt, ctx) })}</span>
                    {session.ip !== null ? <code className="font-mono">{session.ip}</code> : null}
                  </Meta>
                  {revoke.isError && revoke.variables === session.id ? <ProblemAlert error={revoke.error} /> : null}
                </div>
                {session.current ? null : (
                  <ButtonBar className="mt-0">
                    <Button variant="danger" size="small" disabled={revoke.isPending} onClick={() => revoke.mutate(session.id)}>
                      {t('me.sessions.signOutDevice')}
                    </Button>
                  </ButtonBar>
                )}
              </div>
            </Row>
          ))}
        </Rows>
      )}
    </>
  );
}
