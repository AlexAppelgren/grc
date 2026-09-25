'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { ToneDot } from '@/components/ui/ToneDot';
import { useFormatContext } from '@/features/identity/hooks';
import { useRoadmap } from '@/features/home/hooks';
import { presentRoadmapItem, roadmapOwner, roadmapSubjectHref, roadmapWhat, roadmapWhen } from '@/features/home/roadmap-presentation';
import type { Roadmap, RoadmapItem, RoadmapQuery } from '@/features/home/types';
import { urgencyOf } from '@/features/watch/change-presentation';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';
import type { FormatContext } from '@/shared/utils/format';

// /roadmap (design/screens/tenant-roadmap.html; HOM-03, FP-03). Every dated
// change the bank has open work on, by quarter, filtered by `kind` in the
// URL so a filtered view is linkable. A card expands in place — the detail
// panel below the roster — and never navigates; the link inside it does.
// One of the bank's own deadlines (a review, a gap's target, a certificate's
// expiry or audit, and the case workflow's deadlines and actions) reads "Our
// deadline", says what produced the date and names its owner and its record.
// The head links to the person's calendar feeds (HOM-04), which need the
// same grant as this page.

type Kind = RoadmapQuery['kind'] & string;
const KINDS: readonly Exclude<Kind, undefined>[] = ['all', 'regulatory', 'internal'];

function kindFrom(params: { get(name: string): string | null }): Exclude<Kind, undefined> {
  const raw = params.get('kind');
  return (KINDS as readonly string[]).includes(raw ?? '') ? (raw as Exclude<Kind, undefined>) : 'all';
}

const CHIP_LABEL_KEY = {
  all: 'roadmap.chip.all',
  regulatory: 'roadmap.chip.regulatory',
  internal: 'roadmap.chip.internal',
} as const;

/** "2026-Q4" -> "Q4 2026", from the message catalog and never a literal string. */
function quarterLabel(key: string, t: Translate): string {
  const [year, quarter] = key.split('-Q');
  return t('format.quarter', { quarter: quarter ?? '', year: year ?? '' });
}

function itemPills(item: RoadmapItem, t: Translate) {
  const urgency = urgencyOf(item.urgency);
  return presentRoadmapItem({ ourDeadline: item.kind === 'internal', ...(urgency === null ? {} : { urgency }) }, t);
}

function RoadmapCard({
  item,
  expanded,
  onToggle,
  t,
  ctx,
}: {
  item: RoadmapItem;
  expanded: boolean;
  onToggle: () => void;
  t: Translate;
  ctx: FormatContext;
}) {
  const pills = itemPills(item, t);
  return (
    <button
      type="button"
      aria-pressed={expanded}
      onClick={onToggle}
      data-roadmap-card={item.id}
      className={cn(
        'flex w-full items-start gap-2 rounded-card border-2 p-3 text-left',
        expanded ? 'border-fg bg-subtle' : 'border-line hover:border-line-strong',
      )}
    >
      <ToneDot tone={pills[0]?.tone ?? 'information'} />
      <span className="min-w-0">
        <span className="block font-medium tabular-nums">{roadmapWhen(item, ctx, new Date()).date}</span>
        <span className="block text-meta">{item.title}</span>
        <span className="block text-meta text-muted">
          {item.kind === 'internal' ? [t('pill.ourDeadline'), roadmapWhat(item.itemType, t), roadmapOwner(item.owner, t)].join(' · ') : t('roadmap.regulatoryDate')}
        </span>
      </span>
    </button>
  );
}

function RoadmapDetail({ item, t, ctx }: { item: RoadmapItem; t: Translate; ctx: FormatContext }) {
  const when = roadmapWhen(item, ctx, new Date());
  return (
    <div className="mt-4 rounded-card border border-line bg-surface p-4" data-roadmap-detail={item.id}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <PillRow pills={itemPills(item, t)} />
        <span className="text-meta text-muted">{when.date}</span>
        {when.daysLeft !== null ? <span className="text-meta text-muted">{t('watch.row.daysLeft', { count: when.daysLeft })}</span> : null}
      </div>
      <h2 className="mb-3">{item.title}</h2>
      {item.kind === 'internal' ? <OurDeadline item={item} t={t} /> : null}
      {item.changeId !== null ? (
        <Link
          href={`/watch/${item.changeId}`}
          prefetch={false}
          className="inline-flex h-9 items-center rounded-control border border-line-control bg-surface px-4 font-medium no-underline hover:hover-fill"
        >
          {t('roadmap.openChange')}
        </Link>
      ) : null}
    </div>
  );
}

function OurDeadline({ item, t }: { item: RoadmapItem; t: Translate }) {
  const href = roadmapSubjectHref(item.subject);
  const entity = item.subject?.entity ?? null;
  return (
    <>
      <dl className="mb-3 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1" data-our-deadline="">
        <dt className="text-muted">{t('roadmap.detail.what')}</dt>
        <dd>{roadmapWhat(item.itemType, t)}</dd>
        <dt className="text-muted">{t('roadmap.detail.owner')}</dt>
        <dd className="font-medium">{roadmapOwner(item.owner, t)}</dd>
        {entity !== null ? (
          <>
            <dt className="text-muted">{t('roadmap.detail.entity')}</dt>
            <dd>{entity.name}</dd>
          </>
        ) : null}
      </dl>
      {href !== null ? (
        <Link
          href={href}
          prefetch={false}
          className="inline-flex h-9 items-center rounded-control border border-line-control bg-surface px-4 font-medium no-underline hover:hover-fill"
        >
          {t('roadmap.openObligation')}
        </Link>
      ) : null}
    </>
  );
}

function QuarterRoster({
  data,
  expanded,
  onToggle,
  t,
  ctx,
}: {
  data: Roadmap;
  expanded: string | null;
  onToggle: (id: string) => void;
  t: Translate;
  ctx: FormatContext;
}) {
  const byQuarter = new Map<string, RoadmapItem[]>();
  for (const item of data.items) {
    const list = byQuarter.get(item.quarter);
    if (list === undefined) byQuarter.set(item.quarter, [item]);
    else list.push(item);
  }
  const expandedItem = data.items.find((item) => item.id === expanded) ?? null;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-roadmap-roster="">
        {data.quarters.map((quarter) => (
          <div key={quarter} className="min-w-0">
            <h2 className="mb-2 border-b-2 border-fg pb-2 text-title">{quarterLabel(quarter, t)}</h2>
            <div className="grid gap-2">
              {(byQuarter.get(quarter) ?? []).map((item) => (
                <RoadmapCard key={item.id} item={item} expanded={item.id === expanded} onToggle={() => onToggle(item.id)} t={t} ctx={ctx} />
              ))}
            </div>
          </div>
        ))}
      </div>
      {expandedItem !== null ? <RoadmapDetail item={expandedItem} t={t} ctx={ctx} /> : null}
    </>
  );
}

export function RoadmapScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const kind = kindFrom(params);
  const [expanded, setExpanded] = useState<string | null>(null);
  const query = useRoadmap(kind === 'all' ? {} : { kind });
  const forbidden = forbiddenFrom(query.error);

  const go = (next: Exclude<Kind, undefined>) => {
    setExpanded(null);
    router.replace(next === 'all' ? pathname : `${pathname}?kind=${next}`);
  };

  return (
    <>
      <PageHead
        title={t('roadmap.title')}
        lede={t('roadmap.lede')}
        actions={
          <Link
            href="/me/calendar-feeds"
            className="inline-flex h-9 items-center rounded-control border border-line-control bg-surface px-4 font-medium no-underline hover:hover-fill"
          >
            {t('roadmap.subscribe')}
          </Link>
        }
      />
      <div data-roadmap-filters="">
        <ChipRow className="mb-4">
          {KINDS.map((option) => (
            <Chip key={option} pressed={kind === option} onClick={() => go(option)}>
              {t(CHIP_LABEL_KEY[option])}
            </Chip>
          ))}
          {query.isSuccess ? (
            <span className="ml-auto text-meta text-muted">{t('roadmap.itemsShown', { count: query.data.items.length })}</span>
          ) : null}
        </ChipRow>
      </div>

      {query.isPending ? (
        <LoadingState rows={3} />
      ) : forbidden !== null ? (
        <RestrictedScreen {...forbidden} />
      ) : query.isError ? (
        <ErrorState title={t('roadmap.errorTitle')} onRetry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <EmptyState
          title={kind === 'internal' ? t('roadmap.empty.internal.title') : t('roadmap.empty.title')}
          body={kind === 'internal' ? t('roadmap.empty.internal.body') : t('roadmap.empty.body')}
        />
      ) : (
        <QuarterRoster data={query.data} expanded={expanded} onToggle={(id) => setExpanded(expanded === id ? null : id)} t={t} ctx={ctx} />
      )}
    </>
  );
}
