'use client';

import type { UseQueryResult } from '@tanstack/react-query';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { DiffText } from '@/components/inventory/DiffText';
import { ObligationCommentsPanel } from '@/components/inventory/ObligationCommentsPanel';
import { ObligationGapsPanel } from '@/components/inventory/ObligationGapsPanel';
import { ObligationHistoryPanel } from '@/components/inventory/ObligationHistoryPanel';
import { DutyPanel, instrumentHref, ProvenancePanel, RelatedPanel, ScopePanel, VersionsPanel } from '@/components/inventory/ObligationPanels';
import { ObligationParticipantsPanel } from '@/components/inventory/ObligationParticipantsPanel';
import { ObligationPositionPanel } from '@/components/inventory/ObligationPositionPanel';
import { ObligationHandlePanel } from '@/components/inventory/ObligationStatusPanel';
import { ObligationTagsPanel } from '@/components/inventory/ObligationTagsPanel';
import { ObligationUnitsPanel } from '@/components/inventory/ObligationUnitsPanel';
import { RecordProblemReports } from '@/components/inventory/RecordProblemReports';
import { RuleWords } from '@/components/inventory/RuleWords';
import { ObligationRelatedChanges } from '@/components/library/ObligationRelatedChanges';
import { ReportProblemModal } from '@/components/inventory/ReportProblemModal';
import { VersionBar } from '@/components/inventory/VersionBar';
import { Button } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Fold } from '@/components/ui/fold';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel } from '@/components/ui/Panel';
import { Pill } from '@/components/ui/Pill';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useObligation, useObligationDiff, useReportObligationProblem } from '@/features/library/hooks';
import { machineConfirmedLabel, presentObligation, STANDARD_LEVEL_KIND } from '@/features/library/obligation-presentation';
import { summaryMachineLabel } from '@/features/library/rule-words-presentation';
import type { LocalizedText, ObligationDetail, VersionDiff } from '@/features/library/types';
import type { PartialDate } from '@/features/shared/presentation-types';
import { languageName } from '@/features/library/version-presentation';
import { useRecordProblemReports, useRefreshProblemReports } from '@/features/library/problem-reports/hooks';
import { useRegisterEntry } from '@/features/register/hooks';
import { presentComplianceHeader } from '@/features/register/register-presentation';
import type { RegisterEntry } from '@/features/register/types';
import type { Locale, Translate } from '@/shared/i18n';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate, formatPartialDate, type FormatContext } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';

// The obligation page (design/screens/tenant-obligation.html; INV-03..INV-06,
// AC-INV1). Under the head, two texts that are never confused: "In plain
// words", bleqq's own summary of the duty with its versions and diff, and "The
// rule's own words", the cited provisions' verbatim text in the language the
// authority wrote them in. Then five cards, in this order, which stack in the
// same order on a phone: Our position, How we comply, The rule, Source and
// changes, People and discussion. The page reads and never writes the library:
// the one thing a reader can send about it is a problem report, which stays
// inside their own bank (AUD-03). Whether the duty applies to this bank and
// whether the bank complies are the register's separate facts (REG-01 to
// REG-05, REG-08), each drawn by its own part and filled by its own package.

/** Reporting a problem with a library record is everyone's, but it is still a permission. */
const REPORT_PERMISSION = 'problems.report';

/** One language chip: a language the version holds its summary in, plus the reader's own when it holds none. */
export interface LanguageChoice {
  language: string;
  label: string;
  selected: boolean;
  /** False on the reader's own language when this version carries no text in it. */
  hasText: boolean;
}

/**
 * The chips above a text, the regulation page's summary among them (InstrumentScreen).
 * The original carries no label of its own beyond saying it is the original; a
 * machine translation is labelled on the text itself (INV-05).
 */
export function languageChoices(translations: readonly LocalizedText[], selected: string, reader: Locale, t: Translate): LanguageChoice[] {
  return summaryChoices(translations, selected, reader).map((choice) =>
    translations.some((text) => text.isOriginal && text.language === choice.language) ? { ...choice, label: t('library.languageOriginal', { language: choice.label }) } : choice,
  );
}

/**
 * The obligation summary's chips, by language name only: the summary is
 * bleqq's wording, so none of its languages is "the original". A machine
 * translation is labelled on the text itself, where a reader cannot miss it.
 */
export function summaryChoices(translations: readonly LocalizedText[], selected: string, reader: Locale): LanguageChoice[] {
  const choices = translations.map((text) => ({ language: text.language, label: languageName(text.language, reader), selected: text.language === selected, hasText: true }));
  if (!translations.some((text) => text.language === reader)) {
    choices.push({ language: reader, label: languageName(reader, reader), selected: reader === selected, hasText: false });
  }
  return choices;
}

/** The text of one language, or null when the version holds none in it. */
export function textIn(translations: readonly LocalizedText[], language: string): LocalizedText | null {
  return translations.find((text) => text.language === language) ?? null;
}

/** The language bleqq wrote the summary in, which a machine translation names and "Read it in" goes back to. */
export function originalLanguage(translations: readonly LocalizedText[]): string | null {
  return (translations.find((text) => text.isOriginal) ?? translations[0])?.language ?? null;
}

/** A version's effective date in the diff's sentence; a version with none has been in force since the record began. */
export function effectiveIn(date: PartialDate | null, t: Translate, ctx: FormatContext): string {
  if (date === null) return t('inventory.obligation.diffSinceAlways');
  return t('inventory.obligation.diffInForceFrom', { date: formatPartialDate(date.date, date.precision, ctx) });
}

/** "Comparing version 1 (in force since it began) with version 2 (in force from 1 Oct 2026)." */
export function diffSentence(diff: VersionDiff, t: Translate, ctx: FormatContext): string {
  return t('inventory.obligation.diffBanner', {
    from: diff.fromVersion,
    fromDate: effectiveIn(diff.fromEffective, t, ctx),
    to: diff.toVersion,
    toDate: effectiveIn(diff.toEffective, t, ctx),
  });
}

/**
 * The summary's text in its own language, with the machine line above it when
 * a machine translated it. `data-legal-text` is the hook the journeys have
 * always read the summary by; it carries no § margin, which belongs to the
 * law's own words.
 */
function SummaryText({ lang, machineFrom, children }: { lang: string; machineFrom: string | null; children: ReactNode }) {
  const t = useT();
  const locale = useLocale();
  return (
    <div data-legal-text="" className="max-w-[78ch] rounded-card border border-line bg-surface p-4 md:px-6 md:py-5">
      {machineFrom === null ? null : (
        <p data-machine-translation="" className="mb-2 text-meta font-medium text-brass">
          {summaryMachineLabel(machineFrom, locale, t)}
        </p>
      )}
      <div lang={lang} className="leading-[1.375rem]">
        {children}
      </div>
    </div>
  );
}

/** The header pills, the regulation's short name a link to its own page, then the bank's weakest standing when it has one. */
function HeadLine({ record, entry }: { record: ObligationDetail; entry: RegisterEntry | undefined }) {
  const t = useT();
  const pills = presentObligation(
    {
      instrument: { key: record.instrument.key, label: record.instrument.shortName },
      regime: { key: record.regime.key, label: record.regime.label },
      binding: record.binding,
      levelKind: record.bindingLevel.kind,
      privateToUs: record.privateToUs,
    },
    'header',
    t,
  );
  const standing = entry === undefined ? null : presentComplianceHeader(entry, t);
  return (
    <Meta className="mb-1.5">
      <span className="flex flex-wrap items-center gap-1.5" data-header-pills="">
        {pills.map((pill) => {
          const drawn = (
            <Pill key={pill.key} tone={pill.tone} outlined={pill.outlined}>
              {pill.label}
            </Pill>
          );
          return pill.key.startsWith('instrument:') ? (
            <Link key={pill.key} href={instrumentHref(record.instrument.id)} prefetch={false} className="rounded-[10px]" data-instrument-link="">
              {drawn}
            </Link>
          ) : (
            drawn
          );
        })}
      </span>
      {standing === null ? null : (
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1.5" data-status-header="">
          <PillRow pills={[standing.pill]} />
          {standing.weakest === null ? null : <span>{standing.weakest}</span>}
        </span>
      )}
    </Meta>
  );
}

interface PlainWordsProps {
  record: ObligationDetail;
  selected: string;
  onChoose: (language: string) => void;
  asOf: string;
  onAsOf: (asOf: string) => void;
  showDiff: boolean;
  onShowDiff: (show: boolean) => void;
  diff: UseQueryResult<VersionDiff>;
}

/** "In plain words": bleqq's summary, its languages, its versions, "Show what changed" and "As of". */
function PlainWords({ record, selected, onChoose, asOf, onAsOf, showDiff, onShowDiff, diff }: PlainWordsProps) {
  const t = useT();
  const ctx = useFormatContext();
  const locale = useLocale();
  const shown = textIn(record.translations, selected);
  // The newer side of the comparison, when an independent agent confirmed it, says so in the banner (INV-05).
  const diffMachine =
    diff.data === undefined ? null : machineConfirmedLabel(record.versions.find((version) => version.versionNumber === diff.data.toVersion) ?? null, null, t, ctx);
  const writtenIn = originalLanguage(record.translations);

  return (
    <section data-summary="">
      <h2 className="mb-2 microlabel text-muted">{t('inventory.obligation.plainWordsTitle')}</h2>
      <div data-language-chips="">
        <ChipRow className="mb-3">
          {summaryChoices(record.translations, selected, locale).map((choice) => (
            <Chip key={choice.language} pressed={choice.selected} onClick={() => onChoose(choice.language)}>
              {choice.label}
            </Chip>
          ))}
        </ChipRow>
      </div>

      <VersionBar
        versions={record.versions}
        currentVersion={record.version?.versionNumber ?? null}
        asOf={asOf}
        onAsOf={onAsOf}
        showDiff={showDiff}
        onShowDiff={onShowDiff}
      />

      {asOf === '' ? null : (
        <Notice className="flex flex-wrap items-center gap-2" data-as-of={asOf}>
          <span>
            {record.version === null
              ? t('inventory.obligation.asOfNoVersion', { date: formatDate(asOf, ctx) })
              : t('inventory.obligation.asOfBanner', { number: record.version.versionNumber, date: formatDate(asOf, ctx) })}
          </span>
          <Button variant="ghost" size="small" onClick={() => onAsOf('')}>
            {t('inventory.backToToday')}
          </Button>
        </Notice>
      )}

      {showDiff && diff.isError ? <ErrorState title={t('inventory.obligation.diffErrorTitle')} onRetry={() => void diff.refetch()} /> : null}
      {showDiff && diff.data !== undefined ? (
        <>
          <Notice data-diff-banner="">
            {diffSentence(diff.data, t, ctx)}
            {diffMachine === null ? null : (
              <span className="mt-1 block" data-machine-confirmed="">
                {diffMachine}
              </span>
            )}
          </Notice>
          <SummaryText lang={diff.data.language} machineFrom={diff.data.isMachine ? writtenIn : null}>
            <DiffText segments={diff.data.segments} />
          </SummaryText>
        </>
      ) : shown === null ? (
        <EmptyState
          title={t('library.noTextTitle', { language: languageName(selected, locale) })}
          body={t('library.noTextBody')}
          action={writtenIn === null ? undefined : { label: t('inventory.obligation.summaryReadIn', { language: languageName(writtenIn, locale) }), href: '#', onClick: () => onChoose(writtenIn) }}
        />
      ) : (
        <SummaryText lang={shown.language} machineFrom={shown.isMachine ? writtenIn : null}>
          {shown.text}
        </SummaryText>
      )}
    </section>
  );
}

/** "Reported problems", folded with its count, for a reader who may file one. */
function ReportsFold({ obligationId }: { obligationId: string }) {
  const t = useT();
  const allowed = (usePermissions() ?? []).includes(REPORT_PERMISSION);
  const reports = useRecordProblemReports('obligation', obligationId, allowed);
  if (!allowed) return null;
  return (
    <Fold title={t('inventory.reports.title')} count={reports.data?.total} as="h3" className="mt-4">
      <RecordProblemReports subjectType="obligation" subjectId={obligationId} bare />
    </Fold>
  );
}

export function ObligationScreen({ obligationId }: { obligationId: string }) {
  const t = useT();
  const locale = useLocale();
  const permissions = usePermissions() ?? [];
  const [asOf, setAsOf] = useState('');
  const [chosen, setChosen] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [reporting, setReporting] = useState(false);

  const obligation = useObligation(obligationId, asOf);
  const record = obligation.data;
  // The register read carries the first page of every register part below and leaves each
  // where its part reads it, so the parts mount once it has answered and send nothing of their
  // own. Should it fail, they mount anyway and each asks its own route. "Answered once" and
  // not "not pending": a part re-asking a failed read puts it back to pending, and the parts
  // must not unmount and remount over and over while it does.
  const entry = useRegisterEntry(obligationId);
  const panelsRead = entry.isFetched;
  const selected = chosen ?? record?.summary?.language ?? locale;
  const diff = useObligationDiff(obligationId, selected, showDiff);
  const report = useReportObligationProblem(obligationId);
  const refreshReports = useRefreshProblemReports();
  // A report just filed joins the record's "Reported problems" when the form closes.
  const onReporting = (open: boolean) => {
    setReporting(open);
    if (!open) refreshReports();
  };

  if (obligation.isError) {
    if (problemStatus(obligation.error) === 404) return <NotFoundScreen backHref="/inventory" backLabel={t('inventory.obligation.back')} />;
    return <ErrorState title={t('inventory.obligation.errorTitle')} onRetry={() => void obligation.refetch()} />;
  }

  // The record and the register read both start from the id in the address, in one round.
  // The parts drawn from the record wait for it; the rest wait for the register read, which
  // already holds what they show.
  const waiting = <LoadingState rows={2} />;
  return (
    <div data-obligation={record?.stableKey}>
      <BackLink href="/inventory" label={t('inventory.obligation.back')} />
      {record === undefined ? (
        <LoadingState rows={3} />
      ) : (
        <>
          <HeadLine record={record} entry={entry.data} />
          <PageHead title={record.title === null ? record.refLabel : record.title.text} />
          <PlainWords
            record={record}
            selected={selected}
            onChoose={setChosen}
            asOf={asOf}
            onAsOf={setAsOf}
            showDiff={showDiff}
            onShowDiff={setShowDiff}
            diff={diff}
          />
          <RuleWords obligation={record} />
        </>
      )}

      <div className="mt-6 grid gap-x-4 lg:grid-cols-2 lg:items-start">
        <div>
          {panelsRead ? (
            <ObligationPositionPanel obligationId={obligationId}>
              {record?.bindingLevel.kind === STANDARD_LEVEL_KIND ? <ObligationUnitsPanel obligationId={obligationId} /> : null}
            </ObligationPositionPanel>
          ) : (
            <Panel title={t('inventory.obligation.card.position')}>{waiting}</Panel>
          )}
          <Panel title={t('inventory.obligation.card.comply')} data-comply-card="">
            {panelsRead ? (
              <>
                <ObligationHistoryPanel obligationId={obligationId} />
                <ObligationHandlePanel obligationId={obligationId} />
                <ObligationGapsPanel obligationId={obligationId} />
              </>
            ) : (
              waiting
            )}
          </Panel>
        </div>
        <div>
          <Panel title={t('inventory.obligation.card.rule')} data-rule-card="">
            {record === undefined ? (
              waiting
            ) : (
              <>
                <ScopePanel obligation={record} />
                <DutyPanel obligation={record} />
              </>
            )}
            {/* Mounted from the start: it draws once the record is here, and its list of tags is asked beside the record, not after it. */}
            <ObligationTagsPanel obligationId={obligationId} />
          </Panel>
          <Panel title={t('inventory.obligation.card.source')} data-source-card="">
            {record === undefined ? (
              waiting
            ) : (
              <ProvenancePanel
                obligation={record}
                actions={
                  permissions.includes(REPORT_PERMISSION) ? (
                    <Button variant="outline" size="small" className="mt-4" onClick={() => setReporting(true)}>
                      {t('inventory.obligation.reportProblem')}
                    </Button>
                  ) : undefined
                }
              />
            )}
            {panelsRead ? <ObligationRelatedChanges obligationId={obligationId} /> : null}
            {record === undefined ? null : (
              <>
                <VersionsPanel versions={record.versions} />
                <RelatedPanel related={record.related} />
              </>
            )}
            {panelsRead ? <ReportsFold obligationId={obligationId} /> : null}
          </Panel>
          {/* Participants and comments are shared cards; inside this one they lose their own frame and read as its parts. */}
          <Panel
            title={t('inventory.obligation.card.people')}
            className="[&>section]:m-0 [&>section]:rounded-none [&>section]:border-x-0 [&>section]:border-b-0 [&>section]:bg-transparent [&>section]:px-0 [&>section]:pb-0 [&>section+section]:mt-4 [&>section>h2]:text-body [&>section>h2]:font-semibold [&>section:first-of-type]:border-t-0 [&>section:first-of-type]:pt-0"
            data-people-card=""
          >
            {panelsRead ? (
              <>
                <ObligationParticipantsPanel obligationId={obligationId} />
                <ObligationCommentsPanel obligationId={obligationId} />
              </>
            ) : (
              waiting
            )}
          </Panel>
        </div>
      </div>

      {record === undefined ? null : (
        <ReportProblemModal
          open={reporting}
          onOpenChange={onReporting}
          context={{ language: selected, ...(record.version === null ? {} : { versionNumber: record.version.versionNumber }) }}
          report={report}
        />
      )}
    </div>
  );
}
