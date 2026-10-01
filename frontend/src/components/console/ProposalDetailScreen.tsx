'use client';

import { useState, type ReactNode } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { ProposalCorrectionForm } from '@/components/console/ProposalCorrectionForm';
import { RejectProposalDialog } from '@/components/console/RejectProposalDialog';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen, ProblemAlert } from '@/components/ui/States';
import { SwatchPair } from '@/components/ui/Swatch';
import { useJurisdictions } from '@/features/footprint/hooks';
import { useFormatContext } from '@/features/identity/hooks';
import { useApproveProposal, useProposal, useScopeTermLabels } from '@/features/proposals/hooks';
import {
  agentCorrectionLine,
  bindingLabel,
  decisionLine,
  decisionNoteLine,
  fieldSourceLabel,
  fieldSourceRows,
  instrumentPayloadOf,
  isObligationVersion,
  isVocabularyKind,
  labelOfKey,
  languageTexts,
  newObligationPayloadOf,
  obligationPayloadOf,
  precisionOf,
  presentProposal,
  proposerLine,
  scopeTermPills,
  vocabularyPayloadOf,
} from '@/features/proposals/proposal-presentation';
import type { ProposalDetail, ProposalRow } from '@/features/proposals/types';
import { languageName } from '@/features/library/version-presentation';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { listLabel, presentVocabularyValue } from '@/features/vocabularies/vocabulary-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';
import { externalHref } from '@/shared/utils/external-href';
import { formatDate, formatDateTime, formatPartialDate } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// /console/queue/[proposalId] (design/screens/console-queue.html; PRO-01,
// PRO-02, PRO-03, AC-PRO2). The source sits beside "What changes" so a
// reviewer never approves without the excerpt in view; the proposer never
// approves their own proposal, and the screen replaces Approve with the
// four-eyes notice rather than hiding why the control is unavailable — the
// server still refuses it (409 four_eyes_violation) if it is ever called.
// Whether the reader filed it is the server's own `isMine`. An agent that
// decided or corrected it is named as an agent, never in a person's slot.
//
// "What changes" shows the proposed text plainly; a console session has no
// tenant, so there is no "Open the obligation" link to a tenant-scoped page.

function SourcePanel({ proposal }: { proposal: ProposalRow }) {
  const t = useT();
  const ctx = useFormatContext();
  const rows = fieldSourceRows(proposal.fieldSources ?? {});
  return (
    <Panel title={t('console.queue.detail.sourcePanel')} data-proposal-sources="">
      {proposal.sourceLabel !== '' ? (
        <p className="mb-2 flex flex-wrap items-center gap-x-1.5">
          <span>{proposal.sourceLabel}</span>
          {proposal.sourceUrl === '' ? null : externalHref(proposal.sourceUrl) === null ? (
            <span className="break-all">{proposal.sourceUrl}</span>
          ) : (
            <a href={proposal.sourceUrl} target="_blank" rel="noopener noreferrer" className="underline">
              {t('console.queue.detail.openSource')}
            </a>
          )}
        </p>
      ) : null}
      {rows.length > 0 ? (
        <dl className="grid grid-cols-1 gap-x-3.5 gap-y-2 text-meta md:grid-cols-[140px_1fr]">
          {rows.map(({ field, url }) => (
            <div key={field} className="contents">
              <dt className="text-muted">{fieldSourceLabel(field, (code) => languageName(code, ctx.locale), t)}</dt>
              <dd className="m-0">
                <MaybeLink href={url} />
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

/** A text per content language, the original first, each marked as the original or a machine translation (AUD-02). */
function LanguageTextBlocks({ heading, texts, originalLanguage, isMachine, field }: { heading: string; texts: Record<string, string>; originalLanguage: string; isMachine?: boolean; field: string }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <div className="mb-3" data-proposal-fact={field}>
      <p className="microlabel mb-1 text-muted">{heading}</p>
      <div className="grid gap-2">
        {languageTexts(texts, originalLanguage, isMachine).map(({ language, text, mark }) => (
          <div key={language} lang={language} className="rounded-card border border-line bg-surface-2 p-3" data-language={language}>
            <p className="mb-1 text-meta text-muted">
              {mark === 'original'
                ? t('console.queue.detail.languageOriginal', { language: languageName(language, ctx.locale) })
                : mark === 'machine'
                  ? t('console.queue.detail.languageMachine', { language: languageName(language, ctx.locale) })
                  : languageName(language, ctx.locale)}
            </p>
            <p>{text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/** One fact of a new record: its label, in the words the source panel uses, and its value. */
function Fact({ field, label, children }: { field: string; label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-meta text-muted">{label}</dt>
      <dd className="m-0 min-w-0 break-words" data-proposal-fact={field}>
        {children}
      </dd>
    </>
  );
}

const FACTS = 'grid grid-cols-1 gap-x-3.5 gap-y-2 md:grid-cols-[140px_1fr]';

/** An address shown as a link only when it is one (H26); otherwise as plain text. */
function MaybeLink({ href }: { href: string }) {
  return externalHref(href) === null ? (
    <span className="break-all">{href}</span>
  ) : (
    <a href={href} target="_blank" rel="noopener noreferrer" className="break-all underline">
      {href}
    </a>
  );
}

// What a new instrument would add (D-118: the library baseline's first pass). Labels come
// from the reads a console session may make: the level's list, the jurisdictions, the
// regime's terms. The authority is shown by its key: its read, GET /authorities, needs
// `library.read`, which no platform role holds.
function NewInstrumentFacts({ proposal }: { proposal: ProposalRow }) {
  const t = useT();
  const ctx = useFormatContext();
  const payload = instrumentPayloadOf(proposal);
  const levels = useVocabularyValues('instrument_level', true, payload !== null);
  const jurisdictions = useJurisdictions();
  const { labelOf } = useScopeTermLabels(payload === null ? [] : [payload.regime]);
  if (payload === null) return null;
  const eli = payload.eliUri ?? '';
  const implementsNote = payload.implementsNote ?? '';
  return (
    <Panel title={t('console.queue.detail.whatItAdds')} data-proposal-record={proposal.kind}>
      <LanguageTextBlocks heading={t('console.queue.detail.titles')} texts={payload.titles} originalLanguage={payload.originalLanguage} isMachine={payload.isMachine} field="titles" />
      <dl className={FACTS}>
        <Fact field="shortName" label={t('console.queue.field.shortName')}>
          {payload.shortName}
        </Fact>
        <Fact field="officialRef" label={t('console.queue.field.officialRef')}>
          {payload.officialRef}
        </Fact>
        {eli === '' ? null : (
          <Fact field="eliUri" label={t('console.queue.field.eliUri')}>
            <MaybeLink href={eli} />
          </Fact>
        )}
        <Fact field="level" label={t('console.queue.field.level')}>
          {labelOfKey(levels.data, payload.level)}
        </Fact>
        <Fact field="binding" label={t('console.queue.field.binding')}>
          {bindingLabel(payload.binding, t)}
        </Fact>
        <Fact field="jurisdiction" label={t('console.queue.field.jurisdiction')}>
          {labelOfKey(jurisdictions.data, payload.jurisdiction)}
        </Fact>
        <Fact field="authority" label={t('console.queue.field.authority')}>
          {payload.authority ?? t('console.queue.detail.notSet')}
        </Fact>
        <Fact field="regime" label={t('console.queue.field.regime')}>
          {labelOf(payload.regime)}
        </Fact>
        <Fact field="inForceFrom" label={t('console.queue.field.inForceFrom')}>
          {payload.inForceFrom ? formatPartialDate(payload.inForceFrom, precisionOf(payload.inForceFromPrecision), ctx) : t('console.queue.detail.notSet')}
        </Fact>
        <Fact field="inForceTo" label={t('console.queue.field.inForceTo')}>
          {payload.inForceTo ? formatPartialDate(payload.inForceTo, precisionOf(payload.inForceToPrecision), ctx) : t('console.queue.detail.noEnd')}
        </Fact>
        {implementsNote === '' ? null : (
          <Fact field="implementsNote" label={t('console.queue.field.implementsNote')}>
            {implementsNote}
          </Fact>
        )}
      </dl>
    </Panel>
  );
}

// What a new obligation would add (D-118: each duty once its instrument is approved). Its
// instrument is named by the key the payload carries and by the short name the library
// holds under it, which the detail read answers (`instrumentShortName`).
function NewObligationFacts({ proposal }: { proposal: ProposalDetail }) {
  const t = useT();
  const ctx = useFormatContext();
  const payload = newObligationPayloadOf(proposal);
  const dutyTypes = useVocabularyValues('duty_type', true, payload !== null);
  const terms = payload?.terms ?? [];
  const { labelOf } = useScopeTermLabels(terms);
  if (payload === null) return null;
  return (
    <Panel title={t('console.queue.detail.whatItAdds')} data-proposal-record={proposal.kind}>
      <dl className={cn(FACTS, 'mb-3')}>
        <Fact field="instrument" label={t('console.queue.field.instrument')}>
          {proposal.instrumentShortName === '' ? null : <span className="mr-2">{proposal.instrumentShortName}</span>}
          <span className="font-mono text-meta text-muted">{payload.instrument}</span>
          {proposal.instrumentShortName === '' ? <span className="block text-meta text-muted">{t('console.queue.detail.instrumentNotHeld')}</span> : null}
        </Fact>
      </dl>
      <LanguageTextBlocks heading={t('console.queue.detail.titles')} texts={payload.titles} originalLanguage={payload.originalLanguage} isMachine={payload.isMachine} field="titles" />
      <LanguageTextBlocks heading={t('console.queue.detail.summaries')} texts={payload.summaries} originalLanguage={payload.originalLanguage} isMachine={payload.isMachine} field="summaries" />
      <dl className={FACTS}>
        <Fact field="refLabel" label={t('console.queue.field.refLabel')}>
          {payload.refLabel}
        </Fact>
        <Fact field="dutyType" label={t('console.queue.field.dutyType')}>
          {labelOfKey(dutyTypes.data, payload.dutyType)}
        </Fact>
        <Fact field="effectiveFrom" label={t('console.queue.field.effectiveFrom')}>
          {payload.effectiveFrom ? formatPartialDate(payload.effectiveFrom, precisionOf(payload.effectiveFromPrecision), ctx) : t('console.queue.detail.sinceDutyBegan')}
        </Fact>
        <Fact field="terms" label={t('console.queue.field.scope')}>
          {terms.length === 0 ? t('console.queue.detail.noTerms') : <PillRow pills={scopeTermPills(terms, labelOf)} />}
        </Fact>
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

function DecisionPanel({ proposal }: { proposal: ProposalDetail }) {
  const t = useT();
  const ctx = useFormatContext();

  if (proposal.status === 'approved' || proposal.status === 'rejected') {
    const decision = decisionLine(proposal, (iso) => formatDateTime(iso, ctx), t);
    const correction = proposal.status === 'approved' ? agentCorrectionLine(proposal, t) : null;
    const note = decisionNoteLine(proposal, t);
    return (
      <Notice {...(proposal.status === 'approved' ? { 'data-proposal-applied': '' } : { 'data-proposal-rejected': '' })}>
        {decision}
        {correction !== null ? (
          <span className="mt-1 block" data-proposal-corrected-by-agent="">
            {correction}
          </span>
        ) : null}
        {note !== null ? <span className="mt-1 block">{note}</span> : null}
      </Notice>
    );
  }
  if (proposal.status === 'superseded') return null;

  if (proposal.isMine === true) {
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
  const query = useProposal(proposalId);
  const forbidden = forbiddenFrom(query.error);

  if (query.isPending) return <LoadingState rows={3} />;
  if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  if (hasProblemCode(query.error, 'not_found')) {
    return <NotFoundScreen body={t('console.queue.detail.notFoundBody')} backHref="/console/queue" backLabel={t('console.queue.detail.back')} />;
  }
  if (query.isError) return <ErrorState title={t('console.queue.detail.errorTitle')} onRetry={() => void query.refetch()} />;

  const proposal = query.data;
  const pills = presentProposal(proposal, t);

  return (
    <div data-proposal={proposal.id}>
      <BackLink href="/console/queue" label={t('console.queue.detail.back')} />
      <PillRow pills={pills} />
      <h1 className="mt-1.5 mb-1.5">{proposal.title}</h1>
      <p className="mb-4 text-meta text-muted">{t('console.queue.detail.proposedBy', { proposer: proposerLine(proposal, t), date: formatDateTime(proposal.createdAt, ctx) })}</p>
      {(proposal.riskFlags ?? []).length > 0 ? (
        <Notice tone="warn" data-proposal-flagged="">
          {t('console.queue.detail.flagged')}
        </Notice>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
        <SourcePanel proposal={proposal} />
        {isObligationVersion(proposal.kind) ? (
          <ObligationChanges proposal={proposal} />
        ) : isVocabularyKind(proposal.kind) ? (
          <VocabularyChanges proposal={proposal} />
        ) : proposal.kind === 'new_instrument' ? (
          <NewInstrumentFacts proposal={proposal} />
        ) : proposal.kind === 'new_obligation' ? (
          <NewObligationFacts proposal={proposal} />
        ) : null}
      </div>

      <DecisionPanel proposal={proposal} />
    </div>
  );
}
