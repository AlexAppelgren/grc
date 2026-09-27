'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useMyWork } from '@/features/my-work/hooks';
import { MyCommentsPanel } from '@/features/my-work/MyCommentsPanel';
import { SECTIONS, kindLabel, permissionLimitedLines, presentWorkItem, tenantToday, workHref, workReasons, workWhen } from '@/features/my-work/my-work-presentation';
import { initialScope, storedScope, storeScope } from '@/features/my-work/scope';
import type { WorkItem, WorkScope } from '@/features/my-work/types';
import { useT } from '@/shared/i18n/LocaleProvider';

// /work (design/screens/tenant-my-work.html; HOM-05, AC-HOM1, COL-04, J-9).
// Four sections in a fixed order, each row in the first it qualifies for;
// rows and counts are the server's permission-filtered set, and a kind the
// reader cannot open is named above the sections. Decisions stay on Today:
// one line links there. A department head gets a switch between their own
// work and each department they head, remembered on this device.

const DOT = "before:mx-1.5 before:content-['·']";

function itemKey(item: WorkItem): string {
  const { obligationId, changeId, internalItemId } = item.subject;
  return `${item.bucket}:${item.itemKind}:${obligationId ?? changeId ?? internalItemId}:${item.entity?.id ?? ''}`;
}

function WorkRow({ item, scope, today }: { item: WorkItem; scope: WorkScope['scope']; today: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const href = workHref(item);
  const when = workWhen(item, today, ctx, t);
  const pills = presentWorkItem(item);
  return (
    <li className="rounded-card border border-line bg-surface px-4 py-3" data-work-item={item.itemKind}>
      {pills.length > 0 ? (
        <div className="mb-1.5">
          <PillRow pills={pills} />
        </div>
      ) : null}
      <h3>
        {href === null ? (
          item.subject.title
        ) : (
          <Link href={href} prefetch={false} className="no-underline hover:underline">
            {item.subject.title}
          </Link>
        )}
      </h3>
      <p className="mt-1 text-meta text-muted">
        <span>{kindLabel(item.itemKind, t)}</span>
        <span className={`${DOT} font-medium text-fg tabular-nums`}>{when.date}</span>
        {when.days === null ? null : <span className={DOT}>{when.days}</span>}
        {item.entity === null ? null : <span className={DOT}>{t('work.entity', { name: item.entity.name })}</span>}
      </p>
      <p className="mt-1 text-meta text-muted" data-work-reasons="">
        {workReasons(item, scope, t).map((reason, i) => (
          <span key={reason} className={i === 0 ? undefined : DOT}>
            {reason}
          </span>
        ))}
      </p>
    </li>
  );
}

export function MyWorkScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const { me } = useSession();
  const router = useRouter();
  const addressed = useSearchParams().get('unit');
  const headOf = me?.headOf ?? [];
  // Until the reader picks a view, the one they open on follows the session as it loads.
  const [chosen, setChosen] = useState<WorkScope | null>(null);
  const scope = chosen ?? initialScope(addressed, storedScope(), headOf);
  const query = useMyWork(scope);

  // Mine, each department the reader heads, and a department opened by its
  // address that they do not head. One option needs no switch.
  const options: { scope: WorkScope; label: string }[] = [
    { scope: { scope: 'mine' }, label: t('work.scope.mine') },
    ...headOf.map((unit) => ({ scope: { scope: 'unit', unit: unit.id } as WorkScope, label: unit.name })),
  ];
  if (scope.scope === 'unit' && !headOf.some((unit) => unit.id === scope.unit)) {
    options.push({ scope, label: t('work.scope.department') });
  }
  const current = scope.scope === 'unit' ? scope.unit : 'mine';

  function choose(next: WorkScope) {
    setChosen(next);
    storeScope(next);
    if (addressed !== null) router.replace('/work');
  }

  let body;
  if (query.isPending) {
    body = <LoadingState rows={3} />;
  } else if (query.isError) {
    body = <ErrorState title={t('work.errorTitle')} onRetry={() => void query.refetch()} />;
  } else {
    const first = query.data.pages[0];
    const items = query.data.pages.flatMap((page) => page.items);
    const limited = permissionLimitedLines(first?.permissionLimited ?? [], t);
    const counts = first?.counts ?? { overdue: 0, dueSoon: 0, aware: 0, open: 0 };
    const nothing = counts.overdue + counts.dueSoon + counts.aware + counts.open === 0 && limited.length === 0;
    const today = tenantToday(new Date(), ctx.timeZone);
    body = nothing ? (
      <EmptyState title={t('work.empty.title')} body={t('work.empty.body')} action={{ label: t('work.decide.action'), href: '/' }} />
    ) : (
      <>
        {limited.map((line) => (
          <p key={line} className="mb-4 max-w-[72ch] text-meta text-muted" data-permission-limited="">
            {line}
          </p>
        ))}
        {SECTIONS.map((section) => {
          const rows = items.filter((item) => item.bucket === section.bucket);
          return (
            <section key={section.bucket} className="mb-6" data-work-section={section.bucket}>
              <div className="mb-2 flex items-baseline gap-2">
                <h2>{t(section.title)}</h2>
                <span className="text-meta text-muted tabular-nums">{counts[section.count]}</span>
              </div>
              {rows.length === 0 ? (
                <p className="text-meta text-muted">{t(section.empty)}</p>
              ) : (
                <ul className="grid list-none gap-2">
                  {rows.map((item) => (
                    <WorkRow key={itemKey(item)} item={item} scope={scope.scope} today={today} />
                  ))}
                </ul>
              )}
            </section>
          );
        })}
        {query.hasNextPage ? (
          <Button variant="outline" size="small" className="mb-6" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            {t('work.showMore')}
          </Button>
        ) : null}
        <div className="mb-6 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-2 rounded-control bg-subtle px-3 py-2.5" data-decide-line="">
          <p>{t('work.decide.line')}</p>
          <Link href="/" className="font-medium underline">
            {t('work.decide.action')}
          </Link>
        </div>
      </>
    );
  }

  return (
    <div>
      <PageHead title={t('work.title')} lede={t('work.lede')} />
      {options.length > 1 ? (
        <div role="group" aria-label={t('work.scope.label')} className="mb-5 flex flex-wrap gap-2">
          {options.map((option) => {
            const id = option.scope.scope === 'unit' ? option.scope.unit : 'mine';
            return (
              <Chip key={id} pressed={id === current} onClick={() => choose(option.scope)}>
                {option.label}
              </Chip>
            );
          })}
        </div>
      ) : null}
      {body}
      <MyCommentsPanel />
    </div>
  );
}
