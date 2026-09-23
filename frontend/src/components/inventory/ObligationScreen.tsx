'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { DiffText } from '@/components/inventory/DiffText';
import { LegalText } from '@/components/inventory/LegalText';
import { DutyPanel, PendingPanels, ProvenancePanel, RelatedPanel, ScopePanel, VersionsPanel } from '@/components/inventory/ObligationPanels';
import { ReportProblemModal, type ReportContext } from '@/components/inventory/ReportProblemModal';
import { VersionBar } from '@/components/inventory/VersionBar';
import { Button } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useObligation, useObligationDiff, useReportObligationProblem } from '@/features/library/hooks';
import { machineConfirmedLabel, presentObligation } from '@/features/library/obligation-presentation';
import type { LocalizedText, ObligationDetail, VersionDiff } from '@/features/library/types';
import type { PartialDate } from '@/features/shared/presentation-types';
import { languageName } from '@/features/library/version-presentation';
import type { Locale, Translate } from '@/shared/i18n';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate, formatPartialDate, type FormatContext } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';

// The obligation card (design/screens/tenant-obligation.html; INV-03..INV-06,
// AC-INV1). It reads and never writes the library: the one thing a reader can
// send from here is a problem report, which stays inside their own bank.
// Nothing on it says the duty applies to this bank or that the bank complies
// with it — those are the register's separate facts, and the panel that will
// hold them says so until chunk 8 fills it.

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
 * The chips above the text. The original carries no label of its own beyond
 * saying it is the original; a machine translation is labelled on the text
 * itself, where a reader cannot miss it (INV-05).
 */
export function languageChoices(translations: readonly LocalizedText[], selected: string, reader: Locale, t: Translate): LanguageChoice[] {
  const choices = translations.map((text) => ({
    language: text.language,
    label: text.isOriginal ? t('library.languageOriginal', { language: languageName(text.language, reader) }) : languageName(text.language, reader),
    selected: text.language === selected,
    hasText: true,
  }));
  if (!translations.some((text) => text.language === reader)) {
    choices.push({ language: reader, label: languageName(reader, reader), selected: reader === selected, hasText: false });
  }
  return choices;
}

/** The text of one language, or null when the version holds none in it. */
export function textIn(translations: readonly LocalizedText[], language: string): LocalizedText | null {
  return translations.find((text) => text.language === language) ?? null;
}

/** The language of the original, which is what "Show the original" goes back to. */
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

function Reference({ obligation }: { obligation: ObligationDetail }) {
  return (
    <>
      {obligation.instrument.officialRef}
      <br />
      {obligation.refLabel}
    </>
  );
}

export function ObligationScreen({ obligationId }: { obligationId: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const locale = useLocale();
  const permissions = usePermissions() ?? [];
  const [asOf, setAsOf] = useState('');
  const [chosen, setChosen] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [reporting, setReporting] = useState(false);

  const obligation = useObligation(obligationId, asOf);
  const record = obligation.data;
  const selected = chosen ?? record?.summary?.language ?? locale;
  const diff = useObligationDiff(obligationId, selected, showDiff);
  const report = useReportObligationProblem(obligationId);

  if (obligation.isError) {
    if (problemStatus(obligation.error) === 404) return <NotFoundScreen backHref="/inventory" backLabel={t('inventory.obligation.back')} />;
    return <ErrorState title={t('inventory.obligation.errorTitle')} onRetry={() => void obligation.refetch()} />;
  }
  if (record === undefined) return <LoadingState rows={3} />;

  const header = presentObligation(
    {
      instrument: { key: record.instrument.key, label: record.instrument.shortName },
      regime: { key: record.regime.key, label: record.regime.label },
      binding: record.binding,
      levelKind: record.bindingLevel.kind,
    },
    'header',
    t,
  );
  const shown = textIn(record.translations, selected);
  // The newer side of the comparison, when an independent agent confirmed it, says so in the banner (INV-05).
  const diffMachine =
    diff.data === undefined ? null : machineConfirmedLabel(record.versions.find((version) => version.versionNumber === diff.data.toVersion) ?? null, null, t, ctx);
  const original = originalLanguage(record.translations);
  const context: ReportContext = { language: selected, ...(record.version === null ? {} : { versionNumber: record.version.versionNumber }) };

  return (
    <div data-obligation={record.stableKey}>
      <BackLink href="/inventory" label={t('inventory.obligation.back')} />
      <div className="mb-1.5" data-header-pills="">
        <PillRow pills={header} />
      </div>
      <PageHead title={record.title === null ? record.refLabel : record.title.text} />

      <div data-language-chips="">
        <ChipRow className="mb-3">
          {languageChoices(record.translations, selected, locale, t).map((choice) => (
            <Chip key={choice.language} pressed={choice.selected} onClick={() => setChosen(choice.language)}>
              {choice.label}
            </Chip>
          ))}
        </ChipRow>
      </div>

      <VersionBar
        versions={record.versions}
        currentVersion={record.version?.versionNumber ?? null}
        asOf={asOf}
        onAsOf={setAsOf}
        showDiff={showDiff}
        onShowDiff={setShowDiff}
      />

      {asOf === '' ? null : (
        <Notice className="flex flex-wrap items-center gap-2" data-as-of={asOf}>
          <span>
            {record.version === null
              ? t('inventory.obligation.asOfNoVersion', { date: formatDate(asOf, ctx) })
              : t('inventory.obligation.asOfBanner', { number: record.version.versionNumber, date: formatDate(asOf, ctx) })}
          </span>
          <Button variant="ghost" size="small" onClick={() => setAsOf('')}>
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
          <LegalText lang={diff.data.language} translatedFrom={diff.data.isMachine && original !== null ? original : undefined} reference={<Reference obligation={record} />}>
            <DiffText segments={diff.data.segments} />
          </LegalText>
        </>
      ) : shown === null ? (
        <EmptyState
          title={t('library.noTextTitle', { language: languageName(selected, locale) })}
          body={t('library.noTextBody')}
          action={original === null ? undefined : { label: t('library.showOriginal'), href: '#', onClick: () => setChosen(original) }}
        />
      ) : (
        <LegalText lang={shown.language} translatedFrom={shown.isMachine && original !== null ? original : undefined} reference={<Reference obligation={record} />}>
          {shown.text}
        </LegalText>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <ScopePanel obligation={record} />
          <DutyPanel obligation={record} />
          <VersionsPanel versions={record.versions} />
          <RelatedPanel related={record.related} />
        </div>
        <div>
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
          <PendingPanels />
        </div>
      </div>

      <ReportProblemModal open={reporting} onOpenChange={setReporting} context={context} report={report} />
    </div>
  );
}
