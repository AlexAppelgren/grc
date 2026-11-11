'use client';

import Link from 'next/link';
import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { ScopeControl } from '@/components/inventory/InventoryFilters';
import { searchOf } from '@/components/inventory/InventoryScreen';
import { Facts, type Fact } from '@/components/inventory/ObligationPanels';
import { ObligationRow } from '@/components/inventory/ObligationRow';
import { languageChoices, originalLanguage, textIn } from '@/components/inventory/ObligationScreen';
import { ProvisionTree } from '@/components/inventory/ProvisionTree';
import { RecordProblemReports } from '@/components/inventory/RecordProblemReports';
import { ReportProblemModal, type ReportContext } from '@/components/inventory/ReportProblemModal';
import { Button } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Meta, Panel } from '@/components/ui/Panel';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen, QueryState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { lineageDirectionOf } from '@/features/library/api';
import { useInstrument, useObligations, useReportInstrumentProblem } from '@/features/library/hooks';
import { DIRECTIVE_LEVEL, obligationsTitleOf, presentInstrument } from '@/features/library/instrument-presentation';
import { markPrivateToUs, presentBindingLevel } from '@/features/library/obligation-presentation';
import type { InstrumentDetail, InstrumentLineageRef, InstrumentLinkRef, ScopeFilter } from '@/features/library/types';
import { inForceLabel, languageName } from '@/features/library/version-presentation';
import { useRefreshProblemReports } from '@/features/problem-reports/hooks';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { externalHref } from '@/shared/utils/external-href';
import { formatDate } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';

// The instrument card (design/screens/tenant-instrument.html; INV-01, INV-06,
// FP-03). It reads and never writes the library: the one thing a reader can
// send from here is a problem report, which stays inside their own bank,
// and the close of one in its Reported problems section (AUD-03). The
// provision tree is its own panel (chunk3-rest-T18); the identity panel and
// lineage land here.

/** Reporting a problem with a library record is everyone's, but it is still a permission. */
const REPORT_PERMISSION = 'problems.report';

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
            <span className="font-medium">{link.instrument.shortName}</span>
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

/**
 * What applies, said before any list (INV-09): how many duties the library holds and
 * how many fall in the reader's scope; for a directive, that its duties come from each
 * country's implementing law, with those laws; and new duties still waiting for review.
 */
function WhatApplies({ instrument }: { instrument: InstrumentDetail }) {
  const t = useT();
  const counts = instrument.obligationCounts;
  const directive = instrument.level.key === DIRECTIVE_LEVEL && counts.inLibrary === 0;
  return (
    <div className="mb-3 grid gap-2 text-body" data-what-applies="">
      {directive ? (
        <>
          <p>{t('inventory.instrument.applies.directive')}</p>
          {instrument.implementedBy.length === 0 ? (
            <p className="text-meta text-muted">{t('inventory.instrument.applies.noNationalLaw')}</p>
          ) : (
            <div data-implemented-by="">
              <h3 className="mb-1.5 font-semibold">{t('inventory.instrument.applies.implementedByTitle')}</h3>
              <InstrumentLinks links={instrument.implementedBy} />
            </div>
          )}
        </>
      ) : counts.inLibrary === 0 ? (
        counts.waitingForReview === 0 ? (
          <p className="text-meta text-muted">{t('inventory.instrument.applies.none')}</p>
        ) : null
      ) : (
        <p data-applies-counts="">{t('inventory.instrument.applies.counts', { inLibrary: counts.inLibrary, inScope: counts.inScope })}</p>
      )}
      {counts.waitingForReview === 0 ? null : (
        <p className="text-meta text-muted" data-applies-waiting="">
          {t('inventory.instrument.applies.waiting', { count: counts.waitingForReview })}
        </p>
      )}
    </div>
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
 * The obligations from this instrument under the reader's scope filter
 * (FP-03, FP-04), exactly as the inventory filtered by this instrument lists
 * them: the total says how many there are beyond the first page, and the link
 * opens that same list in the inventory.
 */
function ObligationsPanel({ instrument }: { instrument: InstrumentDetail }) {
  const t = useT();
  const [scope, setScope] = useState<ScopeFilter>('in');
  const obligations = useObligations(scope === 'in' ? { instrument: instrument.stableKey } : { instrument: instrument.stableKey, footprint: scope });
  const items = obligations.data?.items ?? [];
  const inventory = `/inventory?${searchOf('obligations', { instrument: instrument.stableKey, regime: '', service: '', dutyType: '', asOf: '', scope })}`;
  if (instrument.obligationCounts.inLibrary === 0) {
    return (
      <Panel title={obligationsTitleOf(instrument.level.key, t)} data-obligations-panel="">
        <WhatApplies instrument={instrument} />
      </Panel>
    );
  }
  return (
    <Panel title={obligationsTitleOf(instrument.level.key, t)} data-obligations-panel="">
      <WhatApplies instrument={instrument} />
      <div className="mb-3">
        <ScopeControl value={scope} onChange={setScope} />
      </div>
      <QueryState query={obligations} rows={2} errorTitle={t('inventory.instrument.obligationsErrorTitle')}>
        {(data) =>
          items.length === 0 ? (
            <p className="text-meta text-muted">
              {t(scope === 'all' ? 'inventory.instrument.obligationsEmpty' : scope === 'watched' ? 'library.empty.watched.title' : 'inventory.instrument.obligationsEmptyInScope')}
            </p>
          ) : (
            <>
              <div className="grid gap-2">
                {items.map((obligation) => (
                  <ObligationRow key={obligation.id} obligation={obligation} watched={scope === 'watched'} />
                ))}
              </div>
              <Meta className="mt-3">
                <span data-obligations-total="">{t('inventory.count', { count: data?.total ?? items.length })}</span>
                <Link href={inventory} prefetch={false} className="underline">
                  {t('inventory.instrument.obligationsInInventory')}
                </Link>
              </Meta>
            </>
          )
        }
      </QueryState>
    </Panel>
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
    if (problemStatus(instrument.error) === 404) return <NotFoundScreen backHref="/inventory" backLabel={t('inventory.instrument.back')} />;
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
      <BackLink href="/inventory" label={t('inventory.instrument.back')} />
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
          <SummaryPanel instrument={record} selected={selected} onChoose={setChosen} />
          <ObligationsPanel instrument={record} />
          <ProvisionTree instrumentId={instrumentId} levelKind={record.level.kind} sourceUrl={record.sourceUrl} />
        </div>
        <div>
          <IdentityPanel
            instrument={record}
            actions={
              permissions.includes(REPORT_PERMISSION) ? (
                <Button variant="outline" size="small" className="mt-4" onClick={() => setReporting(true)}>
                  {t('inventory.instrument.reportProblem')}
                </Button>
              ) : undefined
            }
          />
          <RecordProblemReports subjectType="instrument" subjectId={record.id} />
          <LineagePanel instrument={record} />
        </div>
      </div>

      <ReportProblemModal open={reporting} onOpenChange={onReporting} context={context} report={report} />
    </div>
  );
}
