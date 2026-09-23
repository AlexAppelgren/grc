'use client';

import Link from 'next/link';
import { useState } from 'react';

import { ReportProblemModal } from '@/components/inventory/ReportProblemModal';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Select } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, StatusLine } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useReportObligationProblem } from '@/features/library/hooks';
import { useLibraryUpdates, useMarkVisited } from '@/features/library-updates/hooks';
import { inForceLine, KIND_FILTER, outsideScopeLine, presentLibraryUpdate, titleOf } from '@/features/library-updates/library-updates-presentation';
import type { LibraryUpdateRow, LibraryUpdateTarget } from '@/features/library-updates/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate, formatLongDate } from '@/shared/utils/format';

// /inventory/updates (design/screens/tenant-library-updates.html; PRO-03,
// INV-04, INV-06, AUD-03, FP-03). One row per applied change that touches
// this bank's regulatory scope, grouped by the bank's own day, with the diff
// one tap away and "This looks wrong" on every row that names a record.
// Nothing here writes the library: every member reads, and the one action is
// the same problem report the obligation card files, which stays inside this
// bank.

/** Reporting a problem with a library record is everyone's, but it is still a permission. */
const REPORT_PERMISSION = 'problems.report';

function UpdateRow({ row, canReport, onReport }: { row: LibraryUpdateRow; canReport: boolean; onReport: (row: LibraryUpdateRow) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const target: LibraryUpdateTarget | null = row.target ?? null;
  const inForce = inForceLine(row, t, ctx);
  const outside = outsideScopeLine(row, t);
  return (
    <div
      className={row.inFootprint ? 'rounded-card border border-line bg-surface px-4 py-3.5' : 'rounded-card border border-dashed border-line-control bg-surface px-4 py-3.5'}
      data-update-id={row.id}
      data-outside-footprint={row.inFootprint ? undefined : ''}
    >
      <PillRow pills={presentLibraryUpdate(row, t)}>{inForce === null ? null : <span className="text-meta text-muted">{inForce}</span>}</PillRow>
      <h3 className="my-1.5 font-semibold">
        {target !== null ? (
          <Link href={`/inventory/obligations/${target.id}`} prefetch={false} className="hover:underline">
            {titleOf(row, t)}
          </Link>
        ) : (
          titleOf(row, t)
        )}
      </h3>
      {outside === null ? null : <p className="mb-1.5 text-meta text-muted">{outside}</p>}
      {target !== null ? (
        <ButtonBar className="mt-2 justify-start">
          <Link href={`/inventory/obligations/${target.id}`} prefetch={false} className="font-medium underline">
            {row.kind === KIND_FILTER.newVersion ? t('library.updates.showWhatChanged') : t('library.updates.open')}
          </Link>
          {canReport ? (
            <Button variant="ghost" size="small" onClick={() => onReport(row)}>
              {t('library.updates.thisLooksWrong')}
            </Button>
          ) : null}
        </ButtonBar>
      ) : null}
    </div>
  );
}

export function LibraryUpdatesScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const permissions = usePermissions() ?? [];
  const [kind, setKind] = useState('');
  const [outsideFootprint, setOutsideFootprint] = useState(false);
  const [reporting, setReporting] = useState<LibraryUpdateRow | null>(null);
  const updates = useLibraryUpdates({ ...(kind === '' ? {} : { kind }), ...(outsideFootprint ? { outsideFootprint: true } : {}) });
  const markVisited = useMarkVisited();
  const report = useReportObligationProblem(reporting?.target?.id ?? '');

  const days = updates.data?.days ?? [];
  const total = updates.data?.total ?? 0;

  return (
    <>
      <PageHead
        title={t('library.updates.title')}
        lede={updates.data === undefined ? undefined : t('library.updates.lede', { count: total, date: formatDate(updates.data.since, ctx) })}
        actions={
          <Button variant="outline" disabled={markVisited.isPending} onClick={() => markVisited.mutate()}>
            {t('library.updates.markAsSeen')}
          </Button>
        }
      />
      {markVisited.isSuccess ? <StatusLine tone="positive">{t('library.updates.marked')}</StatusLine> : null}

      <ChipRow className="mb-4">
        <Select aria-label={t('library.updates.filter.kind')} value={kind} onChange={(e) => setKind(e.target.value)} className="h-8 w-auto">
          <option value="">{t('library.updates.filter.kindAny')}</option>
          <option value={KIND_FILTER.newVersion}>{t('library.updates.kind.newVersion')}</option>
          <option value={KIND_FILTER.vocabulary}>{t('library.updates.kind.vocabulary')}</option>
        </Select>
        <Chip pressed={outsideFootprint} onClick={() => setOutsideFootprint((prev) => !prev)}>
          {t('library.updates.filter.outside')}
        </Chip>
      </ChipRow>

      {updates.isPending ? (
        <LoadingState rows={3} />
      ) : updates.isError ? (
        <ErrorState title={t('library.updates.errorTitle')} onRetry={() => void updates.refetch()} />
      ) : days.length === 0 ? (
        <EmptyState
          title={t('library.updates.empty.title', { date: formatDate(updates.data.since, ctx) })}
          body={t('library.updates.empty.body')}
          action={{ label: t('library.updates.empty.browseInventory'), href: '/inventory' }}
        />
      ) : (
        <div className="grid gap-4" data-update-days="">
          {days.map((day) => (
            <div key={day.date}>
              <h2 className="mb-2 text-meta text-muted">{formatLongDate(day.date, ctx)}</h2>
              <div className="grid gap-2">
                {day.items.map((row) => (
                  <UpdateRow key={row.id} row={row} canReport={permissions.includes(REPORT_PERMISSION)} onReport={setReporting} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <ReportProblemModal
        open={reporting !== null}
        onOpenChange={(open) => (open ? undefined : setReporting(null))}
        // The version the row named, so a colleague opens the same words.
        context={typeof reporting?.versionNumber === 'number' ? { versionNumber: reporting.versionNumber } : {}}
        report={report}
      />
    </>
  );
}
