'use client';

import { useState } from 'react';

import { EmptyState } from '@/components/ui/EmptyState';
import { Select } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { Button } from '@/components/ui/Button';
import { ErrorState, LoadingState } from '@/components/ui/States';
import {
  applyFilters,
  coverageSummary,
  filterOptions,
  presentSource,
  registryRows,
  sourceMeta,
  useAuthorities,
  useSourceCoverage,
  useSources,
  type RegistryRow,
} from '@/features/console-watch/sources';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// Sources (design/screens/console-sources.html, WAT-01, ADM-02): every place
// bleqq watches, with how its last check went and whether it has gone stale.
// Read-only. Adding, editing and pausing a source, and "check a source now",
// are not on this page: the first is sources.manage work R1 does not put here
// and the last is AGT-05, which chunk 11 builds on a key-only route. Each is
// absent rather than disabled, so nothing on this page calls a route this
// session could not pass, and the diff holds no call that writes.

function SourceRow({ row }: { row: RegistryRow }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Row data-source-id={row.source.id}>
      <PillRow pills={presentSource(row, t)} />
      <h3 className="mt-1.5 mb-1 font-semibold">{row.source.name}</h3>
      {row.source.url === null ? null : <p className="mb-1 font-mono text-meta break-all">{row.source.url}</p>}
      <Meta>
        {sourceMeta(row, t, ctx).map((line) => (
          <span key={line}>{line}</span>
        ))}
      </Meta>
      {row.coverage?.lastError === null || row.coverage?.lastError === undefined ? null : <p className="mt-1 text-meta text-negative">{row.coverage.lastError}</p>}
    </Row>
  );
}

export function SourcesScreen() {
  const t = useT();
  const sources = useSources();
  const coverage = useSourceCoverage();
  const authorities = useAuthorities();
  const [jurisdiction, setJurisdiction] = useState('');
  const [kind, setKind] = useState('');
  const [failingOnly, setFailingOnly] = useState(false);

  if (sources.isPending || coverage.isPending) return <RegistryFrame>{<LoadingState rows={3} />}</RegistryFrame>;
  if (sources.isError || coverage.isError) {
    return (
      <RegistryFrame>
        <ErrorState
          title={t('console.sources.errorTitle')}
          onRetry={() => {
            void sources.refetch();
            void coverage.refetch();
          }}
        />
      </RegistryFrame>
    );
  }

  const rows = registryRows(sources.data, coverage.data, authorities.data ?? []);
  const options = filterOptions(rows);
  const shown = applyFilters(rows, { jurisdiction, kind, failingOnly });
  const summary = coverageSummary(rows, new Date());

  return (
    <RegistryFrame>
      {rows.length === 0 ? (
        <EmptyState title={t('console.sources.emptyTitle')} body={t('console.sources.emptyBody')} />
      ) : (
        <>
          <Meta className="mb-3 flex flex-wrap gap-x-4 gap-y-1">
            <span>{t('console.sources.checkedInDay', { checked: summary.checked, total: summary.total })}</span>
            <span>{t('console.sources.failing', { count: summary.failing })}</span>
          </Meta>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Select aria-label={t('console.sources.filter.jurisdiction')} value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)}>
              <option value="">{t('console.sources.filter.anyJurisdiction')}</option>
              {options.jurisdictions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </Select>
            <Select aria-label={t('console.sources.filter.kind')} value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">{t('console.sources.filter.anyKind')}</option>
              {options.kinds.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </Select>
            <Button variant="outline" size="small" aria-pressed={failingOnly} onClick={() => setFailingOnly(!failingOnly)}>
              {t('console.sources.filter.failingOnly')}
            </Button>
          </div>
          {shown.length === 0 ? (
            <EmptyState title={t('console.sources.coverageEmptyTitle')} body={t('console.sources.coverageEmptyBody')} />
          ) : (
            <Rows data-sources-list="">
              {shown.map((row) => (
                <SourceRow key={row.source.id} row={row} />
              ))}
            </Rows>
          )}
          <Meta className="mt-4">
            <span>{t('console.sources.registryCount', { count: shown.length })}</span>
          </Meta>
        </>
      )}
    </RegistryFrame>
  );
}

function RegistryFrame({ children }: { children: React.ReactNode }) {
  const t = useT();
  return (
    <>
      <PageHead title={t('console.sources.title')} lede={t('console.sources.lede')} />
      {children}
    </>
  );
}
