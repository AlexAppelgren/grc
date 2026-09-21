'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { ProposalCorrectionForm } from '@/components/console/ProposalCorrectionForm';
import { RejectProposalDialog } from '@/components/console/RejectProposalDialog';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen, ProblemAlert } from '@/components/ui/States';
import { SwatchPair } from '@/components/ui/Swatch';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useApproveProposal, useProposal, useScopeTermLabels } from '@/features/proposals/hooks';
import {
  fieldSourceLabel,
  fieldSourceRows,
  isMineOf,
  isObligationVersion,
  isVocabularyKind,
  obligationPayloadOf,
  presentProposal,
  proposerLine,
  scopeTermPills,
  vocabularyPayloadOf,
} from '@/features/proposals/proposal-presentation';
import type { ProposalRow } from '@/features/proposals/types';
import { languageName } from '@/features/library/version-presentation';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { listLabel, presentVocabularyValue } from '@/features/vocabularies/vocabulary-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDate, formatDateTime } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// /console/queue/[proposalId] (design/screens/console-queue.html; PRO-01,
// PRO-02, PRO-03, AC-PRO2). The source sits beside "What changes" so a
// reviewer never approves without the excerpt in view; the proposer never
// approves their own proposal, and the screen replaces Approve with the
// four-eyes notice rather than hiding why the control is unavailable — the
// server still refuses it (409 four_eyes_violation) if it is ever called.
//
// GET /proposals/{id} answers the plain `ProposalRow`: no target title,
// reference or instrument short name, and no sentence diff against the
// obligation's current wording (chunk4-T10's enrichment and chunk 3's
// obligation-diff read are not on `main`). "What changes" therefore shows the
// proposed text plainly rather than as a diff; a console session has no
// tenant, so there is no "Open the obligation" link to a tenant-scoped page.

function SourcePanel({ proposal }: { proposal: ProposalRow }) {
  const t = useT();
  const ctx = useFormatContext();
  const rows = fieldSourceRows(proposal.fieldSources ?? {});
  return (
    <Panel title={t('console.queue.detail.sourcePanel')}>
      {proposal.sourceLabel !== '' ? (
        <p className="mb-2 flex flex-wrap items-center gap-x-1.5">
          <span>{proposal.sourceLabel}</span>
          {proposal.sourceUrl !== '' ? (
            <a href={proposal.sourceUrl} target="_blank" rel="noopener noreferrer" className="underline">
              {t('console.queue.detail.openSource')}
            </a>
          ) : null}
        </p>
      ) : null}
      {rows.length > 0 ? (
        <dl className="grid grid-cols-1 gap-x-3.5 gap-y-2 text-meta md:grid-cols-[140px_1fr]">
          {rows.map(({ field, url }) => (
            <div key={field} className="contents">
              <dt className="text-muted">{fieldSourceLabel(field, (code) => languageName(code, ctx.locale), t)}</dt>
              <dd className="m-0">
                <a href={url} target="_blank" rel="noopener noreferrer" className="underline">
                  {url}
                </a>
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </Panel>
  );
}

function ObligationChanges({ proposal }: { proposal: ProposalRow }) {
  const t = useT();
  const ctx = useFormatContext();
  const payload = obligationPayloadOf(proposal);
  const terms = payload?.terms ?? null;
  const { labelOf } = useScopeTermLabels(terms ?? []);
  if (payload === null) return null;
  return (
    <Panel title={t('console.queue.detail.whatChanges')} data-proposal-changes="">
      <p className="microlabel mb-1 text-muted">{t('console.queue.detail.proposedText')}</p>
      <div className="grid gap-3">
        {Object.entries(payload.summaries).map(([language, text]) => (
          <div key={language} lang={language} className="rounded-card border border-line bg-surface-2 p-3">
            <p className="mb-1 text-meta text-muted">
              {languageName(language, ctx.locale)}
              {language === payload.originalLanguage ? ` (${t('console.queue.detail.original')})` : ''}
            </p>
            <p>{text}</p>
          </div>
        ))}
      </div>
      <dl className="mt-3 grid grid-cols-1 gap-x-3.5 gap-y-2 md:grid-cols-[140px_1fr]">
        <dt className="text-meta text-muted">{t('console.queue.detail.effectiveDate')}</dt>
        <dd className="m-0">{payload.effectiveFrom ? formatDate(payload.effectiveFrom, ctx) : t('common.never')}</dd>
        <dt className="text-meta text-muted">{t('console.queue.detail.scope')}</dt>
        <dd className="m-0">{terms === null ? t('console.queue.detail.scopeUnchanged') : <PillRow pills={scopeTermPills(terms, labelOf)} />}</dd>
      </dl>
    </Panel>
  );
}

function VocabularyChanges({ proposal }: { proposal: ProposalRow }) {
  const t = useT();
  const payload = vocabularyPayloadOf(proposal);
  const list = payload.list ?? payload.dimension ?? '';
  const values = useVocabularyValues(list, true, list !== '');
  const current = values.data?.find((row) => row.key === payload.key);
  return (
    <Panel title={t('console.queue.detail.whatChanges')} data-proposal-changes="">
      <dl className="grid grid-cols-1 gap-x-3.5 gap-y-2 md:grid-cols-[140px_1fr]">
        <dt className="text-meta text-muted">{t('console.queue.detail.vocabulary.list')}</dt>
        <dd className="m-0">{list === '' ? '' : listLabel(list, t)}</dd>
        <dt className="text-meta text-muted">{t('console.queue.detail.vocabulary.key')}</dt>
        <dd className="m-0 font-mono">{payload.key}</dd>
        {current !== undefined ? (
          <>
            <dt className="text-meta text-muted">{t('console.queue.detail.vocabulary.before')}</dt>
            <dd className="m-0">
              <SwatchPair>
                <PillRow pills={[presentVocabularyValue(list, current)]} />
              </SwatchPair>
            </dd>
          </>
        ) : null}
        {payload.labels !== undefined && Object.keys(payload.labels).length > 0 ? (
          <>
            <dt className="text-meta text-muted">{t('console.queue.detail.vocabulary.after')}</dt>
            <dd className="m-0">
              <SwatchPair>
                <PillRow pills={[presentVocabularyValue(list, { key: payload.key ?? '', kind: current?.kind ?? null, label: payload.labels.en ?? current?.label ?? '', extra: current?.extra ?? {} })]} />
              </SwatchPair>
            </dd>
          </>
        ) : null}
        {payload.into !== undefined && payload.into !== '' ? (
          <>
            <dt className="text-meta text-muted">{t('console.queue.detail.vocabulary.after')}</dt>
            <dd className="m-0">{t('console.queue.detail.vocabulary.mergeInto', { label: payload.into })}</dd>
          </>
        ) : null}
      </dl>
    </Panel>
  );
}

function DecisionPanel({ proposal, mine }: { proposal: ProposalRow; mine: boolean }) {
  const t = useT();
  const ctx = useFormatContext();

  if (proposal.status === 'approved') {
    return (
      <Notice data-proposal-applied="">
        {typeof proposal.appliedAt === 'string' ? t('console.queue.detail.appliedBy', { date: formatDateTime(proposal.appliedAt, ctx), reviewer: proposal.reviewedBy?.name ?? '' }) : null}
        {proposal.reviewNote !== '' ? <span className="mt-1 block">{t('console.queue.detail.reviewNote', { note: proposal.reviewNote })}</span> : null}
      </Notice>
    );
  }
  if (proposal.status === 'rejected') {
    return (
      <Notice data-proposal-rejected="">
        {typeof proposal.reviewedAt === 'string'
          ? t('console.queue.detail.rejectedBy', { date: formatDateTime(proposal.reviewedAt, ctx), reviewer: proposal.reviewedBy?.name ?? '', note: proposal.reviewNote })
          : null}
      </Notice>
    );
  }
  if (proposal.status === 'superseded') return null;

  if (mine) {
    return (
      <Notice tone="bad" data-proposal-four-eyes="">
        <b>{t('console.queue.detail.fourEyes.title')}</b> {t('console.queue.detail.fourEyes.body')}
      </Notice>
    );
  }

  // Only an obligation version may be corrected (backend/apps/proposals/logic.py
  // `corrected`): a vocabulary row's label is wording a person writes, not a fact to
  // correct against a source, so those kinds offer a plain Approve and Reject instead.
  if (isObligationVersion(proposal.kind)) {
    return <ProposalCorrectionForm proposal={proposal} />;
  }
  return <SimpleDecisionActions proposal={proposal} />;
}

/** Approve or reject, no correction fields: the vocabulary kinds (PRO-01). */
function SimpleDecisionActions({ proposal }: { proposal: ProposalRow }) {
  const t = useT();
  const approve = useApproveProposal(proposal.id);
  const [rejecting, setRejecting] = useState(false);

  return (
    <div data-proposal-decision="">
      {approve.isError ? <ProblemAlert error={approve.error} /> : null}
      <ButtonBar>
        <Button variant="danger" disabled={approve.isPending} onClick={() => setRejecting(true)}>
          {t('console.queue.reject')}
        </Button>
        <Button disabled={approve.isPending} onClick={() => approve.mutate({ note: '' })}>
          {t('console.queue.approve')}
        </Button>
      </ButtonBar>
      <p className="mt-1.5 text-right text-meta text-muted">{t('console.queue.approveHint')}</p>
      <RejectProposalDialog proposalId={proposal.id} open={rejecting} onClose={() => setRejecting(false)} />
    </div>
  );
}

export function ProposalDetailScreen({ proposalId }: { proposalId: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const { me } = useSession();
  const query = useProposal(proposalId);
  const forbidden = forbiddenFrom(query.error);

  if (query.isPending) return <LoadingState rows={3} />;
  if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  if (hasProblemCode(query.error, 'not_found')) {
    return <NotFoundScreen body={t('console.queue.detail.notFoundBody')} backHref="/console/queue" backLabel={t('console.queue.detail.back')} />;
  }
  if (query.isError) return <ErrorState title={t('console.queue.detail.errorTitle')} onRetry={() => void query.refetch()} />;

  const proposal = query.data;
  const mine = isMineOf(proposal, me?.user.id ?? null);
  const pills = presentProposal(proposal, mine, t);

  return (
    <div data-proposal={proposal.id}>
      <BackLink href="/console/queue" label={t('console.queue.detail.back')} />
      <PillRow pills={pills} />
      <h1 className="mt-1.5 mb-1.5">{proposal.title}</h1>
      <p className="mb-4 text-meta text-muted">{t('console.queue.detail.proposedBy', { proposer: proposerLine(proposal, t), date: formatDateTime(proposal.createdAt, ctx) })}</p>

      <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
        <SourcePanel proposal={proposal} />
        {isObligationVersion(proposal.kind) ? <ObligationChanges proposal={proposal} /> : isVocabularyKind(proposal.kind) ? <VocabularyChanges proposal={proposal} /> : null}
      </div>

      <DecisionPanel proposal={proposal} mine={mine} />
    </div>
  );
}
