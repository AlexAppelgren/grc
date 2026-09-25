'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useState, type ReactNode } from 'react';

import { InstrumentFilterBar, InventoryFilterBar, REGIME, SCOPE_VALUES, SERVICE, ScopeControl, type InstrumentFilters, type InventoryFilters } from '@/components/inventory/InventoryFilters';
import { InstrumentRow } from '@/components/inventory/InstrumentRow';
import { ObligationRow } from '@/components/inventory/ObligationRow';
import { SearchHitRow } from '@/components/inventory/SearchHitRow';
import { NavIcon } from '@/components/shell/NavIcon';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { TabPanel, Tabs } from '@/components/ui/Tabs';
import { useFormatContext } from '@/features/identity/hooks';
import { useInstruments, useObligations } from '@/features/library/hooks';
import type { InstrumentQuery, ObligationQuery, ScopeFilter } from '@/features/library/types';
import { useSearchResults } from '@/features/search/hooks';
import type { SearchRequestBody } from '@/features/search/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { findDestination, unlocks } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';

// /inventory (design/screens/tenant-inventory.html; INV-01, INV-03, INV-04,
// FP-03, SRC-01, SRC-02, J-6, D-103). The filters live in the URL as keys and a
// plain date, so a view is linkable and "as of" is never today by accident.
// Nothing on this screen writes. Obligations and Instruments are two tabs of the
// one screen, switched by the `tab` query parameter so a link to either is
// bookmarkable; the scope sits at the end of the tab row because it applies to both.
//
// The search bar is the product's search (D-103): on the Obligations tab it runs the
// hybrid search over obligations and provisions inside the scope and every filter
// that is set; on the Instruments tab it finds instruments by reference or name.
// What is typed is the bank's own words, so it lives in component state alone and
// never reaches the address bar; Enter runs it.

export type InventoryTab = 'obligations' | 'instruments';

/** The URL's tab; anything but "instruments" reads as the default. */
export function tabFrom(params: { get(name: string): string | null }): InventoryTab {
  return params.get('tab') === 'instruments' ? 'instruments' : 'obligations';
}

/** The URL's scope; anything but one of the three values reads as the default, "My scope". */
function scopeFrom(value: string | null): ScopeFilter {
  return SCOPE_VALUES.find((scope) => scope === value) ?? 'in';
}

/** The URL's filters. Unknown or missing parameters read as "not filtered". */
export function filtersFrom(params: { get(name: string): string | null }): InventoryFilters {
  return {
    instrument: params.get('instrument') ?? '',
    regime: params.get('regime') ?? '',
    service: params.get('service') ?? '',
    dutyType: params.get('dutyType') ?? '',
    asOf: params.get('asOf') ?? '',
    scope: scopeFrom(params.get('scope')),
  };
}

/** The filters back into a query string: keys only, and nothing for a filter that is not set. */
export function searchOf(tab: InventoryTab, filters: InventoryFilters): string {
  const search = new URLSearchParams();
  if (tab === 'instruments') search.set('tab', 'instruments');
  if (filters.instrument !== '') search.set('instrument', filters.instrument);
  if (filters.regime !== '') search.set('regime', filters.regime);
  if (filters.service !== '') search.set('service', filters.service);
  if (filters.dutyType !== '') search.set('dutyType', filters.dutyType);
  if (filters.asOf !== '') search.set('asOf', filters.asOf);
  if (filters.scope !== 'in') search.set('scope', filters.scope);
  return search.toString();
}

/** A scope filter as the routes read it: a `dimension:key` term. */
function termsOf(filters: InventoryFilters): string[] {
  return [...(filters.regime === '' ? [] : [`${REGIME}:${filters.regime}`]), ...(filters.service === '' ? [] : [`${SERVICE}:${filters.service}`])];
}

/** The obligations read's query. */
export function queryOf(filters: InventoryFilters): ObligationQuery {
  const term = termsOf(filters);
  const query: ObligationQuery = {};
  if (filters.instrument !== '') query.instrument = filters.instrument;
  if (term.length > 0) query.term = term;
  if (filters.dutyType !== '') query.dutyType = filters.dutyType;
  if (filters.asOf !== '') query.asOf = filters.asOf;
  if (filters.scope !== 'in') query.footprint = filters.scope;
  return query;
}

/** The search the bar runs: the list's own filters and scope, over obligations and provisions only. */
export function searchRequestOf(filters: InventoryFilters, q: string): SearchRequestBody {
  const term = termsOf(filters);
  const body: SearchRequestBody = {
    q,
    limit: 20,
    types: ['obligation', 'provision'],
    filters: {
      footprint: filters.scope,
      ...(filters.instrument === '' ? {} : { instrument: filters.instrument }),
      ...(term.length === 0 ? {} : { term }),
      ...(filters.dutyType === '' ? {} : { dutyType: filters.dutyType }),
    },
  };
  if (filters.asOf !== '') body.asOf = filters.asOf;
  return body;
}

/** The instruments read's query: regime, q and footprint only (chunk3-rest default). */
export function instrumentQueryOf(filters: InstrumentFilters, q = ''): InstrumentQuery {
  const query: InstrumentQuery = {};
  if (filters.regime !== '') query.regime = filters.regime;
  if (q !== '') query.q = q;
  if (filters.scope !== 'in') query.footprint = filters.scope;
  return query;
}

/** Whether the reader narrowed the list, which decides which empty state answers them. */
export function isNarrowed(filters: InventoryFilters): boolean {
  return filters.instrument !== '' || filters.regime !== '' || filters.service !== '' || filters.dutyType !== '' || filters.asOf !== '';
}

/** The search bar (foundations.md "Search field"): Enter runs it, Clear returns the list. */
function SearchBar({ draft, placeholder, onDraft, onRun, onClear }: { draft: string; placeholder: string; onDraft: (next: string) => void; onRun: () => void; onClear: () => void }) {
  const t = useT();
  return (
    <form
      role="search"
      className="flex h-9 max-w-[560px] min-w-0 flex-[1_1_320px] items-center gap-2 rounded-control border border-line-strong bg-surface pr-1 pl-2.5 text-muted focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-focus max-lg:max-w-none pointer-coarse:h-11"
      onSubmit={(event) => {
        event.preventDefault();
        onRun();
      }}
    >
      <NavIcon id="search" />
      <input
        type="search"
        aria-label={t('inventory.search.label')}
        placeholder={placeholder}
        value={draft}
        onChange={(event) => onDraft(event.target.value)}
        className="h-full min-w-0 flex-1 bg-transparent text-body text-fg outline-none placeholder:text-muted placeholder:italic [&::-webkit-search-cancel-button]:appearance-none"
      />
      {draft === '' ? null : (
        <button type="button" aria-label={t('inventory.search.clear')} onClick={onClear} className="inline-flex size-7 items-center justify-center rounded-control text-muted hover:text-fg">
          <NavIcon id="close" />
        </button>
      )}
    </form>
  );
}

function ObligationsTab({ filters, apply, pathname, bar, query }: { filters: InventoryFilters; apply: (patch: Partial<InventoryFilters>) => void; pathname: string; bar: ReactNode; query: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const permissions = usePermissions();
  const obligations = useObligations(queryOf(filters));
  const results = useSearchResults(query === '' ? null : searchRequestOf(filters, query));
  const items = obligations.data?.items ?? [];
  const hits = results.data?.items ?? [];
  const total = obligations.data?.total ?? 0;
  const allHref = `${pathname}?${searchOf('obligations', { ...filters, scope: 'all' })}`;
  const allAction = filters.scope === 'all' ? undefined : { label: t('library.scope.all'), href: allHref };
  // The way to the regulatory scope shows only to someone the scope page opens for.
  const scopePage = findDestination('admin-footprint');
  const scopeAction =
    scopePage !== undefined && unlocks(scopePage.anyOfPermissions, permissions ?? []) ? { label: t('inventory.empty.inScope.action'), href: scopePage.href } : undefined;

  let body: ReactNode;
  if (query !== '') {
    body = results.isPending ? (
      <LoadingState rows={3} />
    ) : results.isError ? (
      <ErrorState title={t('inventory.search.errorTitle')} onRetry={() => void results.refetch()} />
    ) : hits.length === 0 ? (
      <EmptyState title={t('inventory.search.noMatch.title')} body={t('inventory.search.noMatch.body')} action={allAction} />
    ) : (
      <>
        <p className="mb-2.5 text-meta text-muted" role="status">
          {t('inventory.search.count', { count: hits.length })}
        </p>
        <div className="grid gap-2" data-search-rows="">
          {hits.map((hit) => (
            <SearchHitRow key={hit.id} hit={hit} query={query} t={t} ctx={ctx} />
          ))}
        </div>
      </>
    );
  } else if (obligations.isPending) {
    body = <LoadingState rows={3} />;
  } else if (obligations.isError) {
    body = <ErrorState title={t('inventory.errorTitle')} onRetry={() => void obligations.refetch()} />;
  } else if (items.length === 0) {
    body =
      filters.scope === 'watched' ? (
        <EmptyState title={t('library.empty.watched.title')} body={t('library.empty.watched.body')} />
      ) : isNarrowed(filters) ? (
        <EmptyState title={t('inventory.empty.noMatch.title')} body={t('inventory.empty.noMatch.body')} action={allAction} />
      ) : (
        <EmptyState title={t('inventory.empty.inScope.title')} body={t('inventory.empty.inScope.body')} action={scopeAction} />
      );
  } else {
    body = (
      <>
        <div className="grid gap-2" data-obligation-rows="">
          {items.map((obligation) => (
            <ObligationRow key={obligation.id} obligation={obligation} watched={filters.scope === 'watched'} />
          ))}
        </div>
        {items.length < total ? <p className="mt-3 text-meta text-muted">{t('inventory.showingFirst', { shown: items.length, total })}</p> : null}
      </>
    );
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2" data-inventory-filters="">
        {unlocks(['search.use'], permissions ?? []) ? bar : null}
        <InventoryFilterBar filters={filters} onChange={apply} />
      </div>

      {filters.asOf === '' ? null : (
        <Notice className="flex flex-wrap items-center gap-2" data-as-of={filters.asOf}>
          <span>{t('inventory.asOfBanner', { date: formatDate(filters.asOf, ctx) })}</span>
          <Button variant="ghost" size="small" onClick={() => apply({ asOf: '' })}>
            {t('inventory.backToToday')}
          </Button>
        </Notice>
      )}

      {body}
    </>
  );
}

function InstrumentsTab({ filters, apply, pathname, bar, query }: { filters: InventoryFilters; apply: (patch: Partial<InventoryFilters>) => void; pathname: string; bar: ReactNode; query: string }) {
  const t = useT();
  const instruments = useInstruments(instrumentQueryOf(filters, query));
  const items = instruments.data?.items ?? [];
  const narrowed = filters.regime !== '' || query !== '';
  const allHref = `${pathname}?${searchOf('instruments', { ...filters, scope: 'all' })}`;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2" data-instrument-filters="">
        {bar}
        <InstrumentFilterBar filters={filters} onChange={apply} />
      </div>

      {instruments.isPending ? (
        <LoadingState rows={3} />
      ) : instruments.isError ? (
        <ErrorState title={t('inventory.errorTitle')} onRetry={() => void instruments.refetch()} />
      ) : items.length === 0 ? (
        filters.scope === 'watched' ? (
          <EmptyState title={t('library.empty.watched.title')} body={t('library.empty.watchedInstruments.body')} />
        ) : (
          <EmptyState
            title={t('inventory.empty.noInstrumentMatch.title')}
            body={t('inventory.empty.noInstrumentMatch.body')}
            action={narrowed || filters.scope === 'all' ? undefined : { label: t('library.scope.all'), href: allHref }}
          />
        )
      ) : (
        <div className="grid gap-2" data-instrument-rows="">
          {items.map((instrument) => (
            <InstrumentRow key={instrument.id} instrument={instrument} />
          ))}
        </div>
      )}
    </>
  );
}

export function InventoryScreen() {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = tabFrom(params);
  const filters = filtersFrom(params);
  // What is in the box, and what the last search ran with.
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const obligationCount = useObligations(queryOf(filters));
  // The instruments' count is the instruments tab's lede and nothing else, so the
  // obligations tab never asks for it beside its own rows (NFR-02).
  const instrumentCount = useInstruments(instrumentQueryOf(filters, query), undefined, tab === 'instruments');

  const apply = (patch: Partial<InventoryFilters>) => {
    const search = searchOf(tab, { ...filters, ...patch });
    router.replace(search === '' ? pathname : `${pathname}?${search}`);
  };
  const selectTab = (next: string) => {
    const search = searchOf(next === 'instruments' ? 'instruments' : 'obligations', filters);
    router.replace(search === '' ? pathname : `${pathname}?${search}`);
  };

  let lede: string | undefined;
  if (tab === 'instruments') {
    if (instrumentCount.data !== undefined) lede = t('inventory.instrumentCount', { count: instrumentCount.data.total });
  } else if (obligationCount.data !== undefined) {
    lede = t('inventory.count', { count: obligationCount.data.total });
  }

  const bar = (
    <SearchBar
      draft={draft}
      placeholder={t(tab === 'instruments' ? 'inventory.search.instrumentsPlaceholder' : 'inventory.search.placeholder')}
      onDraft={setDraft}
      onRun={() => setQuery(draft.trim())}
      onClear={() => {
        setDraft('');
        setQuery('');
      }}
    />
  );

  return (
    <>
      <PageHead
        title={t('inventory.title')}
        lede={lede}
        actions={
          <Link href="/inventory/updates" className="font-medium underline" data-library-updates-link="">
            {t('inventory.libraryUpdatesLink')}
          </Link>
        }
      />
      <Tabs
        tabs={[
          { id: 'obligations', label: t('inventory.tabs.obligations') },
          { id: 'instruments', label: t('inventory.tabs.instruments') },
        ]}
        current={tab}
        onSelect={selectTab}
        end={<ScopeControl value={filters.scope} onChange={(scope) => apply({ scope })} />}
      />
      {tab === 'obligations' ? (
        <TabPanel id="obligations">
          <ObligationsTab filters={filters} apply={apply} pathname={pathname} bar={bar} query={query} />
        </TabPanel>
      ) : (
        <TabPanel id="instruments">
          <InstrumentsTab filters={filters} apply={apply} pathname={pathname} bar={bar} query={query} />
        </TabPanel>
      )}
    </>
  );
}
