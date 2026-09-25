'use client';

import { EmptyState } from '@/components/ui/EmptyState';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import type { SourceCoverage } from '@/features/watch/api';
import { coverageMeta, presentSourceCoverage } from '@/features/watch/coverage-presentation';
import { useSourceCoverage } from '@/features/watch/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';

// The feed's Coverage tab (WAT-01, design/screens/tenant-watch.html): what
// the agents checked and how it went, read-only. The console manages the
// registry; this tab only says what happened.
//
// The card also draws four figures at the top — how many sources were checked
// in the last day, how many fetches failed, how many changes were found this
// week and when the last run was. `GET /sources/coverage` answers none of
// them, and a count assembled in the browser would be a different number from
// the one the server knows, so the tab shows the log it can answer for.

export function SourceCoverageRow({ row }: { row: SourceCoverage }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <li data-source={row.source.name} data-stale={row.overdue ? '' : undefined} className="rounded-card border border-line bg-surface px-4 py-3.5">
      <PillRow pills={presentSourceCoverage(row, t)} />
      <h3 className="my-1.5 font-semibold">{row.source.name}</h3>
      <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-muted">
        {coverageMeta(row, t, ctx).map((line) => (
          <span key={line}>{line}</span>
        ))}
      </p>
      {/* The agent's own short message about the failing check. Fetched page
          content never reaches a screen as markup (AGT-07), and this is the
          agent's sentence about the fetch, not the page. */}
      {row.lastError === null || row.lastError === '' ? null : (
        <p data-last-error="" className="mt-1.5 text-meta text-negative">
          {row.lastError}
        </p>
      )}
    </li>
  );
}

export function SourceCoverageTab({ active }: { active: boolean }) {
  const t = useT();
  const coverage = useSourceCoverage(active);
  const forbidden = forbiddenFrom(coverage.error);

  if (coverage.isPending) return <LoadingState rows={3} />;
  if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  if (coverage.isError) return <ErrorState title={t('watch.coverage.errorTitle')} onRetry={() => void coverage.refetch()} />;
  if (coverage.data.length === 0) return <EmptyState title={t('watch.coverage.emptyTitle')} body={t('watch.coverage.emptyBody')} />;

  return (
    <>
      <p className="mb-3 text-meta text-muted">{t('watch.coverage.lede')}</p>
      <ul className="grid gap-2" data-source-coverage="">
        {coverage.data.map((row) => (
          <SourceCoverageRow key={row.source.id} row={row} />
        ))}
      </ul>
    </>
  );
}
