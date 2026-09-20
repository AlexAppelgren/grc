'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { InventoryFilterBar, REGIME, SERVICE, type InventoryFilters } from '@/components/inventory/InventoryFilters';
import { ObligationRow } from '@/components/inventory/ObligationRow';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useObligations } from '@/features/library/hooks';
import type { ObligationQuery } from '@/features/library/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate } from '@/shared/utils/format';

// /inventory, the obligations half (design/screens/tenant-inventory.html;
// INV-03, INV-04, FP-03, J-6). The filters live in the URL as keys and a
// plain date, so a view is linkable and "as of" is never today by accident.
// Nothing on this screen writes. The Instruments tab and the instrument
// filter come with the instrument reads.

/** The URL's filters. Unknown or missing parameters read as "not filtered". */
export function filtersFrom(params: { get(name: string): string | null }): InventoryFilters {
  return {
    regime: params.get('regime') ?? '',
    service: params.get('service') ?? '',
    dutyType: params.get('dutyType') ?? '',
    asOf: params.get('asOf') ?? '',
    outsideFootprint: params.get('outside') === 'true',
  };
}

/** The filters back into a query string: keys only, and nothing for a filter that is not set. */
export function searchOf(filters: InventoryFilters): string {
  const search = new URLSearchParams();
  if (filters.regime !== '') search.set('regime', filters.regime);
  if (filters.service !== '') search.set('service', filters.service);
  if (filters.dutyType !== '') search.set('dutyType', filters.dutyType);
  if (filters.asOf !== '') search.set('asOf', filters.asOf);
  if (filters.outsideFootprint) search.set('outside', 'true');
  return search.toString();
}

/** The read's query: a scope filter is a `dimension:key` term, the way the route reads it. */
export function queryOf(filters: InventoryFilters): ObligationQuery {
  const term = [
    ...(filters.regime === '' ? [] : [`${REGIME}:${filters.regime}`]),
    ...(filters.service === '' ? [] : [`${SERVICE}:${filters.service}`]),
  ];
  const query: ObligationQuery = {};
  if (term.length > 0) query.term = term;
  if (filters.dutyType !== '') query.dutyType = filters.dutyType;
  if (filters.asOf !== '') query.asOf = filters.asOf;
  if (filters.outsideFootprint) query.outsideFootprint = true;
  return query;
}

/** Whether the reader narrowed the list, which decides which empty state answers them. */
export function isNarrowed(filters: InventoryFilters): boolean {
  return filters.regime !== '' || filters.service !== '' || filters.dutyType !== '' || filters.asOf !== '';
}

export function InventoryScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const router = useRouter();
  const pathname = usePathname();
  const filters = filtersFrom(useSearchParams());
  const obligations = useObligations(queryOf(filters));

  const apply = (patch: Partial<InventoryFilters>) => {
    const search = searchOf({ ...filters, ...patch });
    router.replace(search === '' ? pathname : `${pathname}?${search}`);
  };

  const items = obligations.data?.items ?? [];
  const total = obligations.data?.total ?? 0;
  const outsideHref = `${pathname}?${searchOf({ ...filters, outsideFootprint: true })}`;

  return (
    <>
      <PageHead title={t('inventory.title')} lede={obligations.data === undefined ? undefined : t('inventory.count', { count: total })} />
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
          <EmptyState title={t('inventory.empty.inScope.title')} body={t('inventory.empty.inScope.body')} action={{ label: t('inventory.empty.inScope.action'), href: '/admin/footprint' }} />
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
