'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { Tabs, TabPanel, type TabDef } from '@/components/ui/Tabs';
import { SourceCoverageTab } from '@/components/watch/SourceCoverageTab';
import { EMPTY_FILTERS, SCOPE_VALUES, WatchFilterBar, type ScopeFilter, type WatchFilters } from '@/components/watch/WatchFilters';
import { useFormatContext } from '@/features/identity/hooks';
import type { ChangeQuery, ChangeRow } from '@/features/watch/api';
import { authorityAndDate, caseStatusLabel, keyDateMeta, presentChangeRow, scopeTermLabels } from '@/features/watch/change-presentation';
import { TAB_CATEGORY, TAB_KEYS, useChangeFeed, useTriageCount, type TabKey } from '@/features/watch/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';
import type { FormatContext } from '@/shared/utils/format';

// /watch (design/screens/tenant-watch.html; WAT-02, WAT-03, FP-03, CAS-01).
// Tabs by case category, filters that store keys, rows in the card's fixed
// slot order. The URL carries the whole view, so a feed is linkable. Nothing
// on this screen writes: triage arrives with the case workflow.

/** The Coverage tab sits beside the case categories: it reads the source log, not the feed. */
export const COVERAGE_TAB = 'coverage';
export type WatchTab = TabKey | typeof COVERAGE_TAB;

function isTab(value: string | null): value is WatchTab {
  return value !== null && (TAB_KEYS as readonly string[]).concat(COVERAGE_TAB).includes(value);
}

function isScope(value: string | null): value is ScopeFilter {
  return value !== null && (SCOPE_VALUES as readonly string[]).includes(value);
}

/** The URL's filters. An unknown or missing parameter reads as "not filtered". */
export function filtersFrom(params: { get(name: string): string | null }): WatchFilters {
  const scope = params.get('scope');
  return {
    regimeTermId: params.get('term') ?? '',
    changeType: params.get('type') ?? '',
    urgency: params.get('urgency') ?? '',
    week: params.get('week') ?? '',
    unconfirmedSoWhat: params.get('unconfirmed') === 'true',
    scope: isScope(scope) ? scope : 'in',
  };
}

export function tabFrom(params: { get(name: string): string | null }): WatchTab {
  const tab = params.get('tab');
  return isTab(tab) ? tab : 'triage';
}

/** The filters and the tab back into a query string; nothing for a filter that is not set. */
export function searchOf(filters: WatchFilters, tab: WatchTab): string {
  const search = new URLSearchParams();
  if (tab !== 'triage') search.set('tab', tab);
  if (filters.regimeTermId !== '') search.set('term', filters.regimeTermId);
  if (filters.changeType !== '') search.set('type', filters.changeType);
  if (filters.urgency !== '') search.set('urgency', filters.urgency);
  if (filters.week !== '') search.set('week', filters.week);
  if (filters.unconfirmedSoWhat) search.set('unconfirmed', 'true');
  // The phrase someone typed is deliberately absent: it is this bank's own
  // words, and tenant content belongs in no address bar (playbook 6.6).
  if (filters.scope !== 'in') search.set('scope', filters.scope);
  return search.toString();
}

/** The read's query: keys, one term id and one footprint value, the way the route reads them. */
export function queryOf(filters: WatchFilters, search: string): ChangeQuery {
  const query: ChangeQuery = { footprint: filters.scope };
  if (filters.regimeTermId !== '') query.termId = [filters.regimeTermId];
  if (filters.changeType !== '') query.changeType = filters.changeType;
  if (filters.urgency !== '') query.urgency = filters.urgency;
  if (filters.week !== '') query.week = filters.week;
  if (filters.unconfirmedSoWhat) query.unconfirmedSoWhat = true;
  if (search !== '') query.q = search;
  return query;
}

/** Whether the reader narrowed the feed, which decides which empty state answers them. */
export function isNarrowed(filters: WatchFilters, search: string): boolean {
  return (
    filters.regimeTermId !== '' ||
    filters.changeType !== '' ||
    filters.urgency !== '' ||
    filters.week !== '' ||
    search !== '' ||
    filters.unconfirmedSoWhat ||
    filters.scope !== 'in'
  );
}

const TAB_LABEL_KEY = {
  triage: 'watch.tab.triage',
  inProgress: 'watch.tab.inProgress',
  closed: 'watch.tab.closed',
  dismissed: 'watch.tab.dismissed',
} as const;

export function ChangeFeedRow({ row, today }: { row: ChangeRow; today: Date }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Link
      href={`/watch/${row.id}`}
      // A page of rows would otherwise prefetch a page of change pages nobody
      // asked for, which is a request per row.
      prefetch={false}
      data-change={row.stableKey}
      data-outside-footprint={row.inFootprint ? undefined : ''}
      className={cn('block rounded-card border bg-surface px-4 py-3.5 hover:border-fg', row.inFootprint ? 'border-line' : 'border-dashed border-line-control')}
    >
      <PillRow pills={presentChangeRow(row, 'row', t)}>
        <span className="text-meta text-muted">{authorityAndDate(row, t, ctx)}</span>
      </PillRow>
      <h3 className="my-1.5 font-semibold">{row.title}</h3>
      <SoWhat row={row} />
      <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-muted">
        {footMeta(row, t, ctx, today).map((line, index) => (
          // Two facts can read the same, so the position is the key.
          <span key={index}>{line}</span>
        ))}
      </p>
    </Link>
  );
}

/** This bank's own "So what?", with the AI label until a person here confirmed it (WAT-05). */
function SoWhat({ row }: { row: ChangeRow }) {
  const t = useT();
  if (row.case === null || row.case.soWhatText === null || row.case.soWhatText === '') return null;
  return (
    <div className="mb-2 text-meta text-muted">
      {row.case.soWhatConfirmed ? null : <span className="block font-semibold text-brass">{t('watch.soWhat.aiDraft')}</span>}
      <span className="font-semibold text-fg">{t('watch.soWhat.label')}</span> <span>{row.case.soWhatText}</span>
    </div>
  );
}

/** The row's foot: where the case stands, the date that drives it, the scope it carries. */
export function footMeta(row: ChangeRow, t: Translate, ctx: FormatContext, today: Date): string[] {
  const meta: string[] = [];
  if (row.case !== null) meta.push(caseStatusLabel(row.case.category, t));
  meta.push(...keyDateMeta(row, t, ctx, today));
  const terms = scopeTermLabels(row);
  if (terms.length > 0) meta.push(terms.join(', '));
  // A row from a market we watch names the market, as text and never a pill
  // (FP-04). Otherwise the feed read says whether a row is outside the footprint
  // but not which terms put it there, so the row says that it is and the change
  // page says why.
  if (row.market !== null) meta.push(t('watch.row.watchedMarket', { market: row.market.label }));
  else if (!row.inFootprint) meta.push(t('watch.row.outside'));
  return meta;
}

/** The view's own address, so every state can link back to a feed the reader can read. */
function hrefOf(pathname: string, filters: WatchFilters, tab: WatchTab): string {
  const search = searchOf(filters, tab);
  return search === '' ? pathname : `${pathname}?${search}`;
}

export function WatchFeedScreen() {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = filtersFrom(params);
  const tab = tabFrom(params);
  // The phrase in the box, and the phrase the feed was last read with.
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');
  const query = queryOf(filters, search);
  const onCoverage = tab === COVERAGE_TAB;
  // The Coverage tab has no feed of its own, so neither read is made while it
  // is open: a screen never asks for what it cannot show.
  const feed = useChangeFeed({ ...query, tab: onCoverage ? TAB_CATEGORY.triage : TAB_CATEGORY[tab] }, !onCoverage);
  const triage = useTriageCount(query, tab !== 'triage' && !onCoverage);

  const go = (next: WatchFilters, nextTab: WatchTab) => router.replace(hrefOf(pathname, next, nextTab));

  const pages = feed.data?.pages ?? [];
  const items = pages.flatMap((page) => page.items);
  const total = pages[0]?.total ?? 0;
  const forbidden = forbiddenFrom(feed.error);

  // The count is part of the triage tab's own words, as the card writes it:
  // "Needs triage (3)". On that tab it is the feed's own total; anywhere else
  // it is one small read of the same route. It is never a count of the page.
  const triageCount = tab === 'triage' ? (feed.isSuccess ? total : undefined) : triage.data?.total;
  const tabs: TabDef[] = [
    ...TAB_KEYS.map((key) => ({
      id: key,
      label: key === 'triage' && triageCount !== undefined ? t('watch.tab.withCount', { label: t(TAB_LABEL_KEY[key]), count: triageCount }) : t(TAB_LABEL_KEY[key]),
    })),
    { id: COVERAGE_TAB, label: t('watch.tab.coverage') },
  ];
  // One fixed moment for every row of this render, so two rows can never
  // disagree about how many days are left.
  const today = new Date();

  return (
    <>
      <PageHead title={t('watch.title')} lede={t('watch.lede')} />
      <Tabs tabs={tabs} current={tab} onSelect={(id) => go(filters, isTab(id) ? id : 'triage')} />

      {tab === COVERAGE_TAB ? (
        <TabPanel id={COVERAGE_TAB}>
          <SourceCoverageTab active />
        </TabPanel>
      ) : (
        <TabPanel id={tab}>
          <WatchFilterBar
            filters={filters}
            draft={draft}
            onChange={(patch) => go({ ...filters, ...patch }, tab)}
            onDraft={setDraft}
            onSearch={() => setSearch(draft)}
          />

          {feed.isPending ? (
            <LoadingState rows={3} />
          ) : forbidden !== null ? (
            <RestrictedScreen {...forbidden} />
          ) : feed.isError ? (
            <ErrorState title={t('watch.errorTitle')} onRetry={() => void feed.refetch()} />
          ) : items.length === 0 ? (
            <FeedEmpty
              filters={filters}
              search={search}
              tab={tab}
              pathname={pathname}
              onClear={() => {
                setDraft('');
                setSearch('');
              }}
            />
          ) : (
            <div className="grid gap-2" data-change-rows="">
              {items.map((row) => (
                <ChangeFeedRow key={row.id} row={row} today={today} />
              ))}
            </div>
          )}

          {items.length > 0 ? (
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <p className="text-meta text-muted">{t('watch.showing', { shown: items.length, total })}</p>
              {feed.hasNextPage === true ? (
                <Button variant="outline" size="small" disabled={feed.isFetchingNextPage} onClick={() => void feed.fetchNextPage()}>
                  {t('watch.showMore')}
                </Button>
              ) : null}
            </div>
          ) : null}
        </TabPanel>
      )}
    </>
  );
}

function FeedEmpty({
  filters,
  search,
  tab,
  pathname,
  onClear,
}: {
  filters: WatchFilters;
  search: string;
  tab: TabKey;
  pathname: string;
  onClear: () => void;
}) {
  const t = useT();
  if (isNarrowed(filters, search)) {
    return (
      <EmptyState
        title={t('watch.empty.filters.title')}
        body={t('watch.empty.filters.body')}
        action={{ label: t('watch.filter.clear'), href: hrefOf(pathname, EMPTY_FILTERS, tab), onClick: onClear }}
      />
    );
  }
  if (tab !== 'triage') return <EmptyState title={t('watch.empty.tab.title')} body={t('watch.empty.tab.body')} />;
  return (
    <EmptyState
      title={t('watch.empty.triage.title')}
      body={t('watch.empty.triage.body')}
      action={{ label: t('watch.empty.triage.action'), href: hrefOf(pathname, { ...EMPTY_FILTERS, scope: 'all' }, tab) }}
    />
  );
}
