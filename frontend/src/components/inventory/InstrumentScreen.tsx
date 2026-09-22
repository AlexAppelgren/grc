'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
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
import type { InstrumentDetail, InstrumentLineageRef } from '@/features/library/types';
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

function lineageOf(lineage: readonly InstrumentLineageRef[], relation: string, direction: 'outgoing' | 'incoming'): InstrumentLineageRef[] {
  return lineage.filter((link) => link.relation.key === relation && link.direction === direction);
}

function LineageGroup({ title, links }: { title: string; links: readonly InstrumentLineageRef[] }) {
  if (links.length === 0) return null;
  return (
    <div className="mb-3" data-lineage-group={title}>
      <h3 className="mb-1.5 font-semibold">{title}</h3>
      <ul className="m-0 grid list-none gap-1.5 p-0 text-meta">
        {links.map((link) => (
          <li key={`${link.relation.key}:${link.direction}:${link.instrument.key}`} data-lineage-instrument={link.instrument.key}>
            <span className="font-medium">{link.instrument.shortName}</span>
            {link.note === '' ? null : <Meta className="mt-0.5">{link.note}</Meta>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** "Lineage": what this instrument implements, what elaborates it, and what amends it (INV-01). */
function LineagePanel({ instrument }: { instrument: InstrumentDetail }) {
  const t = useT();
  const implements_ = lineageOf(instrument.lineage, 'implements', 'outgoing');
  const elaboratedBy = lineageOf(instrument.lineage, 'elaborates', 'incoming');
  const amendedBy = lineageOf(instrument.lineage, 'amends', 'incoming');
  return (
    <Panel title={t('inventory.instrument.lineageTitle')} data-lineage-panel="">
      {instrument.lineage.length === 0 ? (
        <p className="text-meta text-muted">{t('inventory.instrument.lineageEmpty')}</p>
      ) : (
        <>
          <LineageGroup title={t('inventory.instrument.lineageImplements')} links={implements_} />
          <LineageGroup title={t('inventory.instrument.lineageElaboratedBy')} links={elaboratedBy} />
          <LineageGroup title={t('inventory.instrument.lineageAmendedBy')} links={amendedBy} />
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

function ObligationsPanel({ instrument }: { instrument: InstrumentDetail }) {
  const t = useT();
  const obligations = useObligations({ instrument: instrument.stableKey, outsideFootprint: true });
  const items = obligations.data?.items ?? [];
  return (
    <Panel title={t('inventory.instrument.obligationsTitle')} data-obligations-panel="">
      {obligations.isPending ? (
        <LoadingState rows={2} />
      ) : obligations.isError ? (
        <ErrorState title={t('inventory.instrument.obligationsErrorTitle')} onRetry={() => void obligations.refetch()} />
      ) : items.length === 0 ? (
        <p className="text-meta text-muted">{t('inventory.instrument.obligationsEmpty')}</p>
      ) : (
        <div className="grid gap-2">
          {items.map((obligation) => (
            <ObligationRow key={obligation.id} obligation={obligation} />
          ))}
        </div>
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
