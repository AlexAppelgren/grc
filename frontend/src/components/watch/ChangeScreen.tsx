'use client';

import { BackLink } from '@/components/admin/AdminGate';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen } from '@/components/ui/States';
import { ChangeDocuments } from '@/components/watch/ChangeDocuments';
import { ChangeObligations } from '@/components/watch/ChangeObligations';
import { ChangeTimeline } from '@/components/watch/ChangeTimeline';
import { SoWhatPanel } from '@/components/watch/SoWhatPanel';
import { useFormatContext } from '@/features/identity/hooks';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { ChangeDetail } from '@/features/watch/api';
import { CHANGE_SLOT_ORDER, caseStatusLabel, presentChange, urgencyOf, type ChangeFacts } from '@/features/watch/change-presentation';
import { useChange } from '@/features/watch/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDate, formatPartialDate, type DatePrecision, type FormatContext } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// /watch/[changeId] (design/screens/tenant-change.html; WAT-02, WAT-03,
// WAT-04, INV-06, FP-03). The reform's sourced facts — its header, what
// happened, how it was classified, its timeline, the pages it was found on
// and the duties it affects. The bank's own "So what?" is the panel beside
// "What happened"; triage, assessment, actions, evidence and sign-off are
// the case workflow and arrive with chunk 9.
//
// Nothing here writes. A change's type, flags and scope are library facts
// that only a library editor settles, so this screen shows what an agent put
// forward and offers a reader of this bank no control that would confirm it.

/**
 * The facts the header's pills are made of, in the card's slot order.
 *
 * The urgency is this bank's own where it has a case and the library's
 * suggestion otherwise, exactly as a feed row reads it. `suggested` marks the
 * record: a change a run registered carries a type no person has stood behind
 * (`origin` is `agent`), which is the rule the feed read applies to the type
 * too.
 *
 * Each flag and each scope term now arrives with its own `confidence` and
 * `suggested` beside the vocabulary row, as a feed row has always carried
 * them. The header still shows one marker for the record, because the pill
 * card gives the slot one pill; marking an individual flag or term as a
 * suggestion is a change to that card and to the classification block, not to
 * this mapping.
 */
export function detailFacts(change: ChangeDetail, t: Translate): ChangeFacts {
  const urgency = urgencyOf(change.case === null ? change.suggestedUrgency : (change.case.urgency ?? change.suggestedUrgency));
  return {
    type: { key: change.changeType.key, label: change.changeType.label },
    ...(urgency === null ? {} : { urgency }),
    flags: change.flags.map((flag) => ({ key: flag.ref.key, label: flag.ref.label })),
    suggested: change.origin === 'agent',
    ...(change.case === null ? {} : { workflowStatus: { key: change.case.category, label: caseStatusLabel(change.case.category, t) } }),
  };
}

export function presentChangeDetail(change: ChangeDetail, t: Translate): PresentedPill[] {
  return presentChange(detailFacts(change, t), 'header', t);
}

/** The scope block: one pill per term, tone by the slot. An empty list means no restriction. */
export function presentScopeTerms(change: ChangeDetail): PresentedPill[] {
  return change.terms.map((term, index) => ({
    key: `term:${term.ref.key}`,
    label: term.ref.label,
    tone: slotTone.scopeTerm,
    order: CHANGE_SLOT_ORDER.libraryTags + index,
  }));
}

/** The plain meta text under the title: who issued it, when, how it reached us, and whether it is ours to read. */
export function headMeta(change: ChangeDetail, t: Translate, ctx: FormatContext): string[] {
  const meta = [change.authorityLabel];
  if (change.publishedOn !== null) {
    const date = formatPartialDate(change.publishedOn, (change.publishedPrecision ?? 'day') as DatePrecision, ctx);
    meta.push(t('watch.change.published', { date }));
  }
  if (change.duplicateCount > 0) meta.push(t('watch.row.duplicatesMerged', { count: change.duplicateCount }));
  if (change.model !== null) meta.push(t('watch.change.foundBy', { agent: change.model, date: formatDate(change.firstSeenAt, ctx) }));
  if (!change.inFootprint) meta.push(t('watch.row.outside'));
  return meta;
}

export function ChangeScreen({ changeId }: { changeId: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const query = useChange(changeId);
  const forbidden = forbiddenFrom(query.error);

  if (query.isPending) return <LoadingState rows={3} />;
  if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  // A change that is not there and a change this bank may not see answer the
  // same 404 on purpose, so the screen says the same thing to both.
  if (hasProblemCode(query.error, 'not_found')) {
    return <NotFoundScreen body={t('watch.change.notFoundBody')} backHref="/watch" backLabel={t('watch.change.backToWatch')} />;
  }
  if (query.isError) return <ErrorState title={t('watch.change.errorTitle')} onRetry={() => void query.refetch()} />;

  const change = query.data;
  // One fixed moment for the whole render, so two timeline entries can never
  // disagree about how many days are left.
  const today = new Date();
  // The header's pills are the one presentation of this record; the
  // classification panel shows the same pills slot by slot rather than
  // choosing a second set of tones for them.
  const pills = presentChangeDetail(change, t);
  const slot = (prefix: string) => pills.filter((pill) => pill.key.startsWith(prefix));
  const urgencySuggested = change.case === null || !change.case.urgencyConfirmed;

  return (
    <div data-change={change.stableKey}>
      <BackLink href="/watch" label={t('watch.change.back')} />
      <PillRow pills={pills} />
      <h1 className="mt-1.5 mb-1.5">{change.title}</h1>
      <p className="mb-4 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-muted">
        {headMeta(change, t, ctx).map((line, index) => (
          // Two facts can read the same, so the position is the key.
          <span key={index}>{line}</span>
        ))}
        <a href={change.sourceUrl} rel="noopener noreferrer" target="_blank" className="underline">
          {t('watch.change.source', { source: change.sourceLabel })}
        </a>
      </p>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr] lg:items-start">
        <div>
          <Panel title={t('watch.change.whatHappened')}>
            <p className="max-w-[70ch]">{change.summary}</p>
            <SoWhatPanel change={change} />
          </Panel>

          <Panel title={t('watch.change.classification')} data-change-classification="">
            <p className="mb-2 text-meta text-muted">{t('watch.change.classificationHint')}</p>
            <dl className="grid grid-cols-1 gap-x-3.5 gap-y-2.5 md:grid-cols-[150px_1fr]">
              <dt className="text-meta text-muted">{t('watch.change.changeType')}</dt>
              <dd className="m-0 flex flex-wrap items-center gap-1.5">
                <PillRow pills={slot('type:')} />
                {change.origin === 'agent' ? <span className="text-meta text-muted">{t('watch.change.suggested')}</span> : null}
              </dd>
              <dt className="text-meta text-muted">{t('watch.change.urgency')}</dt>
              <dd className="m-0 flex flex-wrap items-center gap-1.5">
                <PillRow pills={slot('urgency:')} />
                {urgencySuggested ? <span className="text-meta text-muted">{t('watch.change.suggested')}</span> : null}
              </dd>
              <dt className="text-meta text-muted">{t('watch.change.flags')}</dt>
              <dd className="m-0">
                <PillRow pills={slot('flag:')} />
              </dd>
              <dt className="text-meta text-muted">{t('watch.change.scope')}</dt>
              <dd className="m-0">
                {change.terms.length === 0 ? (
                  <span className="text-meta text-muted">{t('scope.notSpecific')}</span>
                ) : (
                  <PillRow pills={presentScopeTerms(change)} />
                )}
              </dd>
            </dl>
          </Panel>

          <Panel title={t('watch.change.obligations')}>
            <ChangeObligations obligations={change.obligations} />
          </Panel>
        </div>

        <div>
          <Panel title={t('watch.change.timeline')}>
            <ChangeTimeline events={change.events} today={today} />
          </Panel>
          <Panel title={t('watch.change.documents')}>
            <ChangeDocuments documents={change.documents} />
          </Panel>
          <Panel title={t('watch.change.record')}>
            <dl className="grid grid-cols-1 gap-x-3.5 gap-y-2.5 md:grid-cols-[120px_1fr]">
              <dt className="text-meta text-muted">{t('watch.change.stableKey')}</dt>
              <dd className="m-0">
                <code className="font-mono text-meta">{change.stableKey}</code>
              </dd>
              <dt className="text-meta text-muted">{t('watch.change.registered')}</dt>
              <dd className="m-0 text-meta">{formatDate(change.firstSeenAt, ctx)}</dd>
            </dl>
          </Panel>
        </div>
      </div>
    </div>
  );
}
