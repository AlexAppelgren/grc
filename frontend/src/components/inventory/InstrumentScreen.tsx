'use client';

import Link from 'next/link';
import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { ObligationsPanel } from '@/components/inventory/InstrumentObligations';
import { Facts, type Fact } from '@/components/inventory/ObligationPanels';
import { languageChoices, originalLanguage, textIn } from '@/components/inventory/ObligationScreen';
import { ProvisionTree } from '@/components/inventory/ProvisionTree';
import { RecordProblemReports } from '@/components/inventory/RecordProblemReports';
import { ReportProblemModal, type ReportContext } from '@/components/inventory/ReportProblemModal';
import { Button } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Fold } from '@/components/ui/fold';
import { Meta, Panel } from '@/components/ui/Panel';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { lineageDirectionOf } from '@/features/library/api';
import { useInstrument, useReportInstrumentProblem } from '@/features/library/hooks';
import { presentInstrument } from '@/features/library/instrument-presentation';
import { markPrivateToUs, presentBindingLevel } from '@/features/library/obligation-presentation';
import type { InstrumentDetail, InstrumentLineageRef, InstrumentLinkRef } from '@/features/library/types';
import { inForceLabel, languageName } from '@/features/library/version-presentation';
import { useRecordProblemReports, useRefreshProblemReports } from '@/features/library/problem-reports/hooks';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { externalHref } from '@/shared/utils/external-href';
import { formatDate } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';

// The instrument card (design/screens/tenant-instrument.html; INV-01, INV-06,
// FP-03). It reads and never writes the library: the one thing a reader can
// send from here is a problem report, which stays inside their own bank,
// and the close of one in its Reported problems section (AUD-03). The
// obligations come first (InstrumentObligations.tsx) and the provision tree
// under them (chunk3-rest-T18); what it is, the identity panel with its
// reported problems, and lineage sit beside them.

/** Reporting a problem with a library record is everyone's, but it is still a permission. */
const REPORT_PERMISSION = 'problems.report';

/** Where Back and Not found lead: the Inventory's Regulations tab. */
const REGULATIONS_HREF = '/inventory?tab=instruments';

/** One heading of the lineage panel: every link of one relation type in one direction. */
interface LineageGroupOf {
  id: string;
  relation: InstrumentLineageRef['relation'];
  direction: 'outgoing' | 'incoming';
  links: InstrumentLineageRef[];
}

/**
 * The lineage grouped by relation type and direction, in the order the read
 * answers them. Relation types are rows an admin may add to, so no pair is
 * hard-coded: every pair the read carries gets its own heading.
 */
function lineageGroups(lineage: readonly InstrumentLineageRef[]): LineageGroupOf[] {
  const groups = new Map<string, LineageGroupOf>();
  for (const link of lineage) {
    const direction = lineageDirectionOf(link);
    const id = `${link.relation.key}:${direction}`;
    const group = groups.get(id) ?? { id, relation: link.relation, direction, links: [] };
    group.links.push(link);
    groups.set(id, group);
  }
  return [...groups.values()];
}

function LineageGroup({ group }: { group: LineageGroupOf }) {
  const t = useT();
  // "Implements" going out; "Amends this instrument" coming in, where the related instrument does the amending.
  const title = t(group.direction === 'outgoing' ? 'inventory.instrument.lineageOutgoing' : 'inventory.instrument.lineageIncoming', { relation: group.relation.label });
  return (
    <div className="mb-3" data-lineage-group={group.id}>
      <h3 className="mb-1.5 font-semibold">{title}</h3>
      <ul className="m-0 grid list-none gap-1.5 p-0 text-meta">
        {group.links.map((link) => (
          <li key={`${group.id}:${link.instrument.key}`} data-lineage-instrument={link.instrument.key}>
            <Link href={`/inventory/instruments/${link.instrument.id}`} prefetch={false} className="font-medium underline">
              {link.instrument.shortName}
            </Link>
            {link.note === '' ? null : <Meta className="mt-0.5">{link.note}</Meta>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** "Lineage": what this instrument implements, elaborates or amends, and what does so to it in turn (INV-01, INV-09). Left out when there is none. */
function LineagePanel({ instrument }: { instrument: InstrumentDetail }) {
  const t = useT();
  const groups = lineageGroups(instrument.lineage);
  if (groups.length === 0 && instrument.implements.length === 0) return null;
  return (
    <Panel title={t('inventory.instrument.lineageTitle')} data-lineage-panel="">
      {instrument.implements.length === 0 ? null : (
        <div className="mb-3" data-implements="">
          <h3 className="mb-1.5 font-semibold">{t('inventory.instrument.implementsTitle')}</h3>
          <InstrumentLinks links={instrument.implements} />
        </div>
      )}
      {groups.map((group) => (
        <LineageGroup key={group.id} group={group} />
      ))}
    </Panel>
  );
}

/** Other instruments by short name and jurisdiction, each opening its own card. */
function InstrumentLinks({ links }: { links: readonly InstrumentLinkRef[] }) {
  return (
    <ul className="m-0 grid list-none gap-1.5 p-0 text-meta">
      {links.map((link) => (
        <li key={link.id} data-instrument-link={link.key}>
          <Link href={`/inventory/instruments/${link.id}`} prefetch={false} className="font-medium underline">
            {link.shortName}
          </Link>
          <span className="ml-2 text-muted">{link.jurisdiction.label}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * "What it is": the instrument in plain words (INV-09), when the library holds a summary, in
 * the language chosen above it. The chips offer every language the summary is held in, the
 * original named as such, and a machine translation says so above its text (INV-05, D-129).
 */
function SummaryPanel({ instrument, selected, onChoose }: { instrument: InstrumentDetail; selected: string; onChoose: (language: string) => void }) {
  const t = useT();
  const locale = useLocale();
  if (instrument.summary === null) return null;
  const shown = textIn(instrument.summaryTranslations, selected);
  const original = originalLanguage(instrument.summaryTranslations);
  return (
    <Panel title={t('inventory.instrument.summaryTitle')} data-summary-panel="">
      <div data-language-chips="">
        <ChipRow className="mb-3">
          {languageChoices(instrument.summaryTranslations, selected, locale, t).map((choice) => (
            <Chip key={choice.language} pressed={choice.selected} onClick={() => onChoose(choice.language)}>
              {choice.label}
            </Chip>
          ))}
        </ChipRow>
      </div>
      {shown === null ? (
        <EmptyState
          title={t('library.noTextTitle', { language: languageName(selected, locale) })}
          body={t('library.noTextBody')}
          action={original === null ? undefined : { label: t('library.showOriginal'), href: '#', onClick: () => onChoose(original) }}
        />
      ) : (
        <>
          {shown.isMachine && original !== null ? (
            <p data-machine-translation="" className="mb-2 text-meta font-medium text-brass">
              {t('legal.machineTranslation', { language: languageName(original, locale) })}
            </p>
          ) : null}
          <p lang={shown.language} className="max-w-[72ch] text-body">
            {shown.text}
          </p>
        </>
      )}
    </Panel>
  );
}

/** The Identity panel: official reference, ELI or "Not available", level, binding, jurisdiction, authority, in force, last verified. */
function IdentityPanel({ instrument, actions }: { instrument: InstrumentDetail; actions?: React.ReactNode }) {
  const t = useT();
  const ctx = useFormatContext();
  const facts: Fact[] = [
    { key: 'ref', label: t('inventory.instrument.officialRefLabel'), value: <span className="font-mono">{instrument.officialRef}</span> },
    { key: 'eli', label: t('inventory.instrument.eliLabel'), value: instrument.eliUri === '' ? t('inventory.instrument.eliNotAvailable') : instrument.eliUri },
    { key: 'level', label: t('inventory.instrument.levelLabel'), value: instrument.level.label },
    { key: 'binding', label: t('inventory.instrument.bindingLabel'), value: presentBindingLevel(instrument.binding, instrument.level.kind, 0, t).label },
    { key: 'jurisdiction', label: t('inventory.instrument.jurisdictionLabel'), value: instrument.jurisdiction.label },
  ];
  if (instrument.authority !== null) {
    facts.push({ key: 'authority', label: t('inventory.instrument.authorityLabel'), value: instrument.authority.name });
  }
  facts.push({ key: 'inForce', label: t('inventory.instrument.inForceLabel'), value: inForceLabel(instrument.inForceFrom, instrument.inForceTo, t, ctx) });
  const verified =
    instrument.lastVerifiedAt === null
      ? t('library.notVerifiedYet')
      : instrument.verifiedBy === null
        ? formatDate(instrument.lastVerifiedAt, ctx)
        : t('library.lastVerifiedBy', { date: formatDate(instrument.lastVerifiedAt, ctx), name: instrument.verifiedBy.name });
  facts.push({ key: 'verified', label: t('inventory.instrument.lastVerifiedLabel'), value: <span data-last-verified="">{verified}</span> });
  return (
    <Panel title={t('inventory.instrument.identityTitle')} data-identity-panel="">
      <Facts facts={facts} />
      {actions}
    </Panel>
  );
}

/**
 * The bank's reports on this regulation, folded under Identity with their count, and left out
 * while there is none: the section is read with the same permission as filing one, which the
 * caller checks, and shares its read with the section inside.
 */
function ReportedProblems({ instrumentId }: { instrumentId: string }) {
  const t = useT();
  const reports = useRecordProblemReports('instrument', instrumentId, true);
  const total = reports.data?.total ?? 0;
  if (total === 0 && !reports.isError) return null;
  return (
    <Fold title={t('inventory.reports.title')} count={reports.data?.total} as="h3" className="mt-4" data-reported-problems="">
      <RecordProblemReports subjectType="instrument" subjectId={instrumentId} bare />
    </Fold>
  );
}

export function InstrumentScreen({ instrumentId }: { instrumentId: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const locale = useLocale();
  const permissions = usePermissions() ?? [];
  const [reporting, setReporting] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);

  const instrument = useInstrument(instrumentId);
  const record = instrument.data;
  const report = useReportInstrumentProblem(instrumentId);
  const refreshReports = useRefreshProblemReports();
  // A report just filed joins the record's "Reported problems" when the form closes.
  const onReporting = (open: boolean) => {
    setReporting(open);
    if (!open) refreshReports();
  };

  if (instrument.isError) {
    if (problemStatus(instrument.error) === 404) return <NotFoundScreen backHref={REGULATIONS_HREF} backLabel={t('inventory.instrument.back')} />;
    return <ErrorState title={t('inventory.instrument.errorTitle')} onRetry={() => void instrument.refetch()} />;
  }
  if (record === undefined) return <LoadingState rows={3} />;

  const pills = presentInstrument(
    {
      instrument: { key: record.stableKey, label: record.shortName },
      level: { key: record.level.key, label: record.level.label },
      levelKind: record.level.kind,
      binding: record.binding,
      jurisdiction: { key: record.jurisdiction.key, label: record.jurisdiction.label },
      regime: { key: record.regime.key, label: record.regime.label },
    },
    t,
  );
  // The short name is the heading, so its pill would only repeat it.
  const facts = pills.filter((pill) => !pill.key.startsWith('instrument:'));
  // The bank's own instrument leads its head with "Private to us", as its obligations do (OWN-04).
  const header = record.privateToUs ? markPrivateToUs(facts, t) : facts;
  // The official name follows the language chosen for the summary, where the library holds it in that one.
  const selected = chosen ?? record.summary?.language ?? locale;
  const name = textIn(record.nameTranslations, selected) ?? record.name;
  const officialTitle = name === null || name.text === record.shortName ? undefined : name.text;
  const nameOriginal = originalLanguage(record.nameTranslations);
  const context: ReportContext = {};
  const sourceHref = externalHref(record.sourceUrl);

  return (
    <div data-instrument={record.stableKey}>
      <BackLink href={REGULATIONS_HREF} label={t('inventory.instrument.back')} />
      <div className="mb-1.5" data-header-pills="">
        <PillRow pills={header} />
      </div>
      <PageHead title={record.shortName} lede={officialTitle} />
      <Meta className="mb-4">
        {officialTitle !== undefined && name?.isMachine === true && nameOriginal !== null ? (
          <span data-name-machine="">{t('inventory.instrument.nameMachine', { language: languageName(nameOriginal, locale) })}</span>
        ) : null}
        <span data-in-force-line="">{inForceLabel(record.inForceFrom, record.inForceTo, t, ctx)}</span>
        {sourceHref === null ? (
          <span className="break-all">{record.sourceUrl}</span>
        ) : (
          <a href={sourceHref} target="_blank" rel="noopener noreferrer" className="underline" data-source-link="">
            {t('inventory.instrument.sourceLabel')}
          </a>
        )}
      </Meta>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <ObligationsPanel instrument={record} />
          <ProvisionTree instrumentId={instrumentId} levelKind={record.level.kind} sourceUrl={record.sourceUrl} />
        </div>
        <div>
          <SummaryPanel instrument={record} selected={selected} onChoose={setChosen} />
          <IdentityPanel
            instrument={record}
            actions={
              permissions.includes(REPORT_PERMISSION) ? (
                <>
                  <div className="mt-4 flex justify-end">
                    <Button variant="outline" size="small" onClick={() => setReporting(true)}>
                      {t('inventory.instrument.reportProblem')}
                    </Button>
                  </div>
                  <ReportedProblems instrumentId={record.id} />
                </>
              ) : undefined
            }
          />
          <LineagePanel instrument={record} />
        </div>
      </div>

      <ReportProblemModal open={reporting} onOpenChange={onReporting} context={context} report={report} />
    </div>
  );
}
