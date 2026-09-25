'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ProblemAlert } from '@/components/ui/States';
import { GAPS_EDIT, gapActions, gapKind, gapProblemCopy, ownerName, statusKeyOf, waitingPill } from '@/features/gaps/gap-view';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { isStaleWrite, useApproveRiskAcceptance, useReloadRegister, useReopenGap, useRequestRiskAcceptance, useUpdateGap } from '@/features/register/hooks';
import type { RegisterGap } from '@/features/register/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';

// "Way out" on a gap record (design/screens/tenant-gaps.html, states 5 to 12;
// REG-03, REG-S5, REG-S6): start the fix and close it, or ask someone else to
// accept the risk. Asking takes a reason from the bank's own list and moves no
// status; approving needs a second person holding risk.accept.approve and a
// passkey step-up, which the API client prompts for when the server asks.
// The requester sees no Approve; any refusal the server gives renders from its
// code, above the buttons, where it happened.

type Dialog = 'close' | 'accept' | 'approve' | 'reopen' | null;

function AcceptRiskDialog({ gap, onClose, onDone }: { gap: RegisterGap; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const reasons = useVocabularyValues('risk_acceptance_reason');
  const request = useRequestRiskAcceptance();
  const [reason, setReason] = useState('');
  const [tried, setTried] = useState(false);
  const error = tried && reason === '' ? t('gaps.acceptDialog.reasonRequired') : undefined;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (reason === '') return;
    request.mutate({ gapId: gap.id, body: { reason } }, { onSuccess: onDone });
  };

  return (
    <Modal open onOpenChange={(open) => (open ? undefined : onClose())} title={t('gaps.acceptDialog.title')} description={t('gaps.acceptDialog.body')}>
      <form onSubmit={submit} noValidate aria-busy={request.isPending} data-accept-risk-form="">
        <Field id="gap-accept-reason" label={t('gaps.acceptDialog.reason')} error={error}>
          <Select id="gap-accept-reason" value={reason} aria-invalid={error !== undefined} aria-describedby={error === undefined ? undefined : 'gap-accept-reason-error'} onChange={(e) => setReason(e.target.value)}>
            <option value="">{t('gaps.acceptDialog.choose')}</option>
            {(reasons.data ?? []).map((row) => (
              <option key={row.key} value={row.key}>
                {row.label}
              </option>
            ))}
          </Select>
        </Field>
        <p className="text-meta text-muted">{t('gaps.acceptDialog.hint')}</p>
        {request.isError ? <ProblemAlert error={request.error} codes={gapProblemCopy(t)} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={request.isPending}>
            {t('gaps.acceptDialog.send')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

function ConfirmDialog({ title, body, action, busy, onConfirm, onClose }: { title: string; body: string; action: string; busy: boolean; onConfirm: () => void; onClose: () => void }) {
  const t = useT();
  return (
    <Modal open onOpenChange={(open) => (open ? undefined : onClose())} title={title} description={body}>
      <ButtonBar>
        <Button variant="outline" onClick={onClose}>
          {t('common.cancel')}
        </Button>
        <Button disabled={busy} onClick={onConfirm}>
          {action}
        </Button>
      </ButtonBar>
    </Modal>
  );
}

export function GapAcceptancePanel({ gap, onDone }: { gap: RegisterGap; onDone: (message: MessageKey) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const meId = useSession().me?.user.id ?? null;
  const permissions = usePermissions() ?? [];
  const actions = gapActions(gap, meId, permissions);
  const statuses = useVocabularyValues('gap_status', false, actions.startRemediation || actions.close);
  const move = useUpdateGap();
  const approve = useApproveRiskAcceptance();
  const reopen = useReopenGap();
  const reload = useReloadRegister();
  const [dialog, setDialog] = useState<Dialog>(null);
  const kind = gapKind(gap);
  const acceptance = gap.riskAcceptance;
  const owner = ownerName(gap, t);

  const done = (message: MessageKey) => () => {
    setDialog(null);
    onDone(message);
  };
  const moveTo = (target: 'remediating' | 'closed', message: MessageKey) => {
    const status = statusKeyOf(statuses.data ?? [], target);
    if (status !== null) move.mutate({ gapId: gap.id, body: { status }, version: gap.version }, { onSuccess: done(message), onError: () => setDialog(null) });
  };
  const failed = [move, approve, reopen].find((write) => write.isError);

  let lead: string;
  if (acceptance !== null && acceptance.approvedBy !== null && acceptance.approvedAt !== null && kind === 'risk_accepted') {
    lead = t('gaps.way.accepted', { approver: acceptance.approvedBy.name, date: formatDate(acceptance.approvedAt, ctx), requester: acceptance.requestedBy.name });
  } else if (kind === 'closed' || kind === 'risk_accepted') {
    lead = t('gaps.way.closed');
  } else if (acceptance !== null) {
    const date = formatDate(acceptance.requestedAt, ctx);
    lead = actions.ownRequest ? t('gaps.way.youAsked', { date }) : t('gaps.way.theyAsk', { name: acceptance.requestedBy.name, date });
  } else if (permissions.includes(GAPS_EDIT)) {
    lead = t(kind === 'open' ? 'gaps.way.open' : 'gaps.way.remediating');
  } else {
    lead = t(kind === 'open' ? 'gaps.way.readOpen' : 'gaps.way.readRemediating', { owner });
  }
  const waiting = acceptance !== null && acceptance.approvedBy === null && (kind === 'open' || kind === 'remediating');

  return (
    <Panel title={t('gaps.way.title')} data-gap-way-out={kind} data-waiting={waiting ? '' : undefined}>
      <p className="flex flex-wrap items-center gap-2">
        {waiting ? <PillRow pills={[waitingPill(t)]} /> : null}
        <span>{lead}</span>
      </p>
      {acceptance !== null && (waiting || kind === 'risk_accepted') ? (
        <div className="mt-2 rounded-control bg-subtle px-3 py-2.5" data-acceptance-reason={acceptance.reason.key}>
          <b className="block text-meta font-medium text-muted">{t('gaps.way.reason')}</b>
          {acceptance.reason.label}
        </div>
      ) : null}
      {actions.ownRequest ? (
        <Notice tone="bad" className="mt-3 mb-0" data-own-request="">
          {t('gaps.way.ownRequest')}
        </Notice>
      ) : null}
      {failed === undefined ? null : (
        <div data-gap-problem="">
          <ProblemAlert error={failed.error} codes={gapProblemCopy(t, failed === approve)} />
          {isStaleWrite(failed.error) ? (
            <Button variant="ghost" size="small" className="mt-1" onClick={() => void reload()}>
              {t('gaps.reload')}
            </Button>
          ) : null}
        </div>
      )}
      <ButtonBar>
        {actions.acceptRisk ? (
          <Button variant="outline" onClick={() => setDialog('accept')}>
            {t('gaps.way.acceptRisk')}
          </Button>
        ) : null}
        {actions.startRemediation ? (
          <Button disabled={move.isPending || statuses.isPending} onClick={() => moveTo('remediating', 'gaps.done.remediating')}>
            {t('gaps.way.startRemediation')}
          </Button>
        ) : null}
        {actions.close ? (
          <Button disabled={statuses.isPending} onClick={() => setDialog('close')}>
            {t('gaps.way.close')}
          </Button>
        ) : null}
        {actions.approve ? <Button onClick={() => setDialog('approve')}>{t('gaps.way.approve')}</Button> : null}
        {actions.reopen ? (
          <Button variant="outline" onClick={() => setDialog('reopen')}>
            {t('gaps.way.reopen')}
          </Button>
        ) : null}
      </ButtonBar>
      {dialog === 'accept' ? <AcceptRiskDialog gap={gap} onClose={() => setDialog(null)} onDone={done('gaps.done.requested')} /> : null}
      {dialog === 'close' ? (
        <ConfirmDialog
          title={t('gaps.closeDialog.title')}
          body={t('gaps.closeDialog.body')}
          action={t('gaps.way.close')}
          busy={move.isPending}
          onConfirm={() => moveTo('closed', 'gaps.done.closed')}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === 'approve' ? (
        <ConfirmDialog
          title={t('gaps.approveDialog.title', { title: gap.title })}
          body={t('gaps.approveDialog.body')}
          action={t('gaps.way.approve')}
          busy={approve.isPending}
          onConfirm={() => approve.mutate(gap.id, { onSuccess: done('gaps.done.accepted'), onError: () => setDialog(null) })}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === 'reopen' ? (
        <ConfirmDialog
          title={t('gaps.reopenDialog.title')}
          body={t('gaps.reopenDialog.body')}
          action={t('gaps.way.reopen')}
          busy={reopen.isPending}
          onConfirm={() => reopen.mutate(gap.id, { onSuccess: done('gaps.done.reopened'), onError: () => setDialog(null) })}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </Panel>
  );
}
