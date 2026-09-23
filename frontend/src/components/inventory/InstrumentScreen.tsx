'use client';

import Link from 'next/link';
import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { ScopeChips } from '@/components/inventory/InventoryFilters';
import { searchOf } from '@/components/inventory/InventoryScreen';
import { Facts, type Fact } from '@/components/inventory/ObligationPanels';
import { ObligationRow } from '@/components/inventory/ObligationRow';
import { ProvisionTree } from '@/components/inventory/ProvisionTree';
import { ReportProblemModal, type ReportContext } from '@/components/inventory/ReportProblemModal';
import { Button } from '@/components/ui/Button';
import { Meta, Panel } from '@/components/ui/Panel';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useInstrument, useObligations, useReportInstrumentProblem } from '@/features/library/hooks';
import { presentInstrument } from '@/features/library/instrument-presentation';
import type { InstrumentDetail, InstrumentLineageRef, ScopeFilter } from '@/features/library/types';
import { inForceLabel } from '@/features/library/version-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';

// The instrument card (design/screens/tenant-instrument.html; INV-01, INV-06,
// FP-03). It reads and never writes the library: the one thing a reader can
// send from here is a problem report, which stays inside their own bank. The
// provision tree is its own panel (chunk3-rest-T18); the identity panel and
// lineage land here.

/** Reporting a problem with a library record is everyone's, but it is still a permission. */
const REPORT_PERMISSION = 'problems.report';

/** One heading of the lineage panel: every link of one relation type in one direction. */
interface LineageGroupOf {
  id: string;
  relation: InstrumentLineageRef['relation'];
  direction: InstrumentLineageRef['direction'];
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
    const id = `${link.relation.key}:${link.direction}`;
    const group = groups.get(id) ?? { id, relation: link.relation, direction: link.direction, links: [] };
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
          <li key={`${link.relation.key}:${link.direction}:${link.instrument.key}`} data-lineage-instrument={link.instrument.key}>
            <span className="font-medium">{link.instrument.shortName}</span>
            {link.note === '' ? null : <Meta className="mt-0.5">{link.note}</Meta>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** "Lineage": what this instrument implements, elaborates or amends, and what does so to it in turn (INV-01). */
function LineagePanel({ instrument }: { instrument: InstrumentDetail }) {
  const t = useT();
  const groups = lineageGroups(instrument.lineage);
  return (
    <Panel title={t('inventory.instrument.lineageTitle')} data-lineage-panel="">
      {groups.length === 0 ? (
        <p className="text-meta text-muted">{t('inventory.instrument.lineageEmpty')}</p>
      ) : (
        groups.map((group) => <LineageGroup key={group.id} group={group} />)
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
    { key: 'binding', label: t('inventory.instrument.bindingLabel'), value: instrument.binding ? t('pill.binding') : t('pill.guidanceComplyOrExplain') },
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
  return (
    <Panel title={t('inventory.instrument.obligationsTitle')} data-obligations-panel="">
      <div className="mb-3">
        <ScopeChips value={scope} onChange={setScope} />
      </div>
      {obligations.isPending ? (
        <LoadingState rows={2} />
      ) : obligations.isError ? (
        <ErrorState title={t('inventory.instrument.obligationsErrorTitle')} onRetry={() => void obligations.refetch()} />
      ) : items.length === 0 ? (
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
            <span data-obligations-total="">{t('inventory.count', { count: obligations.data?.total ?? items.length })}</span>
            <Link href={inventory} prefetch={false} className="underline">
              {t('inventory.instrument.obligationsInInventory')}
            </Link>
          </Meta>
        </>
      )}
    </Panel>
  );
}

export function InstrumentScreen({ instrumentId }: { instrumentId: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const permissions = usePermissions() ?? [];
  const [reporting, setReporting] = useState(false);

  const instrument = useInstrument(instrumentId);
  const record = instrument.data;
  const report = useReportInstrumentProblem(instrumentId);

  if (instrument.isError) {
    if (problemStatus(instrument.error) === 404) return <NotFoundScreen backHref="/inventory" backLabel={t('inventory.instrument.back')} />;
    return <ErrorState title={t('inventory.instrument.errorTitle')} onRetry={() => void instrument.refetch()} />;
  }
  if (record === undefined) return <LoadingState rows={3} />;

  const header = presentInstrument(
    {
      instrument: { key: record.stableKey, label: record.shortName },
      level: { key: record.level.key, label: record.level.label },
      binding: record.binding,
      jurisdiction: { key: record.jurisdiction.key, label: record.jurisdiction.label },
      ...(record.regime === null ? {} : { regime: { key: record.regime.key, label: record.regime.label } }),
    },
    t,
  );
  const context: ReportContext = {};

  return (
    <div data-instrument={record.stableKey}>
      <BackLink href="/inventory" label={t('inventory.instrument.back')} />
      <div className="mb-1.5" data-header-pills="">
        <PillRow pills={header} />
      </div>
      <PageHead title={record.name === null ? record.shortName : record.name.text} />
      <Meta className="mb-4">
        <span data-in-force-line="">{inForceLabel(record.inForceFrom, record.inForceTo, t, ctx)}</span>
        <a href={record.sourceUrl} target="_blank" rel="noopener noreferrer" className="underline" data-source-link="">
          {t('inventory.instrument.sourceLabel')}
        </a>
      </Meta>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <ProvisionTree instrumentId={instrumentId} />
          <ObligationsPanel instrument={record} />
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
          <LineagePanel instrument={record} />
        </div>
      </div>

      <ReportProblemModal open={reporting} onOpenChange={setReporting} context={context} report={report} />
    </div>
  );
}
