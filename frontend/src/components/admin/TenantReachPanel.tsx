'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useApproveReach, useRejectReach, useRequestReach, useSwitchOffReach, useTenantReach } from '@/features/agent-access/hooks';
import type { TenantReach, TenantReachRequest } from '@/features/agent-access/types';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { humanisePermission, usePermissions } from '@/shared/navigation/require-permission';
import { formatDateTime } from '@/shared/utils/format';
import { problemFrom } from '@/shared/utils/problem';

// Tenant reach (design/screens/admin-security.html, states 1 and 5 to 12;
// ACC-08): whether the agents the bank registers under Agents, Access may
// read its register decisions at all. Its own panel below the policy form,
// never part of Save. Off until two different holders of security.manage
// switch it on, one asking and another approving, each with a passkey; the
// requester is never offered a decision, and should their approval reach the
// server anyway its 409 four_eyes_violation is drawn as a state. Rejecting and
// switching off ask for a passkey too; switching off needs one person.

const SECURITY_MANAGE = 'security.manage';
const ACCESS_HREF = '/admin/agents/access';

type Done = 'asked' | 'approved' | 'rejected' | 'switchedOff';

const DONE_KEY: Record<Done, MessageKey> = {
  asked: 'agentAccess.tenantReach.asked',
  approved: 'agentAccess.tenantReach.approved',
  rejected: 'agentAccess.tenantReach.rejected',
  switchedOff: 'agentAccess.tenantReach.switchedOff',
};

const refusals = (t: (key: MessageKey) => string): Record<string, string> => ({
  request_pending: t('agentAccess.tenantReach.requestPending'),
  invalid_transition: t('agentAccess.tenantReach.alreadyDecided'),
  stale_write: t('agentAccess.tenantReach.alreadyDecided'),
  step_up_required: t('problem.stepUpCancelled'),
});

function Pending({ request, mine, onDone, onFourEyes }: { request: TenantReachRequest; mine: boolean; onDone: (done: Done) => void; onFourEyes: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const approve = useApproveReach();
  const reject = useRejectReach();
  const date = formatDateTime(request.requestedAt, ctx);
  const failed = approve.isError ? approve.error : reject.isError ? reject.error : null;
  const busy = approve.isPending || reject.isPending;
  const decide = (write: typeof approve, done: Done) =>
    write.mutate(request, {
      onSuccess: () => onDone(done),
      onError: (error) => {
        if (problemFrom(error)?.code === 'four_eyes_violation') onFourEyes();
      },
    });

  if (mine) {
    return (
      <>
        <Notice tone="warn" data-reach-pending="mine">
          {t('agentAccess.tenantReach.pendingMine', { date })}
        </Notice>
        <p className="text-meta text-muted">{t('agentAccess.tenantReach.pendingMineNote')}</p>
      </>
    );
  }
  return (
    <>
      <Notice tone="warn" data-reach-pending="other">
        {t('agentAccess.tenantReach.pendingOther', { name: request.requestedBy.name, date })}
      </Notice>
      {failed !== null && problemFrom(failed)?.code !== 'four_eyes_violation' ? <ProblemAlert error={failed} codes={refusals(t)} /> : null}
      <ButtonBar>
        <Button variant="danger" disabled={busy} onClick={() => decide(reject, 'rejected')}>
          {t('agentAccess.tenantReach.reject')}
        </Button>
        <Button disabled={busy} onClick={() => decide(approve, 'approved')}>
          {t('agentAccess.tenantReach.approve')}
        </Button>
      </ButtonBar>
      <p className="mt-2 text-right text-meta text-muted">{t('agentAccess.tenantReach.decideHint')}</p>
    </>
  );
}

function Off({ onDone }: { onDone: (done: Done) => void }) {
  const t = useT();
  const ask = useRequestReach();
  return (
    <>
      <p>
        {t('agentAccess.tenantReach.off')}{' '}
        <Link href={ACCESS_HREF} className="font-semibold underline">
          {t('agentAccess.tenantReach.seeEntries')}
        </Link>
      </p>
      <p className="mt-2 text-meta text-muted">{t('agentAccess.tenantReach.offHint')}</p>
      {ask.isError ? <ProblemAlert error={ask.error} codes={refusals(t)} /> : null}
      <ButtonBar>
        <Button disabled={ask.isPending} onClick={() => ask.mutate(undefined, { onSuccess: () => onDone('asked') })}>
          {t('agentAccess.tenantReach.ask')}
        </Button>
      </ButtonBar>
      <p className="mt-2 text-right text-meta text-muted">{t('agentAccess.tenantReach.askHint')}</p>
    </>
  );
}

function On({ reach, onDone }: { reach: TenantReach; onDone: (done: Done) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const off = useSwitchOffReach();
  const [confirming, setConfirming] = useState(false);
  const since = reach.changedAt ? formatDateTime(reach.changedAt, ctx) : null;
  return (
    <>
      <p>
        {since !== null ? (reach.changedBy ? t('agentAccess.tenantReach.on', { date: since, name: reach.changedBy.name }) : t('agentAccess.tenantReach.onSince', { date: since })) : null}{' '}
        <Link href={ACCESS_HREF} className="font-semibold underline">
          {t('agentAccess.tenantReach.seeEntries')}
        </Link>
      </p>
      <p className="mt-2 text-meta text-muted">{t('agentAccess.tenantReach.onHint')}</p>
      <ButtonBar>
        <Button variant="danger" onClick={() => setConfirming(true)}>
          {t('agentAccess.tenantReach.switchOff')}
        </Button>
      </ButtonBar>
      {confirming ? (
        <Modal open onOpenChange={(next) => (next ? undefined : setConfirming(false))} title={t('agentAccess.tenantReach.offTitle')} description={t('agentAccess.tenantReach.offBody')}>
          {off.isError ? <ProblemAlert error={off.error} codes={refusals(t)} /> : null}
          <ButtonBar>
            <Button variant="outline" disabled={off.isPending} onClick={() => setConfirming(false)}>
              {t('agentAccess.tenantReach.keepOn')}
            </Button>
            <Button
              variant="danger"
              disabled={off.isPending}
              onClick={() =>
                off.mutate(undefined, {
                  onSuccess: () => {
                    setConfirming(false);
                    onDone('switchedOff');
                  },
                })
              }
            >
              {t('agentAccess.tenantReach.switchOff')}
            </Button>
          </ButtonBar>
          <p className="mt-2 text-right text-meta text-muted">{t('agentAccess.tenantReach.offStepUp')}</p>
        </Modal>
      ) : null}
    </>
  );
}

function Reach() {
  const t = useT();
  const reach = useTenantReach(true);
  // Who is looking decides what a pending request offers, so the panel waits for the session.
  const { me } = useSession();
  const [done, setDone] = useState<Done | null>(null);
  const [fourEyes, setFourEyes] = useState(false);

  if (fourEyes) {
    return (
      <Panel title={t('agentAccess.tenantReach.fourEyesTitle')} role="alert" data-reach-four-eyes="">
        <p>{t('agentAccess.tenantReach.fourEyesBody')}</p>
        <ButtonBar>
          <Button onClick={() => setFourEyes(false)}>{t('agentAccess.tenantReach.back')}</Button>
        </ButtonBar>
      </Panel>
    );
  }

  const pending = reach.data?.pending ?? null;
  return (
    <Panel title={t('agentAccess.tenantReach.title')} data-tenant-reach={reach.data === undefined ? undefined : reach.data.enabled ? 'on' : pending !== null ? 'pending' : 'off'}>
      {done !== null ? <StatusLine tone="positive">{t(DONE_KEY[done])}</StatusLine> : null}
      {reach.isPending || me === null ? (
        <LoadingState rows={1} />
      ) : reach.isError ? (
        <ErrorState title={t('agentAccess.tenantReach.errorTitle')} onRetry={() => void reach.refetch()} />
      ) : reach.data.enabled ? (
        <On reach={reach.data} onDone={setDone} />
      ) : pending !== null ? (
        <Pending request={pending} mine={pending.requestedBy.id === me.user.id} onDone={setDone} onFourEyes={() => setFourEyes(true)} />
      ) : (
        <Off onDone={setDone} />
      )}
    </Panel>
  );
}

export function TenantReachPanel() {
  const t = useT();
  const canManage = (usePermissions() ?? []).includes(SECURITY_MANAGE);
  // The state is read under security.manage too, so without it the panel says
  // who changes it and reads nothing.
  if (!canManage) {
    return (
      <Panel title={t('agentAccess.tenantReach.title')} data-tenant-reach="read-only">
        <p className="text-muted">{t('agentAccess.tenantReach.readOnly', { permission: humanisePermission(SECURITY_MANAGE) })}</p>
      </Panel>
    );
  }
  return <Reach />;
}
