'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { DutyPanel, PendingPanels, ProvenancePanel, RelatedPanel, ScopePanel, VersionsPanel } from '@/components/inventory/ObligationPanels';
import { LegalText } from '@/components/inventory/LegalText';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen } from '@/components/ui/States';
import { useObligation } from '@/features/library/hooks';
import { presentObligation } from '@/features/library/obligation-presentation';
import type { LocalizedText, ObligationDetail } from '@/features/library/types';
import { languageName } from '@/features/library/version-presentation';
import type { Locale, Translate } from '@/shared/i18n';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { problemStatus } from '@/shared/utils/problem';

// The obligation card (design/screens/tenant-obligation.html; INV-03, INV-05,
// INV-06). It reads and never writes: the library changes only through an
// approved proposal. Nothing on it says the duty applies to this bank or that
// the bank complies with it — those are the register's separate facts, and
// the panel that will hold them says so until chunk 8 fills it.

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

function SummaryBlock({ obligation }: { obligation: ObligationDetail }) {
  const t = useT();
  const locale = useLocale();
  const [chosen, setChosen] = useState<string | null>(null);
  const selected = chosen ?? obligation.summary?.language ?? locale;
  const shown = textIn(obligation.translations, selected);
  const original = originalLanguage(obligation.translations);

  return (
    <>
      <div data-language-chips="">
        <ChipRow className="mb-3">
          {languageChoices(obligation.translations, selected, locale, t).map((choice) => (
            <Chip key={choice.language} pressed={choice.selected} onClick={() => setChosen(choice.language)}>
              {choice.label}
            </Chip>
          ))}
        </ChipRow>
      </div>
      {shown === null ? (
        <EmptyState
          title={t('library.noTextTitle', { language: languageName(selected, locale) })}
          body={t('library.noTextBody')}
          action={original === null ? undefined : { label: t('library.showOriginal'), href: '#', onClick: () => setChosen(original) }}
        />
      ) : (
        <LegalText
          lang={shown.language}
          translatedFrom={shown.isMachine && original !== null ? original : undefined}
          reference={
            <>
              {obligation.instrument.officialRef}
              <br />
              {obligation.refLabel}
            </>
          }
        >
          {shown.text}
        </LegalText>
      )}
    </>
  );
}

export function ObligationScreen({ obligationId }: { obligationId: string }) {
  const t = useT();
  const obligation = useObligation(obligationId);

  if (obligation.isError) {
    if (problemStatus(obligation.error) === 404) return <NotFoundScreen backHref="/inventory" backLabel={t('inventory.obligation.back')} />;
    return <ErrorState title={t('inventory.obligation.errorTitle')} onRetry={() => void obligation.refetch()} />;
  }
  if (obligation.data === undefined) return <LoadingState rows={3} />;

  const record = obligation.data;
  const header = presentObligation(
    {
      instrument: { key: record.instrument.key, label: record.instrument.shortName },
      regime: record.regime === null ? undefined : { key: record.regime.key, label: record.regime.label },
      binding: record.binding,
    },
    'header',
    t,
  );

  return (
    <div data-obligation={record.stableKey}>
      <BackLink href="/inventory" label={t('inventory.obligation.back')} />
      <div className="mb-1.5" data-header-pills="">
        <PillRow pills={header} />
      </div>
      <PageHead title={record.title === null ? record.refLabel : record.title.text} />

      <SummaryBlock obligation={record} />

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <ScopePanel obligation={record} />
          <DutyPanel obligation={record} />
          <VersionsPanel versions={record.versions} />
          <RelatedPanel related={record.related} />
        </div>
        <div>
          <ProvenancePanel obligation={record} />
          <PendingPanels />
        </div>
      </div>
    </div>
  );
}
