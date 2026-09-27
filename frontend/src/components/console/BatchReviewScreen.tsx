'use client';

import { useMemo, useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { BatchPreviewTable } from '@/components/console/BatchPreviewTable';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen, ProblemAlert } from '@/components/ui/States';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { batchDecided, batchTally, lastDecision, type RowDraft } from '@/features/proposals/batch-presentation';
import { useDecideProposalBatch, useProposalBatch, useScopeTermLabels } from '@/features/proposals/hooks';
import { presentProposal, proposerLine } from '@/features/proposals/proposal-presentation';
import type { ProposalBatch } from '@/features/proposals/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDateTime } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// /console/queue/batches/[batchId] (design/screens/console-queue-batch.html; PRO-04,
// ADM-02). A batch is one proposal with a row per record: four eyes, the rejection
// reason and the audit row are the queue's own. Rows are decided here as drafts and
// sent in one call with "Approve the rest" (the drafts, then every undecided row
// approved) or "Reject all" (one reason, nothing changes); both ask for a passkey,
// which the client's step-up handler supplies when the server answers
// `step_up_required`. The person who filed the batch sees the four-eyes notice
// instead of any decision; the server still refuses them (409 four_eyes_violation),
// as it refuses whoever asked for the re-tag, and that refusal renders in place.

const QUEUE = '/console/queue';

function About({ batch }: { batch: ProposalBatch }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Panel aria-label={t('console.batch.about')} className="mb-4">
      <dl className="grid grid-cols-1 gap-x-3.5 gap-y-2 md:grid-cols-[140px_1fr]">
        <dt className="text-meta text-muted">{t('console.batch.askedBy')}</dt>
        <dd className="m-0">{t('console.batch.askedByValue', { proposer: proposerLine(batch, t), date: formatDateTime(batch.createdAt, ctx) })}</dd>
        {batch.sourceLabel !== '' || batch.sourceUrl !== '' ? (
          <>
            <dt className="text-meta text-muted">{t('console.batch.source')}</dt>
            <dd className="m-0 break-words">
              {batch.sourceUrl !== '' ? (
                <a href={batch.sourceUrl} target="_blank" rel="noopener noreferrer" className="underline">
                  {batch.sourceLabel !== '' ? batch.sourceLabel : batch.sourceUrl}
                </a>
              ) : (
                batch.sourceLabel
              )}
            </dd>
          </>
        ) : null}
        <dt className="text-meta text-muted">{t('console.batch.records')}</dt>
        <dd className="m-0">{t('console.batch.recordCount', { count: batch.rowCount ?? (batch.rows ?? []).length })}</dd>
      </dl>
    </Panel>
  );
}

function Result({ batch }: { batch: ProposalBatch }) {
  const t = useT();
  const ctx = useFormatContext();
  const rows = batch.rows ?? [];
  const tally = batchTally(rows, new Map());
  const last = lastDecision(rows);
  const date = typeof last?.decidedAt === 'string' ? formatDateTime(last.decidedAt, ctx) : null;
  const reviewer = last?.decidedBy?.name ?? '';
  return (
    <Panel role="status" data-batch-result="" className="mb-4">
      <h2 className="mb-1 text-title">{t('console.batch.result.title', { changed: tally.approved, unchanged: tally.rejected })}</h2>
      {date !== null ? (
        <p className="text-meta text-muted">{reviewer !== '' ? t('console.batch.result.decidedBy', { reviewer, date }) : t('console.batch.result.decided', { date })}</p>
      ) : null}
    </Panel>
  );
}

function Decide({ batch, drafts, onDecided }: { batch: ProposalBatch; drafts: ReadonlyMap<string, RowDraft>; onDecided: () => void }) {
  const t = useT();
  const decide = useDecideProposalBatch(batch.id);
  const reasons = useVocabularyValues('rejection_reason');
  const [rejectingAll, setRejectingAll] = useState(false);
  const [reason, setReason] = useState('');
  const rows = batch.rows ?? [];
  const tally = batchTally(rows, drafts);
  // A stale row cannot be approved, so "the rest" cannot include one left undecided.
  const staleLeft = rows.some((row) => row.decision === 'pending' && row.stale === true && !drafts.has(row.id));
  const codes = { four_eyes_violation: t('console.batch.problem.fourEyes'), stale_write: t('console.batch.problem.stale') };

  const approveRest = () =>
    decide.mutate(
      { rows: [...drafts.entries()].map(([rowId, draft]) => ({ rowId, decision: draft.decision, rejectionCode: draft.rejectionCode })), rest: 'approved', restRejectionCode: '', note: '' },
      { onSuccess: onDecided },
    );
  const rejectAll = () =>
    decide.mutate(
      { rows: [], rest: 'rejected', restRejectionCode: reason, note: '' },
      {
        onSuccess: () => {
          setRejectingAll(false);
          onDecided();
        },
      },
    );

  return (
    <div className="sticky bottom-0 mt-4 rounded-card border border-line bg-surface px-4 py-3" data-batch-decision="">
      <p role="status" className="flex flex-wrap gap-x-3 text-meta text-muted">
        <span>{t('console.batch.tally.approved', { count: tally.approved })}</span>
        <span>{t('console.batch.tally.rejected', { count: tally.rejected })}</span>
        <span>{t('console.batch.tally.pending', { count: tally.pending })}</span>
      </p>
      {rejectingAll ? null : <ProblemAlert error={decide.error} codes={codes} />}
      {staleLeft ? <p className="mt-2 text-meta text-muted">{t('console.batch.problem.stale')}</p> : null}
      <ButtonBar className="mt-3">
        <Button variant="danger" disabled={decide.isPending} onClick={() => setRejectingAll(true)}>
          {t('console.batch.rejectAll')}
        </Button>
        <Button disabled={decide.isPending || staleLeft} onClick={approveRest}>
          {t('console.batch.approveRest')}
        </Button>
      </ButtonBar>
      <p className="mt-1.5 text-right text-meta text-muted">{t('console.batch.approveHint')}</p>
      <Modal
        open={rejectingAll}
        onOpenChange={(open) => {
          if (open) return;
          decide.reset();
          setRejectingAll(false);
        }}
        title={t('console.batch.rejectAllDialog.title', { count: rows.length })}
        description={t('console.batch.rejectAllDialog.body')}
      >
        <Field id="batch-reject-all-reason" label={t('console.batch.row.reason')}>
          <Select id="batch-reject-all-reason" value={reason} onChange={(event) => setReason(event.target.value)}>
            <option value="">{t('console.batch.row.reasonPlaceholder')}</option>
            {(reasons.data ?? []).map((row) => (
              <option key={row.key} value={row.key}>
                {row.label}
              </option>
            ))}
          </Select>
        </Field>
        {rejectingAll ? <ProblemAlert error={decide.error} codes={codes} /> : null}
        <ButtonBar>
          <Button variant="outline" disabled={decide.isPending} onClick={() => setRejectingAll(false)}>
            {t('common.cancel')}
          </Button>
          <Button variant="danger" disabled={reason === '' || decide.isPending} onClick={rejectAll}>
            {t('console.batch.rejectAll')}
          </Button>
        </ButtonBar>
      </Modal>
    </div>
  );
}

export function BatchReviewScreen({ batchId }: { batchId: string }) {
  const t = useT();
  const { me } = useSession();
  const query = useProposalBatch(batchId);
  const reasons = useVocabularyValues('rejection_reason');
  const [drafts, setDrafts] = useState<ReadonlyMap<string, RowDraft>>(new Map());
  const refs = useMemo(() => (query.data?.rows ?? []).flatMap((row) => [...(row.before.terms ?? []), ...(row.after.terms ?? [])]), [query.data]);
  const { labelOf } = useScopeTermLabels(refs);
  const forbidden = forbiddenFrom(query.error);

  if (query.isPending) return <LoadingState rows={3} />;
  if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  if (hasProblemCode(query.error, 'not_found')) return <NotFoundScreen body={t('console.batch.notFoundBody')} backHref={QUEUE} backLabel={t('console.batch.back')} />;
  if (query.isError) return <ErrorState title={t('console.batch.errorTitle')} onRetry={() => void query.refetch()} />;

  const batch = query.data;
  const decided = batchDecided(batch);
  const mine = me !== null && batch.proposedBy?.id === me.user.id;
  const editable = batch.status === 'open' && !decided && !mine;

  const setDraft = (rowId: string, draft: RowDraft | null) =>
    setDrafts((current) => {
      const next = new Map(current);
      if (draft === null) next.delete(rowId);
      else next.set(rowId, draft);
      return next;
    });

  return (
    <div data-batch={batch.id}>
      <BackLink href={QUEUE} label={t('console.batch.back')} />
      <PillRow pills={presentProposal({ ...batch, isMine: mine }, t)} />
      <h1 className="mt-1.5 mb-1.5 break-words">{batch.title}</h1>
      {decided ? null : <p className="mb-4 text-meta text-muted">{t('console.batch.lede')}</p>}
      {(batch.riskFlags ?? []).length > 0 ? <Notice tone="warn">{t('console.queue.detail.flagged')}</Notice> : null}
      {decided ? <Result batch={batch} /> : null}
      {mine && batch.status === 'open' ? (
        <Notice tone="bad" data-batch-four-eyes="">
          <b>{t('console.batch.fourEyes.title')}</b> {t('console.batch.fourEyes.body')}
        </Notice>
      ) : null}
      <About batch={batch} />
      <h2 className="mb-2 text-title">{t('console.batch.preview')}</h2>
      <BatchPreviewTable rows={batch.rows ?? []} drafts={drafts} editable={editable} reasons={reasons.data ?? []} labelOf={labelOf} onDraft={setDraft} />
      {editable ? <Decide batch={batch} drafts={drafts} onDecided={() => setDrafts(new Map())} /> : null}
    </div>
  );
}
