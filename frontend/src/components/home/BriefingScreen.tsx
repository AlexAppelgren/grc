'use client';

import Link from 'next/link';

import { ComingUpPanel } from '@/components/home/ComingUpPanel';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen } from '@/components/ui/States';
import { weekKicker } from '@/features/home/briefing-presentation';
import { useBriefing, useCurrentBriefing } from '@/features/home/hooks';
import { presentLead } from '@/features/home/today-presentation';
import type { Briefing } from '@/features/home/types';
import { authorityAndDate, presentChangeRow } from '@/features/watch/change-presentation';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { RestrictedScreen, forbiddenFrom } from '@/shared/navigation/require-permission';
import { formatDateTime, type FormatContext } from '@/shared/utils/format';
import { hasProblemCode } from '@/shared/utils/problem';

// /briefing and /briefing/[weekStart] (design/screens/tenant-briefing.html;
// HOM-02, WAT-05, FP-03). The running week is computed live; a past week is
// read back from its snapshot, frozen the moment it was sent — the banner
// says so rather than letting a reader assume both are live.

function previousMonday(weekStart: string): string {
  const [year, month, day] = weekStart.split('-').map(Number);
  const previous = new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, (day ?? 1) - 7));
  return previous.toISOString().slice(0, 10);
}

function BriefingFeature({ briefing, ctx }: { briefing: Briefing; ctx: FormatContext }) {
  const t = useT();
  if (briefing.lead === null) return null;
  const lead = briefing.lead;
  return (
    <div className="mb-4 flex flex-col gap-3 rounded-card border border-line bg-surface p-5" data-lead-card={lead.stableKey}>
      <div className="flex flex-wrap items-center gap-2">
        <PillRow pills={presentLead(lead, t)} />
        <span className="text-meta text-muted">{authorityAndDate(lead, t, ctx)}</span>
      </div>
      <h2>{lead.title}</h2>
      {lead.case !== null && lead.case.soWhatText !== null && lead.case.soWhatText !== '' ? (
        <div className="rounded-control border border-line bg-subtle px-3 py-2.5 text-meta">
          {lead.case.soWhatConfirmed ? null : <span className="mb-0.5 block font-semibold text-brass">{t('watch.soWhat.aiDraft')}</span>}
          <span className="font-semibold text-fg">{t('watch.soWhat.label')}</span> <span>{lead.case.soWhatText}</span>
        </div>
      ) : null}
      <Link
        href={`/watch/${lead.id}`}
        prefetch={false}
        className="inline-flex h-9 w-fit items-center rounded-control border border-button bg-button px-4 font-medium text-on-button no-underline"
      >
        {t('briefing.openChange')}
      </Link>
    </div>
  );
}

function AlsoThisWeek({ items }: { items: Briefing['items'] }) {
  const t = useT();
  if (items.length === 0) return null;
  return (
    <Panel title={t('briefing.also.title')} data-also-this-week="">
      <div className="grid gap-4">
        {items.map((row) => (
          <div key={row.id} className="border-b border-line pb-4 last:border-0 last:pb-0" data-brief-item={row.stableKey}>
            <Link href={`/watch/${row.id}`} prefetch={false} className="font-semibold underline-offset-2 hover:underline">
              {row.title}
            </Link>
            {row.case !== null && row.case.soWhatText !== null && row.case.soWhatText !== '' ? (
              <p className="mt-1 text-meta text-muted">
                <span className="font-semibold text-fg">{t('watch.soWhat.label')}</span> {row.case.soWhatText}
              </p>
            ) : null}
            <div className="mt-1.5">
              <PillRow pills={presentChangeRow(row, 'row', t)} />
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export function BriefingScreen({ weekStart }: { weekStart?: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const current = useCurrentBriefing(weekStart === undefined);
  const past = useBriefing(weekStart ?? '', weekStart !== undefined);
  const query = weekStart === undefined ? current : past;
  const forbidden = forbiddenFrom(query.error);

  if (query.isPending) return <LoadingState rows={3} />;
  if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  if (weekStart !== undefined && hasProblemCode(query.error, 'not_found')) {
    return <NotFoundScreen body={t('briefing.notFound.body')} backHref="/briefing" backLabel={t('briefing.snapshot.seeCurrent')} />;
  }
  if (query.isError) return <ErrorState title={t('briefing.errorTitle')} onRetry={() => void query.refetch()} />;

  const briefing = query.data;
  const kicker = weekKicker(briefing.weekStart, briefing.weekEnd, t, ctx);
  const rest = briefing.lead === null ? briefing.items : briefing.items.filter((item) => item.id !== briefing.lead?.id);

  return (
    <>
      <PageHead kicker={kicker} title={t('briefing.title')} />

      {briefing.emailSentAt !== null ? (
        <Notice tone="plain" className="mb-4" data-snapshot-banner="">
          {t('briefing.snapshot.banner', { date: formatDateTime(briefing.emailSentAt, ctx) })}{' '}
          <Link href="/briefing" className="underline underline-offset-2">
            {t('briefing.snapshot.seeCurrent')}
          </Link>
        </Notice>
      ) : (
        <p className="mb-4 text-meta text-muted">{t('briefing.runningWeekNote')}</p>
      )}

      {briefing.items.length === 0 ? (
        <EmptyState title={t('briefing.empty.title')} body={t('briefing.empty.body')} />
      ) : (
        <>
          <BriefingFeature briefing={briefing} ctx={ctx} />
          <div className="grid gap-4 lg:grid-cols-[1.7fr_1fr] lg:items-start">
            <AlsoThisWeek items={rest} />
            <ComingUpPanel items={briefing.comingUp} ctx={ctx} />
          </div>
        </>
      )}

      <p className="mt-4">
        <Link href={`/briefing/${previousMonday(briefing.weekStart)}`} className="text-meta text-muted underline underline-offset-2">
          {t('briefing.previousWeek')}
        </Link>
      </p>
    </>
  );
}
