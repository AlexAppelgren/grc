'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

import { RetagRequestForm } from '@/components/console/RetagRequestForm';

import { Button } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Select } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { Tabs, TabPanel, type TabDef } from '@/components/ui/Tabs';
import { useFormatContext } from '@/features/identity/hooks';
import { presentProposal, proposerLine, sourceLine, targetLine } from '@/features/proposals/proposal-presentation';
import { useProposals } from '@/features/proposals/hooks';
import { TERM_KINDS, VOCABULARY_KINDS, type ProposalKind, type ProposalOrder, type ProposalQueueRow } from '@/features/proposals/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDateTime } from '@/shared/utils/format';

// /console/queue (design/screens/console-queue.html; PRO-01, PRO-02, PRO-03,
// AC-PRO2). Waiting, Approved and Rejected tabs read GET /proposals with its
// own `status`, so each tab's count is the API's own total, never a
// client-side count of one page. Kind, "proposed by" and "Not mine" are the
// route's own filters (backend/apps/proposals/schemas.py `ProposalQuery`), so
// they reach every row and not only the page read. Each row carries the
// server's own `isMine`, `fromOrganisation` and `target`. The queue pages by
// the route's `limit`, `offset` and `total`, the offset held in the address so
// a reviewer comes back to the page they left; Waiting reads oldest first, the
// order the work arrived in, and the decided tabs newest first.

const TAB_STATUS = { waiting: 'open', approved: 'approved', rejected: 'rejected' } as const;
type TabKey = keyof typeof TAB_STATUS;
const TAB_KEYS: readonly TabKey[] = ['waiting', 'approved', 'rejected'];
export const TAB_ORDER: Readonly<Record<TabKey, ProposalOrder>> = { waiting: 'oldest', approved: 'newest', rejected: 'newest' };

// The route's largest page (API_PAGE_SIZE_MAX).
export const QUEUE_PAGE = 100;

const OBLIGATION_KIND: ProposalKind = 'new_obligation_version';

type KindFilter = '' | 'obligation' | 'vocabulary';
type OriginFilter = '' | 'agent' | 'user';

export interface QueueFilters {
  kind: KindFilter;
  origin: OriginFilter;
  notMine: boolean;
}

const EMPTY_FILTERS: QueueFilters = { kind: '', origin: '', notMine: false };

function isTab(value: string | null): value is TabKey {
  return value !== null && (TAB_KEYS as readonly string[]).includes(value);
}

function isKindFilter(value: string | null): value is KindFilter {
  return value === 'obligation' || value === 'vocabulary';
}

function isOriginFilter(value: string | null): value is OriginFilter {
  return value === 'agent' || value === 'user';
}

export function tabFrom(params: { get(name: string): string | null }): TabKey {
  const tab = params.get('tab');
  return isTab(tab) ? tab : 'waiting';
}

export function filtersFrom(params: { get(name: string): string | null }): QueueFilters {
  const kind = params.get('kind');
  const origin = params.get('origin');
  return { kind: isKindFilter(kind) ? kind : '', origin: isOriginFilter(origin) ? origin : '', notMine: params.get('notMine') === 'true' };
}

/** The page's first row, counting from 0: a whole multiple of the page, never negative. */
export function offsetFrom(params: { get(name: string): string | null }): number {
  const offset = Number(params.get('offset'));
  return Number.isInteger(offset) && offset > 0 ? offset - (offset % QUEUE_PAGE) : 0;
}

export function searchOf(filters: QueueFilters, tab: TabKey, offset = 0): string {
  const search = new URLSearchParams();
  if (tab !== 'waiting') search.set('tab', tab);
  if (filters.kind !== '') search.set('kind', filters.kind);
  if (filters.origin !== '') search.set('origin', filters.origin);
  if (filters.notMine) search.set('notMine', 'true');
  if (offset > 0) search.set('offset', String(offset));
  return search.toString();
}

/** The `kind` query the route reads: a comma list for the vocabulary group, one value for the obligation kind, none for "any kind". */
export function kindQueryOf(kind: KindFilter): string | undefined {
  if (kind === 'obligation') return OBLIGATION_KIND;
  if (kind === 'vocabulary') return [...VOCABULARY_KINDS, ...TERM_KINDS].join(',');
  return undefined;
}

function QueueRow({ row }: { row: ProposalQueueRow }) {
  const t = useT();
  const ctx = useFormatContext();
  const target = targetLine(row, t);
  const source = sourceLine(row, t);
  // A batch is one queue entry (PRO-04) and opens on its own review screen.
  return (
    <Link
      href={row.isBatch === true ? `/console/queue/batches/${row.id}` : `/console/queue/${row.id}`}
      prefetch={false}
      data-proposal-id={row.id}
      data-proposal-kind={row.kind}
      data-proposal-status={row.status}
      className="block rounded-card border border-line bg-surface px-4 py-3.5 hover:border-fg"
    >
      <PillRow pills={presentProposal(row, t)}>
        <span className="text-meta text-muted">{proposerLine(row, t)}</span>
        <span className="text-meta text-muted">{formatDateTime(row.createdAt, ctx)}</span>
        {row.isBatch === true ? <span className="text-meta text-muted">{t('console.queue.rowCount', { count: row.rowCount ?? 0 })}</span> : null}
      </PillRow>
      <h3 className="my-1.5 font-semibold">{row.title}</h3>
      {target !== null || source !== null ? (
        <p className="flex flex-wrap gap-x-3 text-meta text-muted">
          {target !== null ? <span data-proposal-target="">{target}</span> : null}
          {source !== null ? <span>{source}</span> : null}
        </p>
      ) : null}
    </Link>
  );
}

export function QueueScreen() {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [retagging, setRetagging] = useState(false);

  const tab = tabFrom(params);
  const filters = filtersFrom(params);
  const offset = offsetFrom(params);
  const order = TAB_ORDER[tab];
  const query = useProposals({ status: TAB_STATUS[tab], kind: kindQueryOf(filters.kind), origin: filters.origin, notMine: filters.notMine, order, limit: QUEUE_PAGE, offset });
  const forbidden = forbiddenFrom(query.error);

  // A changed tab or filter starts again at the first page: the old offset means nothing in the new result.
  const go = (nextTab: TabKey, patch: Partial<QueueFilters> = {}, nextOffset = 0) => {
    const next = { ...filters, ...patch };
    const search = searchOf(next, nextTab, nextOffset);
    router.replace(search === '' ? pathname : `${pathname}?${search}`);
  };

  const rows = query.data?.items ?? [];
  const total = query.data?.total ?? 0;

  const tabs: TabDef[] = [
    { id: 'waiting', label: tab === 'waiting' && query.isSuccess ? t('console.queue.tab.withCount', { label: t('console.queue.tab.waiting'), count: total }) : t('console.queue.tab.waiting') },
    { id: 'approved', label: t('console.queue.tab.approved') },
    { id: 'rejected', label: t('console.queue.tab.rejected') },
  ];

  const narrowed = filters.kind !== '' || filters.origin !== '' || filters.notMine;

  return (
    <>
      <PageHead
        title={t('console.queue.title')}
        lede={t('console.queue.lede')}
        actions={
          retagging ? undefined : (
            <Button variant="outline" onClick={() => setRetagging(true)}>
              {t('console.retag.open')}
            </Button>
          )
        }
      />
      {retagging ? <RetagRequestForm onClose={() => setRetagging(false)} /> : null}
      <Tabs tabs={tabs} current={tab} onSelect={(id) => go(isTab(id) ? id : 'waiting')} />
      <TabPanel id={tab}>
        <ChipRow className="mb-4">
          <Select aria-label={t('console.queue.filter.kind')} value={filters.kind} onChange={(e) => go(tab, { kind: isKindFilter(e.target.value) ? e.target.value : '' })} className="h-8 w-auto">
            <option value="">{t('console.queue.filter.kindAny')}</option>
            <option value="obligation">{t('console.queue.filter.kindObligationVersion')}</option>
            <option value="vocabulary">{t('console.queue.filter.kindVocabulary')}</option>
          </Select>
          <Select
            aria-label={t('console.queue.filter.origin')}
            value={filters.origin}
            onChange={(e) => go(tab, { origin: isOriginFilter(e.target.value) ? e.target.value : '' })}
            className="h-8 w-auto"
          >
            <option value="">{t('console.queue.filter.originAny')}</option>
            <option value="agent">{t('console.queue.filter.originAgent')}</option>
            <option value="user">{t('console.queue.filter.originUser')}</option>
          </Select>
          <Chip pressed={filters.notMine} onClick={() => go(tab, { notMine: !filters.notMine })}>
            {t('console.queue.filter.notMine')}
          </Chip>
        </ChipRow>

        {query.isPending ? (
          <LoadingState rows={3} />
        ) : forbidden !== null ? (
          <RestrictedScreen {...forbidden} />
        ) : query.isError ? (
          <ErrorState title={t('console.queue.errorTitle')} onRetry={() => void query.refetch()} />
        ) : rows.length === 0 ? (
          narrowed ? (
            <EmptyState title={t('console.queue.empty.filtered.title')} body={t('console.queue.empty.filtered.body')} action={{ label: t('common.cancel'), href: pathname, onClick: () => go(tab, EMPTY_FILTERS) }} />
          ) : tab === 'waiting' ? (
            <EmptyState title={t('console.queue.empty.waiting.title')} body={t('console.queue.empty.waiting.body')} />
          ) : tab === 'approved' ? (
            <EmptyState title={t('console.queue.empty.approved.title')} body={t('console.queue.empty.approved.body')} />
          ) : (
            <EmptyState title={t('console.queue.empty.rejected.title')} body={t('console.queue.empty.rejected.body')} />
          )
        ) : (
          <>
            <div className="grid gap-2" data-proposal-rows="">
              {rows.map((row) => (
                <QueueRow key={row.id} row={row} />
              ))}
            </div>
            {offset > 0 || total > offset + rows.length ? (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-meta text-muted" data-queue-paging="">
                <span>{t(order === 'newest' ? 'console.queue.more.newest' : 'console.queue.more.oldest', { from: offset + 1, to: offset + rows.length, total })}</span>
                <div className="flex gap-2">
                  <Button variant="outline" size="small" disabled={offset === 0} onClick={() => go(tab, {}, Math.max(0, offset - QUEUE_PAGE))}>
                    {t('console.queue.previous')}
                  </Button>
                  <Button variant="outline" size="small" disabled={offset + QUEUE_PAGE >= total} onClick={() => go(tab, {}, offset + QUEUE_PAGE)}>
                    {t('console.queue.next')}
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </TabPanel>
    </>
  );
}
