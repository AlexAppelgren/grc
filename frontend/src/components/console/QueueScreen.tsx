'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { RetagRequestForm } from '@/components/console/RetagRequestForm';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Select } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { Tabs, TabPanel, type TabDef } from '@/components/ui/Tabs';
import { useFormatContext } from '@/features/identity/hooks';
import { presentProposal, proposerLine, refusalReason, selectionBlock, sourceLine, targetLine } from '@/features/proposals/proposal-presentation';
import { useApproveMany, useProposals, type ApproveManyOutcome } from '@/features/proposals/hooks';
import { TERM_KINDS, VOCABULARY_KINDS, type ProposalKind, type ProposalOrder, type ProposalQueueRow } from '@/features/proposals/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';
import { formatDateTime } from '@/shared/utils/format';
import { problemFrom } from '@/shared/utils/problem';

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

// The kind filter's values as the address holds them: two groups of kinds, and the two
// kinds a new record arrives as (the library baseline's, D-118), which are the route's own.
const KIND_FILTERS = ['obligation', 'new_instrument', 'new_obligation', 'vocabulary'] as const;
type KindFilter = '' | (typeof KIND_FILTERS)[number];
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
  return (KIND_FILTERS as readonly (string | null)[]).includes(value);
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

/** The `kind` query the route reads: a comma list for the vocabulary group, one value for any other kind, none for "any kind". */
export function kindQueryOf(kind: KindFilter): string | undefined {
  if (kind === '') return undefined;
  if (kind === 'obligation') return OBLIGATION_KIND;
  if (kind === 'vocabulary') return [...VOCABULARY_KINDS, ...TERM_KINDS].join(',');
  return kind;
}

/** A waiting row's checkbox: ticked or not, and why it cannot be ticked when it cannot. */
interface RowSelection {
  checked: boolean;
  blocked: string | null;
  busy: boolean;
  onChange: (checked: boolean) => void;
}

function QueueRow({ row, selection }: { row: ProposalQueueRow; selection?: RowSelection }) {
  const t = useT();
  const ctx = useFormatContext();
  const target = targetLine(row, t);
  const source = sourceLine(row, t);
  const frame = 'rounded-card border px-4 py-3.5';
  // A batch is one queue entry (PRO-04) and opens on its own review screen.
  const link = (
    <Link
      href={row.isBatch === true ? `/console/queue/batches/${row.id}` : `/console/queue/${row.id}`}
      prefetch={false}
      data-proposal-id={row.id}
      data-proposal-kind={row.kind}
      data-proposal-status={row.status}
      className={selection === undefined ? cn('block border-line bg-surface hover:border-fg', frame) : 'block min-w-0'}
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
  if (selection === undefined) return link;
  // The checkbox sits beside the link, never inside it, so no control is nested in a link.
  const why = `proposal-blocked-${row.id}`;
  return (
    <div className={cn('grid grid-cols-[28px_minmax(0,1fr)] items-start gap-x-2.5 hover:border-fg', frame, selection.checked ? 'border-fg bg-subtle' : 'border-line bg-surface')}>
      <input
        type="checkbox"
        className="mt-0.5 size-5 accent-button"
        checked={selection.checked}
        disabled={selection.blocked !== null || selection.busy}
        onChange={(event) => selection.onChange(event.target.checked)}
        aria-label={t('console.queue.select.row', { title: row.title })}
        aria-describedby={selection.blocked === null ? undefined : why}
        data-proposal-select={row.id}
      />
      <div className="min-w-0">
        {link}
        {selection.blocked === null ? null : (
          <p id={why} className="mt-1 text-meta text-muted" data-proposal-select-blocked="">
            {selection.blocked}
          </p>
        )}
      </div>
    </div>
  );
}

/** The select-all for the page: every row that can be approved together, checked when all are, mixed when some are. */
function SelectAll({ count, selectedCount, disabled, onChange }: { count: number; selectedCount: number; disabled: boolean; onChange: (checked: boolean) => void }) {
  const t = useT();
  const box = useRef<HTMLInputElement>(null);
  const mixed = selectedCount > 0 && selectedCount < count;
  useEffect(() => {
    if (box.current !== null) box.current.indeterminate = mixed;
  }, [mixed]);
  return (
    <label className="mb-2.5 ml-4 flex items-center gap-2.5 font-semibold">
      <input ref={box} type="checkbox" className="size-5 accent-button" checked={selectedCount === count} disabled={disabled} onChange={(event) => onChange(event.target.checked)} data-select-all="" />
      {t('console.queue.select.all', { count })}
    </label>
  );
}

/** How a run of approvals ended: how many were approved, and each refusal by its title and the server's reason. */
function ApproveManyResult({ outcome, onDismiss }: { outcome: ApproveManyOutcome; onDismiss: () => void }) {
  const t = useT();
  return (
    <Notice tone={outcome.refused.length === 0 ? 'plain' : 'warn'} data-approve-many-result="">
      <p className="font-semibold">{t('console.queue.approveMany.approved', { count: outcome.approved })}</p>
      {outcome.refused.length === 0 ? null : (
        <>
          <p className="mt-1">{t('console.queue.approveMany.refused', { count: outcome.refused.length })}</p>
          <ul className="m-0 mt-1 grid list-none gap-1 p-0">
            {outcome.refused.map((refusal) => (
              <li key={refusal.id} data-approve-many-refused={refusal.id} data-problem-code={problemFrom(refusal.error)?.code}>
                <b>{refusal.title}</b> <span className="text-meta">{refusalReason(refusal.error, t)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <Button variant="ghost" size="small" className="mt-2" onClick={onDismiss}>
        {t('common.done')}
      </Button>
    </Notice>
  );
}

export function QueueScreen() {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [retagging, setRetagging] = useState(false);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const approveMany = useApproveMany();

  const tab = tabFrom(params);
  const filters = filtersFrom(params);
  const offset = offsetFrom(params);
  const order = TAB_ORDER[tab];
  const query = useProposals({ status: TAB_STATUS[tab], kind: kindQueryOf(filters.kind), origin: filters.origin, notMine: filters.notMine, order, limit: QUEUE_PAGE, offset });
  const forbidden = forbiddenFrom(query.error);

  // A changed tab or filter starts again at the first page: the old offset means nothing in the new result.
  // A selection belongs to the page it was made on, so it goes with it.
  const go = (nextTab: TabKey, patch: Partial<QueueFilters> = {}, nextOffset = 0) => {
    setSelected(new Set());
    const next = { ...filters, ...patch };
    const search = searchOf(next, nextTab, nextOffset);
    router.replace(search === '' ? pathname : `${pathname}?${search}`);
  };

  const rows = query.data?.items ?? [];
  const total = query.data?.total ?? 0;

  // Approve many (D-118: the library baseline's proposals). Only Waiting selects, and only
  // a row that can be approved as it stands; each is then approved through the one approve
  // route in turn, exactly as if it were opened alone (features/proposals/hooks.ts).
  const waiting = tab === 'waiting';
  const selectable = waiting ? rows.filter((row) => selectionBlock(row, t) === null) : [];
  const chosen = selectable.filter((row) => selected.has(row.id));
  const busy = approveMany.isPending;
  const running = approveMany.variables?.length ?? 0;
  const toggle = (id: string, checked: boolean) => {
    const next = new Set(selected);
    if (checked) next.add(id);
    else next.delete(id);
    setSelected(next);
  };
  const start = () => {
    setConfirming(false);
    approveMany.mutate(chosen, { onSettled: () => setSelected(new Set()) });
  };

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
            <option value="new_instrument">{t('console.queue.filter.kindNewInstrument')}</option>
            <option value="new_obligation">{t('console.queue.filter.kindNewObligation')}</option>
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

        {approveMany.isSuccess ? <ApproveManyResult outcome={approveMany.data} onDismiss={() => approveMany.reset()} /> : null}
        {busy || (waiting && chosen.length > 0) ? (
          <div role="region" aria-label={t('console.queue.select.selection')} className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-card border border-fg bg-surface px-3.5 py-2.5" data-approve-many="">
            {busy ? (
              <p role="status" className="font-semibold">
                {t('console.queue.approveMany.progress', { current: Math.min(approveMany.done + 1, running), total: running })}
              </p>
            ) : (
              <>
                <b>{t('console.queue.select.selected', { count: chosen.length })}</b>
                <ButtonBar className="mt-0">
                  <Button variant="ghost" size="small" onClick={() => setSelected(new Set())}>
                    {t('console.queue.select.clear')}
                  </Button>
                  <Button size="small" onClick={() => setConfirming(true)}>
                    {t('console.queue.select.approve', { count: chosen.length })}
                  </Button>
                </ButtonBar>
              </>
            )}
          </div>
        ) : null}
        <Modal open={confirming} onOpenChange={setConfirming} title={t('console.queue.approveMany.title', { count: chosen.length })} description={t('console.queue.approveMany.body')}>
          <ButtonBar>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={start}>{t('console.queue.select.approve', { count: chosen.length })}</Button>
          </ButtonBar>
        </Modal>

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
            {selectable.length > 0 ? (
              <SelectAll count={selectable.length} selectedCount={chosen.length} disabled={busy} onChange={(checked) => setSelected(new Set(checked ? selectable.map((row) => row.id) : []))} />
            ) : null}
            <div className="grid gap-2" data-proposal-rows="">
              {rows.map((row) => (
                <QueueRow
                  key={row.id}
                  row={row}
                  selection={waiting ? { checked: selected.has(row.id), blocked: selectionBlock(row, t), busy, onChange: (checked) => toggle(row.id, checked) } : undefined}
                />
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
