'use client';

import { Button } from '@/components/ui/Button';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';

// A list's pager over the route's `limit`, `offset` and `total` (playbook 6.4):
// which rows of the total are shown, and the page before and after. A list in
// time order pages Newer and Older; any other list Previous and Next.

export function Pager({
  offset,
  limit,
  shown,
  total,
  inTime = false,
  range,
  className,
  onOffset,
}: {
  offset: number;
  limit: number;
  shown: number;
  total: number;
  inTime?: boolean;
  /** The range sentence, where the list words it its own way. */
  range?: string;
  className?: string;
  onOffset: (offset: number) => void;
}) {
  const t = useT();
  return (
    <div className={cn('mt-4 flex flex-wrap items-center justify-between gap-3 text-meta text-muted', className)} data-pager="">
      <span>{range ?? t('common.pager.range', { from: offset + 1, to: Math.min(offset + shown, total), total })}</span>
      <div className="flex gap-2">
        <Button variant="outline" size="small" disabled={offset === 0} onClick={() => onOffset(Math.max(0, offset - limit))}>
          {t(inTime ? 'common.pager.newer' : 'common.pager.previous')}
        </Button>
        <Button variant="outline" size="small" disabled={offset + limit >= total} onClick={() => onOffset(offset + limit)}>
          {t(inTime ? 'common.pager.older' : 'common.pager.next')}
        </Button>
      </div>
    </div>
  );
}
