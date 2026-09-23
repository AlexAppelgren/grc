'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { InstrumentFilterBar, InventoryFilterBar, REGIME, SERVICE, type InstrumentFilters, type InventoryFilters } from '@/components/inventory/InventoryFilters';
import { InstrumentRow } from '@/components/inventory/InstrumentRow';
import { ObligationRow } from '@/components/inventory/ObligationRow';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { TabPanel, Tabs } from '@/components/ui/Tabs';
import { useFormatContext } from '@/features/identity/hooks';
import { useInstruments, useObligations } from '@/features/library/hooks';
import type { InstrumentQuery, ObligationQuery } from '@/features/library/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { findDestination, unlocks } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';

// /inventory (design/screens/tenant-inventory.html; INV-01, INV-03, INV-04,
// FP-03, J-6). The filters live in the URL as keys and a plain date, so a
// view is linkable and "as of" is never today by accident. Nothing on this
// screen writes. Obligations and Instruments are two tabs of the one screen,
// switched by the `tab` query parameter so a link to either is bookmarkable.

export type InventoryTab = 'obligations' | 'instruments';

/** The URL's tab; anything but "instruments" reads as the default. */
export function tabFrom(params: { get(name: string): string | null }): InventoryTab {
  return params.get('tab') === 'instruments' ? 'instruments' : 'obligations';
}

/** The URL's filters. Unknown or missing parameters read as "not filtered". */
export function filtersFrom(params: { get(name: string): string | null }): InventoryFilters {
  return {
    instrument: params.get('instrument') ?? '',
    regime: params.get('regime') ?? '',
    service: params.get('service') ?? '',
    dutyType: params.get('dutyType') ?? '',
    asOf: params.get('asOf') ?? '',
    outsideFootprint: params.get('outside') === 'true',
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
  if (filters.outsideFootprint) search.set('outside', 'true');
  return search.toString();
}

/** The obligations read's query: a scope filter is a `dimension:key` term, the way the route reads it. */
export function queryOf(filters: InventoryFilters): ObligationQuery {
  const term = [
    ...(filters.regime === '' ? [] : [`${REGIME}:${filters.regime}`]),
    ...(filters.service === '' ? [] : [`${SERVICE}:${filters.service}`]),
  ];
  const query: ObligationQuery = {};
  if (filters.instrument !== '') query.instrument = filters.instrument;
  if (term.length > 0) query.term = term;
  if (filters.dutyType !== '') query.dutyType = filters.dutyType;
  if (filters.asOf !== '') query.asOf = filters.asOf;
  if (filters.outsideFootprint) query.outsideFootprint = true;
  return query;
}

/** The instruments read's query: regime, q and outsideFootprint only (chunk3-rest default). */
export function instrumentQueryOf(filters: InstrumentFilters): InstrumentQuery {
  const query: InstrumentQuery = {};
  if (filters.regime !== '') query.regime = filters.regime;
  if (filters.outsideFootprint) query.outsideFootprint = true;
  return query;
}

/** Whether the reader narrowed the list, which decides which empty state answers them. */
export function isNarrowed(filters: InventoryFilters): boolean {
  return filters.instrument !== '' || filters.regime !== '' || filters.service !== '' || filters.dutyType !== '' || filters.asOf !== '';
}

function ObligationsTab({ filters, apply, pathname }: { filters: InventoryFilters; apply: (patch: Partial<InventoryFilters>) => void; pathname: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const permissions = usePermissions();
  const obligations = useObligations(queryOf(filters));
  const items = obligations.data?.items ?? [];
  const total = obligations.data?.total ?? 0;
  const outsideHref = `${pathname}?${searchOf('obligations', { ...filters, outsideFootprint: true })}`;
  // The way to the regulatory scope shows only to someone the scope page opens for.
  const scope = findDestination('admin-footprint');
  const scopeAction =
    scope !== undefined && unlocks(scope.anyOfPermissions, permissions ?? []) ? { label: t('inventory.empty.inScope.action'), href: scope.href } : undefined;

  return (
    <>
      <InventoryFilterBar filters={filters} onChange={apply} />

      {filters.asOf === '' ? null : (
        <Notice className="flex flex-wrap items-center gap-2" data-as-of={filters.asOf}>
          <span>{t('inventory.asOfBanner', { date: formatDate(filters.asOf, ctx) })}</span>
          <Button variant="ghost" size="small" onClick={() => apply({ asOf: '' })}>
            {t('inventory.backToToday')}
          </Button>
        </Notice>
      )}

      {obligations.isPending ? (
        <LoadingState rows={3} />
      ) : obligations.isError ? (
        <ErrorState title={t('inventory.errorTitle')} onRetry={() => void obligations.refetch()} />
      ) : items.length === 0 ? (
        isNarrowed(filters) ? (
          <EmptyState
            title={t('inventory.empty.noMatch.title')}
            body={t('inventory.empty.noMatch.body')}
            action={filters.outsideFootprint ? undefined : { label: t('inventory.showOutside'), href: outsideHref }}
          />
        ) : (
          <EmptyState title={t('inventory.empty.inScope.title')} body={t('inventory.empty.inScope.body')} action={scopeAction} />
        )
      ) : (
        <div className="grid gap-2" data-obligation-rows="">
          {items.map((obligation) => (
            <ObligationRow key={obligation.id} obligation={obligation} />
          ))}
        </div>
      )}

      {items.length < total ? <p className="mt-3 text-meta text-muted">{t('inventory.showingFirst', { shown: items.length, total })}</p> : null}
    </>
  );
}

function InstrumentsTab({ filters, apply, pathname }: { filters: InventoryFilters; apply: (patch: Partial<InventoryFilters>) => void; pathname: string }) {
  const t = useT();
  const instruments = useInstruments(instrumentQueryOf(filters));
  const items = instruments.data?.items ?? [];
  const narrowed = filters.regime !== '';
  const outsideHref = `${pathname}?${searchOf('instruments', { ...filters, outsideFootprint: true })}`;

  return (
    <>
      <InstrumentFilterBar filters={filters} onChange={apply} />

      {instruments.isPending ? (
        <LoadingState rows={3} />
      ) : instruments.isError ? (
        <ErrorState title={t('inventory.errorTitle')} onRetry={() => void instruments.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          title={t('inventory.empty.noInstrumentMatch.title')}
          body={t('inventory.empty.noInstrumentMatch.body')}
          action={narrowed || filters.outsideFootprint ? undefined : { label: t('inventory.showOutside'), href: outsideHref }}
        />
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
  const obligationCount = useObligations(queryOf(filters));
  const instrumentCount = useInstruments(instrumentQueryOf(filters));

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
      />
      {tab === 'obligations' ? (
        <TabPanel id="obligations">
          <ObligationsTab filters={filters} apply={apply} pathname={pathname} />
        </TabPanel>
      ) : (
        <TabPanel id="instruments">
          <InstrumentsTab filters={filters} apply={apply} pathname={pathname} />
        </TabPanel>
      )}
    </>
  );
}
