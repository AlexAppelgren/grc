'use client';

import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Field';
import { PER_PAGE_CHOICES, type PerPage } from '@/features/library/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// The inventory lists' pager (INV-01): which rows of the total are shown, the page before
// and after, and how many rows a page holds, every row included. The list owns the state;
// a new filter or page size starts again at the first page.

export function ListPager({
  total,
  shown,
  perPage,
  page,
  onPage,
  onPerPage,
}: {
  total: number;
  shown: number;
  perPage: PerPage;
  page: number;
  onPage: (page: number) => void;
  onPerPage: (perPage: PerPage) => void;
}) {
  const t = useT();
  if (total === 0) return null;
  const size = perPage === 'all' ? total : perPage;
  const from = perPage === 'all' ? 1 : page * size + 1;
  const to = perPage === 'all' ? shown : Math.min(from + shown - 1, total);
  const last = perPage === 'all' || to >= total;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-meta" data-list-pager="">
      <span className="text-muted" data-pager-range="">
        {t('inventory.pager.range', { from, to, total })}
      </span>
      {perPage === 'all' ? null : (
        <>
          <Button variant="outline" size="small" disabled={page === 0} onClick={() => onPage(page - 1)}>
            {t('inventory.pager.previous')}
          </Button>
          <Button variant="outline" size="small" disabled={last} onClick={() => onPage(page + 1)}>
            {t('inventory.pager.next')}
          </Button>
        </>
      )}
      <label className="ml-auto flex items-center gap-2">
        <span className="text-muted">{t('inventory.pager.perPage')}</span>
        <Select
          className="w-auto"
          value={String(perPage)}
          onChange={(event) => onPerPage(event.target.value === 'all' ? 'all' : (Number(event.target.value) as PerPage))}
        >
          {PER_PAGE_CHOICES.map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
          <option value="all">{t('inventory.pager.all')}</option>
        </Select>
      </label>
    </div>
  );
}
