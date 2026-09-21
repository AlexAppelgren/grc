'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Select } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { Tabs, TabPanel, type TabDef } from '@/components/ui/Tabs';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { isMineOf, presentProposal, proposerLine, sourceLine } from '@/features/proposals/proposal-presentation';
import { useProposals } from '@/features/proposals/hooks';
import type { ProposalKind, ProposalRow } from '@/features/proposals/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDateTime } from '@/shared/utils/format';

// /console/queue (design/screens/console-queue.html; PRO-01, PRO-02, PRO-03,
// AC-PRO2). Waiting, Approved and Rejected tabs read GET /proposals with its
// own `status`, so each tab's count is the API's own total, never a
// client-side count of one page (there is no paging: the route answers every
// matching row in one call). Kind, "proposed by" and "Not mine" narrow the
// tab's own rows in the browser, because the route filters only by status,
// kind and targetList (backend/apps/proposals/schemas.py `ProposalQuery`).
//
// GET /proposals does not yet carry a target title, reference or instrument
// short name, a server-computed `isMine`, or `fromOrganisation`
// (chunk4-T10's enrichment; not on `main`). `isMine` is computed from the
// row's own `proposedBy.id` against the signed-in reader; see
// proposal-presentation.ts for what that does and does not disclose.

const TAB_STATUS = { waiting: 'open', approved: 'approved', rejected: 'rejected' } as const;
type TabKey = keyof typeof TAB_STATUS;
const TAB_KEYS: readonly TabKey[] = ['waiting', 'approved', 'rejected'];

const OBLIGATION_KIND: ProposalKind = 'new_obligation_version';
const VOCABULARY_KINDS: readonly ProposalKind[] = [
  'vocabulary_create',
  'vocabulary_relabel',
  'vocabulary_retire',
  'vocabulary_restore',
  'vocabulary_merge',
  'term_create',
  'term_update',
];

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

export function searchOf(filters: QueueFilters, tab: TabKey): string {
  const search = new URLSearchParams();
  if (tab !== 'waiting') search.set('tab', tab);
  if (filters.kind !== '') search.set('kind', filters.kind);
  if (filters.origin !== '') search.set('origin', filters.origin);
  if (filters.notMine) search.set('notMine', 'true');
  return search.toString();
}

/** The `kind` query the route reads: a comma list for the vocabulary group, one value for the obligation kind, none for "any kind". */
export function kindQueryOf(kind: KindFilter): string | undefined {
  if (kind === 'obligation') return OBLIGATION_KIND;
  if (kind === 'vocabulary') return VOCABULARY_KINDS.join(',');
  return undefined;
}

/** "Proposed by" and "Not mine" narrow the tab's own rows client-side (the route has no filter for either). */
export function visibleRows(rows: readonly ProposalRow[], filters: QueueFilters, meId: string | null): ProposalRow[] {
  return rows.filter((row) => {
    if (filters.origin !== '' && row.origin !== filters.origin) return false;
    if (filters.notMine && isMineOf(row, meId)) return false;
    return true;
  });
}

function QueueRow({ row, meId }: { row: ProposalRow; meId: string | null }) {
  const t = useT();
  const ctx = useFormatContext();
  const mine = isMineOf(row, meId);
  const source = sourceLine(row, t);
  return (
    <Link
      href={`/console/queue/${row.id}`}
      prefetch={false}
      data-proposal-id={row.id}
      data-proposal-kind={row.kind}
      data-proposal-status={row.status}
      className="block rounded-card border border-line bg-surface px-4 py-3.5 hover:border-fg"
    >
      <PillRow pills={presentProposal(row, mine, t)}>
        <span className="text-meta text-muted">{proposerLine(row, t)}</span>
        <span className="text-meta text-muted">{formatDateTime(row.createdAt, ctx)}</span>
      </PillRow>
      <h3 className="my-1.5 font-semibold">{row.title}</h3>
      {source !== null ? <p className="text-meta text-muted">{source}</p> : null}
    </Link>
  );
}

export function QueueScreen() {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { me } = useSession();
  const meId = me?.user.id ?? null;

  const tab = tabFrom(params);
  const filters = filtersFrom(params);
  const query = useProposals({ status: TAB_STATUS[tab], kind: kindQueryOf(filters.kind) });
  const forbidden = forbiddenFrom(query.error);

  const go = (nextTab: TabKey, patch: Partial<QueueFilters> = {}) => {
    const next = { ...filters, ...patch };
    const search = searchOf(next, nextTab);
    router.replace(search === '' ? pathname : `${pathname}?${search}`);
  };

  const rows = query.data === undefined ? [] : visibleRows(query.data.items, filters, meId);
  const total = query.data?.total ?? 0;

  const tabs: TabDef[] = [
    { id: 'waiting', label: tab === 'waiting' && query.isSuccess ? t('console.queue.tab.withCount', { label: t('console.queue.tab.waiting'), count: total }) : t('console.queue.tab.waiting') },
    { id: 'approved', label: t('console.queue.tab.approved') },
    { id: 'rejected', label: t('console.queue.tab.rejected') },
  ];

  const narrowed = filters.kind !== '' || filters.origin !== '' || filters.notMine;

  return (
    <>
      <PageHead title={t('console.queue.title')} lede={t('console.queue.lede')} />
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
          <div className="grid gap-2" data-proposal-rows="">
            {rows.map((row) => (
              <QueueRow key={row.id} row={row} meId={meId} />
            ))}
          </div>
        )}
      </TabPanel>
    </>
  );
}
