'use client';

import { useRef, useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen, ProblemAlert } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { externalHref } from '@/shared/utils/external-href';
import { formatDateTime } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

import { useApprovePrivateProposal, usePrivateProposal, useRejectPrivateProposal } from './hooks';
import { payloadRows, presentPrivateProposal, proposerLine, sourceHost, sourcesOf } from './private-record-presentation';
import type { PrivateProposalRow } from './types';

// /private-records/[proposalId] (design/screens/tenant-private-records.html states 4 to 14;
// OWN-03, PRO-03, INV-07). The agent's draft sits under the "Drafted by our agent" callout
// until a person here decides it, and each field beside the numbered source it came from.
// There are no corrections: approve what was proposed, behind the passkey step-up the API
// client runs on a 403 `step_up_required`, or reject it with a reason. The proposer never
// decides: the server's `isMine` replaces the buttons with the four-eyes notice, and the
// server's 409 `four_eyes_violation` reads the same. Another bank's proposal and an
// address that does not exist render the shared Not found, which never says a record exists.

const BACK = '/private-records';

function SourcesPanel({ proposal }: { proposal: PrivateProposalRow }) {
  const t = useT();
  const sources = sourcesOf(proposal);
  return (
    <Panel title={t('privateRecords.sources')} data-private-sources="">
      {sources.length === 0 ? <p className="text-muted">{t('privateRecords.sources.none')}</p> : null}
      <ol className="grid gap-2">
        {sources.map((url, index) => {
          const host = sourceHost(url);
          return (
            <li key={url} className="flex gap-2 rounded-control border border-line bg-subtle px-3 py-2.5">
              <span className="font-semibold">{index + 1}</span>
              {externalHref(url) === null ? (
                <span className="break-all">{url}</span>
              ) : (
                <a href={url} target="_blank" rel="noopener noreferrer" className="break-all underline">
                  {host ?? url}
                </a>
              )}
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}

function AddsPanel({ proposal }: { proposal: PrivateProposalRow }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Panel title={t('privateRecords.adds')} data-private-adds="">
      <dl className="grid grid-cols-1 gap-x-4 gap-y-2 md:grid-cols-[150px_1fr]">
        {payloadRows(proposal, t, ctx).map((row) => (
          <div key={row.field} className="contents" data-field={row.field}>
            <dt className="text-muted">{row.label}</dt>
            <dd className="m-0 mb-2 min-w-0 md:mb-0">
              <span lang={row.language}>{row.value}</span>
              {row.source !== null ? <span className="ml-2 text-meta whitespace-nowrap text-muted">{t('privateRecords.sourceNumber', { number: row.source })}</span> : null}
            </dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function RejectDialog({ proposal, open, onClose, onRejected }: { proposal: PrivateProposalRow; open: boolean; onClose: () => void; onRejected: () => void }) {
  const t = useT();
  const reasons = useVocabularyValues('rejection_reason', false, open);
  const reject = useRejectPrivateProposal(proposal.id);
  const [reasonKey, setReasonKey] = useState('');
  const [note, setNote] = useState('');
  const [tried, setTried] = useState(false);

  const close = () => {
    reject.reset();
    setReasonKey('');
    setNote('');
    setTried(false);
    onClose();
  };
  const missing = reasonKey === '' || note.trim() === '';
  const submit = () => {
    setTried(true);
    if (missing) return;
    reject.mutate({ rejectionCode: reasonKey, note: note.trim() }, { onSuccess: onRejected });
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : close())} title={t('privateRecords.reject.title')}>
      <Field id="private-reject-reason" label={t('privateRecords.reject.reason')}>
        <Select id="private-reject-reason" value={reasonKey} aria-required="true" aria-invalid={tried && reasonKey === ''} onChange={(e) => setReasonKey(e.target.value)}>
          <option value="">{t('privateRecords.reject.reasonPlaceholder')}</option>
          {(reasons.data ?? []).map((reason) => (
            <option key={reason.key} value={reason.key}>
              {reason.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field
        id="private-reject-note"
        label={t('privateRecords.reject.note')}
        hint={t('privateRecords.reject.hint')}
        error={tried && missing ? t('privateRecords.reject.required') : undefined}
      >
        <TextArea id="private-reject-note" aria-required="true" aria-invalid={tried && note.trim() === ''} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {reject.isError ? <ProblemAlert error={reject.error} /> : null}
      <ButtonBar>
        <Button variant="outline" onClick={close} disabled={reject.isPending}>
          {t('common.cancel')}
        </Button>
        <Button variant="danger" disabled={reject.isPending} onClick={submit}>
          {t('privateRecords.reject')}
        </Button>
      </ButtonBar>
    </Modal>
  );
}

function Decision({ proposal, onReload }: { proposal: PrivateProposalRow; onReload: () => void }) {
  const t = useT();
  const approve = useApprovePrivateProposal(proposal.id);
  const [confirming, setConfirming] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [done, setDone] = useState<'approved' | 'rejected' | null>(null);
  const status = useRef<HTMLParagraphElement>(null);
  const announce = (outcome: 'approved' | 'rejected') => {
    setDone(outcome);
    // Focus moves to the status line once it renders (state 7).
    requestAnimationFrame(() => status.current?.focus());
  };

  if (done !== null) {
    return (
      <p ref={status} role="status" tabIndex={-1} className="mt-4 font-medium" data-private-decided={done}>
        {t(done === 'approved' ? 'privateRecords.approved' : 'privateRecords.rejected')}
      </p>
    );
  }
  if (proposal.status !== 'open') return null;
  if (proposal.isMine) {
    return (
      <Notice tone="bad" className="mt-4" data-private-four-eyes="">
        {t('privateRecords.fourEyes')}
      </Notice>
    );
  }
  const refusals = { four_eyes_violation: t('privateRecords.fourEyes'), invalid_transition: t('privateRecords.decidedFirst') };
  return (
    <div className="mt-4" data-private-decision="">
      {approve.isError ? <ProblemAlert error={approve.error} codes={refusals} /> : null}
      {hasProblemCode(approve.error, 'invalid_transition') ? (
        <button type="button" className="text-meta underline" onClick={onReload}>
          {t('privateRecords.reload')}
        </button>
      ) : null}
      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
        <span className="text-meta text-muted">{t('privateRecords.approveHint')}</span>
        <ButtonBar className="mt-0">
          <Button variant="danger" disabled={approve.isPending} onClick={() => setRejecting(true)}>
            {t('privateRecords.reject')}
          </Button>
          <Button disabled={approve.isPending} onClick={() => setConfirming(true)}>
            {t('privateRecords.approve')}
          </Button>
        </ButtonBar>
      </div>
      <Modal open={confirming} onOpenChange={setConfirming} title={t('privateRecords.approve.title', { title: proposal.title })} description={t('privateRecords.approve.body')}>
        <ButtonBar>
          <Button variant="outline" onClick={() => setConfirming(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={approve.isPending}
            onClick={() => {
              setConfirming(false);
              approve.mutate({ note: '' }, { onSuccess: () => announce('approved') });
            }}
          >
            {t('privateRecords.approve.submit')}
          </Button>
        </ButtonBar>
      </Modal>
      <RejectDialog
        proposal={proposal}
        open={rejecting}
        onClose={() => setRejecting(false)}
        onRejected={() => {
          setRejecting(false);
          announce('rejected');
        }}
      />
    </div>
  );
}

export function PrivateProposalScreen({ proposalId }: { proposalId: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const query = usePrivateProposal(proposalId);
  const forbidden = forbiddenFrom(query.error);

  if (query.isPending) return <LoadingState rows={3} />;
  if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  if (query.data === null || hasProblemCode(query.error, 'not_found')) {
    return <NotFoundScreen body={t('privateRecords.notFoundBody')} backHref={BACK} backLabel={t('privateRecords.back')} />;
  }
  if (query.isError) return <ErrorState title={t('privateRecords.loadError')} onRetry={() => void query.refetch()} />;

  const proposal = query.data;
  const proposer = proposerLine(proposal, t);
  const host = sourceHost(proposal.sourceUrl ?? '');
  return (
    <div data-private-proposal={proposal.id}>
      <BackLink href={BACK} label={t('privateRecords.back')} />
      <PillRow pills={presentPrivateProposal(proposal, t)} />
      <h1 className="mt-1.5 mb-1">{proposal.title}</h1>
      <p className="mb-4 flex flex-wrap gap-x-3 gap-y-1 text-meta text-muted">
        {proposer !== null ? <span>{proposer}</span> : null}
        <span>{formatDateTime(proposal.createdAt, ctx)}</span>
        {host !== null ? <span>{t('privateRecords.source', { host })}</span> : null}
      </p>
      {/* AI output stays labelled until a person here approves it. */}
      {proposal.origin === 'agent' && proposal.status !== 'approved' ? (
        <div className="mb-4 rounded-card bg-sand px-3.5 py-3" data-private-drafted="">
          <span className="microlabel block text-brass">{t('privateRecords.drafted.label')}</span>
          <p>{t('privateRecords.drafted.body')}</p>
        </div>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
        <SourcesPanel proposal={proposal} />
        <AddsPanel proposal={proposal} />
      </div>
      <Decision proposal={proposal} onReload={() => void query.refetch()} />
    </div>
  );
}
