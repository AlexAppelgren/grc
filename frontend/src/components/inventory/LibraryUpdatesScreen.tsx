'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, Select, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useLibraryUpdates, useMarkVisited } from '@/features/library-updates/hooks';
import { presentLibraryUpdate, titleOf } from '@/features/library-updates/library-updates-presentation';
import type { LibraryUpdateRow, LibraryUpdatesQuery } from '@/features/library-updates/types';
import { api } from '@/shared/utils/api-client';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, formatLongDate } from '@/shared/utils/format';

// /inventory/updates (design/screens/tenant-library-updates.html; PRO-03,
// INV-04, INV-06, FP-03). One row per applied proposal that touches this
// bank's regulatory scope, grouped by day, with the diff one tap away and
// "This looks wrong" on every row that names a record. Nothing here writes
// the library: every member reads, and the one action any member has is a
// report that stays inside this bank (chunk 3, POST
// /obligations/{id}/problem-reports).
//
// GET /library-updates is chunk4-T13b's route and is not on `main` yet (see
// features/library-updates/types.ts); this screen is built against that
// task's own contract so it starts answering real data the moment T13b
// lands, and until then renders the same error state a dropped connection
// would. "Show what changed" and "Open" point at
// `/inventory/obligations/[obligationId]`, the same address
// `components/inventory/ObligationRow.tsx` already links to; that page is
// chunk 3's and is not built yet either.

function ReportProblemDialog({ obligationId, open, onClose }: { obligationId: string; open: boolean; onClose: () => void }) {
  const t = useT();
  const [description, setDescription] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);

  const close = () => {
    setDescription('');
    setSent(false);
    setError(null);
    onClose();
  };

  const submit = async () => {
    setPending(true);
    setError(null);
    try {
      await api.post(`/api/v1/obligations/${obligationId}/problem-reports`, { description: description.trim() });
      setSent(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : close())} title={t('library.updates.report.title')}>
      {sent ? (
        <>
          <StatusLine tone="positive">{t('library.updates.report.sent')}</StatusLine>
          <ButtonBar>
            <Button onClick={close}>{t('common.done')}</Button>
          </ButtonBar>
        </>
      ) : (
        <>
          <Field id="report-description" label={t('library.updates.report.description')}>
            <TextArea id="report-description" placeholder={t('library.updates.report.descriptionPlaceholder')} value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          {error !== null ? <ProblemAlert error={error} /> : null}
          <ButtonBar>
            <Button variant="outline" onClick={close} disabled={pending}>
              {t('common.cancel')}
            </Button>
            <Button disabled={pending || description.trim() === ''} onClick={() => void submit()}>
              {t('library.updates.report.submit')}
            </Button>
          </ButtonBar>
        </>
      )}
    </Modal>
  );
}

function UpdateRow({ row, onReport }: { row: LibraryUpdateRow; onReport: (obligationId: string) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <div className={row.inFootprint ? 'rounded-card border border-line bg-surface px-4 py-3.5' : 'rounded-card border border-dashed border-line-control bg-surface px-4 py-3.5'} data-update-id={row.id}>
      <PillRow pills={presentLibraryUpdate(row, t)}>
        {row.effectiveFrom !== null ? <span className="text-meta text-muted">{t('version.inForceFrom', { from: formatDate(row.effectiveFrom, ctx) })}</span> : null}
      </PillRow>
      <h3 className="my-1.5 font-semibold">
        {row.target !== null ? (
          <Link href={`/inventory/obligations/${row.target.id}`} prefetch={false} className="hover:underline">
            {titleOf(row, t)}
          </Link>
        ) : (
          titleOf(row, t)
        )}
      </h3>
      {!row.inFootprint && row.outsideTerms.length > 0 ? <p className="mb-1.5 text-meta text-muted">{t('library.updates.outsideScope', { terms: row.outsideTerms.join(', ') })}</p> : null}
      {row.target !== null ? (
        <ButtonBar className="mt-2 justify-start">
          <Link href={`/inventory/obligations/${row.target.id}`} prefetch={false} className="font-medium underline">
            {row.kind === 'new_obligation_version' ? t('library.updates.showWhatChanged') : t('library.updates.open')}
          </Link>
          <Button variant="ghost" size="small" onClick={() => onReport(row.target?.id ?? '')}>
            {t('library.updates.thisLooksWrong')}
          </Button>
        </ButtonBar>
      ) : null}
    </div>
  );
}

export function LibraryUpdatesScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const [kind, setKind] = useState('');
  const [outsideFootprint, setOutsideFootprint] = useState(false);
  const [reporting, setReporting] = useState<string | null>(null);
  const query: LibraryUpdatesQuery = { ...(kind === '' ? {} : { kind }), ...(outsideFootprint ? { outsideFootprint: true } : {}) };
  const updates = useLibraryUpdates(query);
  const markVisited = useMarkVisited();

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
          <option value="new_obligation_version">{t('library.updates.kind.newVersion')}</option>
          <option value="vocabulary_create">{t('library.updates.kind.vocabulary')}</option>
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
                  <UpdateRow key={row.id} row={row} onReport={setReporting} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {reporting !== null ? <ReportProblemDialog obligationId={reporting} open onClose={() => setReporting(null)} /> : null}
    </>
  );
}
