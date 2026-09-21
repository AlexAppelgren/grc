'use client';

import Link from 'next/link';

import { ToneDot } from '@/components/ui/ToneDot';
import { presentRoadmapItem } from '@/features/home/roadmap-presentation';
import type { RoadmapItem } from '@/features/home/types';
import { daysUntil, urgencyOf } from '@/features/watch/change-presentation';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate, type FormatContext } from '@/shared/utils/format';

// The "Coming up" panel (design/screens/tenant-today.html,
// tenant-briefing.html; HOM-01, HOM-02): the same short list Today and the
// briefing both draw from `GET /roadmap`'s own order, an urgency dot rather
// than a pill, and a link to the change. `roadmapCount` is Today's only:
// `HomeBriefing` carries no such count, so the briefing's panel omits it
// rather than showing a number from nowhere.

function ComingUpRow({ item, t, ctx, today }: { item: RoadmapItem; t: Translate; ctx: FormatContext; today: Date }) {
  const urgency = urgencyOf(item.urgency);
  const pills = presentRoadmapItem({ ourDeadline: item.kind === 'internal', ...(urgency === null ? {} : { urgency }) }, t);
  const days = daysUntil(item.date, today);
  return (
    <div className="flex gap-2.5 border-b border-line py-2.5 last:border-0" data-roadmap-item={item.id}>
      <ToneDot tone={pills[0]?.tone ?? 'information'} />
      <div className="min-w-0">
        <p className="flex flex-wrap items-baseline gap-x-1.5 text-meta text-muted">
          <span className="font-medium tabular-nums text-fg">{formatDate(item.date, ctx)}</span>
          {days !== null && days > 0 ? <span>{t('watch.row.daysLeft', { count: days })}</span> : null}
        </p>
        {item.changeId === null ? (
          <span className="font-medium">{item.title}</span>
        ) : (
          <Link href={`/watch/${item.changeId}`} prefetch={false} className="font-medium underline-offset-2 hover:underline">
            {item.title}
          </Link>
        )}
      </div>
    </div>
  );
}

export function ComingUpPanel({ items, roadmapCount, ctx }: { items: readonly RoadmapItem[]; roadmapCount?: number; ctx: FormatContext }) {
  const t = useT();
  const today = new Date();
  return (
    <div className="flex h-full flex-col rounded-card border border-line bg-surface p-4" data-coming-up="">
      <h2 className="mb-3">{t('today.comingUp.title')}</h2>
      {items.length === 0 ? (
        <p className="text-meta text-muted" data-empty-state="">
          {t('today.comingUp.empty')}
        </p>
      ) : (
        <div>
          {items.map((item) => (
            <ComingUpRow key={item.id} item={item} t={t} ctx={ctx} today={today} />
          ))}
        </div>
      )}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 pt-3">
        <Link href="/roadmap" className="text-body font-medium underline underline-offset-2">
          {t('today.comingUp.roadmapLink')}
        </Link>
        {roadmapCount !== undefined ? <span className="text-meta text-muted">{t('today.comingUp.count', { count: roadmapCount })}</span> : null}
      </div>
    </div>
  );
}
