'use client';

import Link from 'next/link';
import { useState, type ReactNode } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useDecideSupportAccess, useSupportAccess, type SupportDecision } from '@/features/support-access/hooks';
import { groupSupportGrants, presentSupportGrant } from '@/features/support-access/support-access-presentation';
import type { SupportAccessGrant } from '@/features/support-access/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDateTime } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// Support access (design/screens/admin-support-access.html, TEN-06, D-49):
// any member reads who from platform support asked to look in and who was let
// in. A holder of security.manage approves with a passkey (the api client
// opens the prompt on the server's step_up_required), declines, or revokes a
// live grant; declining and revoking take access away and need no passkey.

const SECURITY_MANAGE = 'security.manage';
const INVALID_TRANSITION = 'invalid_transition';

interface Attempt {
  grantId: string;
  decision: SupportDecision;
}

function Facts({ children }: { children: ReactNode }) {
  return <dl className="m-0 mt-2 grid gap-x-3.5 gap-y-1.5 text-meta md:grid-cols-[150px_1fr]">{children}</dl>;
}

function Fact({ label, children, mono = false }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className={mono ? 'm-0 font-mono' : 'm-0'}>{children}</dd>
    </>
  );
}

function GrantRow({ grant, actions }: { grant: SupportAccessGrant; actions?: ReactNode }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Row data-grant-id={grant.id} data-grant-state={grant.state}>
      <PillRow pills={presentSupportGrant(grant, t)} />
      <h3 className="mt-1.5 font-semibold">{t('supportAccess.who', { name: grant.platformPerson.name })}</h3>
      <Facts>
        <Fact label={t('supportAccess.field.purpose')}>{grant.purpose}</Fact>
        {grant.ticketRef !== '' ? (
          <Fact label={t('supportAccess.field.ticket')} mono>
            {grant.ticketRef}
          </Fact>
        ) : null}
        <Fact label={t('supportAccess.field.askedFor')}>
          {grant.state === 'pending' ? t('supportAccess.hoursFromApproval', { hours: grant.hours }) : t('supportAccess.hours', { hours: grant.hours })}
        </Fact>
        <Fact label={t('supportAccess.field.requested')}>{formatDateTime(grant.requestedAt, ctx)}</Fact>
        {grant.decidedBy !== null && grant.decidedAt !== null ? (
          <Fact label={t('supportAccess.field.decided')}>{t('supportAccess.decidedBy', { date: formatDateTime(grant.decidedAt, ctx), name: grant.decidedBy.name })}</Fact>
        ) : null}
        {grant.endsAt !== null ? <Fact label={t('supportAccess.field.until')}>{formatDateTime(grant.endsAt, ctx)}</Fact> : null}
      </Facts>
      {actions}
    </Row>
  );
}

function Actions({
  grant,
  canDecide,
  busy,
  attempt,
  error,
  onDecide,
}: {
  grant: SupportAccessGrant;
  canDecide: boolean;
  busy: SupportDecision | null;
  attempt: Attempt | null;
  error: unknown;
  onDecide: (decision: SupportDecision) => void;
}) {
  const t = useT();
  if (!canDecide) return <p className="mt-2 text-meta text-muted">{t('supportAccess.needsSecurity')}</p>;
  const pending = grant.state === 'pending';
  const failed = attempt?.grantId === grant.id && busy === null && error !== null && !hasProblemCode(error, INVALID_TRANSITION);
  return (
    <>
      <p className="mt-2 text-meta text-muted">{pending ? t('supportAccess.approveHint') : t('supportAccess.revokeHint')}</p>
      {failed ? <ProblemAlert error={error} codes={{ step_up_required: t('supportAccess.stepUpCancelled') }} /> : null}
      <ButtonBar>
        {pending ? (
          <>
            <Button variant="outline" size="small" disabled={busy !== null} onClick={() => onDecide('decline')}>
              {t('supportAccess.decline')}
            </Button>
            <Button size="small" disabled={busy !== null} onClick={() => onDecide('approve')}>
              {busy === 'approve' ? t('supportAccess.approving') : t('supportAccess.approve')}
            </Button>
          </>
        ) : (
          <Button variant="danger" size="small" disabled={busy !== null} onClick={() => onDecide('revoke')}>
            {t('supportAccess.revoke')}
          </Button>
        )}
      </ButtonBar>
    </>
  );
}

export function SupportAccessScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const grants = useSupportAccess();
  const canDecide = (usePermissions() ?? []).includes(SECURITY_MANAGE);
  const approve = useDecideSupportAccess('approve');
  const decline = useDecideSupportAccess('decline');
  const revoke = useDecideSupportAccess('revoke');
  const mutations = { approve, decline, revoke };
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const running = attempt === null ? null : mutations[attempt.decision];
  const error = running?.error ?? null;
  const busyFor = (grantId: string): SupportDecision | null => (attempt?.grantId === grantId && running?.isPending === true ? attempt.decision : null);

  const onDecide = (grant: SupportAccessGrant, decision: SupportDecision) => {
    setAttempt({ grantId: grant.id, decision });
    setStatus(null);
    mutations[decision].mutate(grant.id, {
      onSuccess: (decided) => {
        const name = decided.platformPerson.name;
        if (decision === 'approve') setStatus(t('supportAccess.approved', { name, time: formatDateTime(decided.endsAt ?? decided.requestedAt, ctx) }));
        else if (decision === 'decline') setStatus(t('supportAccess.declined'));
        else setStatus(t('supportAccess.revoked', { name, time: formatDateTime(decided.decidedAt ?? decided.requestedAt, ctx) }));
      },
    });
  };

  const actionsFor = (grant: SupportAccessGrant) => (
    <Actions grant={grant} canDecide={canDecide} busy={busyFor(grant.id)} attempt={attempt} error={error} onDecide={(decision) => onDecide(grant, decision)} />
  );

  const items = grants.data?.pages.flatMap((page) => page.items) ?? [];
  const { pending, active, history } = groupSupportGrants(items);

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('supportAccess.title')} lede={t('supportAccess.lede')} />
      {status !== null ? <StatusLine tone="positive">{status}</StatusLine> : null}
      {hasProblemCode(error, INVALID_TRANSITION) ? <ProblemAlert error={error} codes={{ [INVALID_TRANSITION]: t('supportAccess.stale') }} /> : null}
      {grants.isPending ? (
        <LoadingState />
      ) : grants.isError ? (
        <ErrorState title={t('supportAccess.errorTitle')} onRetry={() => void grants.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={t('supportAccess.emptyTitle')} body={t('supportAccess.emptyBody')} />
      ) : (
        <div className="mt-4">
          {pending.length > 0 ? (
            <Panel title={t('supportAccess.pending.title')} data-support-section="pending">
              <Rows>
                {pending.map((grant) => (
                  <GrantRow key={grant.id} grant={grant} actions={actionsFor(grant)} />
                ))}
              </Rows>
            </Panel>
          ) : null}
          {active.length > 0 ? (
            <Panel title={t('supportAccess.active.title')} data-support-section="active">
              <Rows>
                {active.map((grant) => (
                  <GrantRow key={grant.id} grant={grant} actions={actionsFor(grant)} />
                ))}
              </Rows>
            </Panel>
          ) : null}
          {history.length > 0 ? (
            <Panel title={t('supportAccess.history.title')} data-support-section="history">
              <p className="mb-2.5 text-meta text-muted">
                {t('supportAccess.history.caption')}{' '}
                <Link href="/admin/audit-log" className="underline">
                  {t('supportAccess.history.auditLog')}
                </Link>
              </p>
              <Rows>
                {history.map((grant) => (
                  <GrantRow key={grant.id} grant={grant} />
                ))}
              </Rows>
              {grants.hasNextPage ? (
                <ButtonBar>
                  <Button variant="outline" size="small" disabled={grants.isFetchingNextPage} onClick={() => void grants.fetchNextPage()}>
                    {t('supportAccess.showMore')}
                  </Button>
                </ButtonBar>
              ) : null}
            </Panel>
          ) : null}
        </div>
      )}
    </>
  );
}
