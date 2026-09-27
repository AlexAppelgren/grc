'use client';

import Link from 'next/link';

import { ComingUpPanel } from '@/components/home/ComingUpPanel';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { Panel } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useCurrentBriefing, useHome } from '@/features/home/hooks';
import { presentStanding, type Standing } from '@/features/home/standing-presentation';
import { decideNowLines, presentLead } from '@/features/home/today-presentation';
import type { Briefing, Home } from '@/features/home/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import type { VocabularyRow } from '@/features/vocabularies/types';
import { authorityAndDate } from '@/features/watch/change-presentation';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { findDestination, unlocks } from '@/shared/navigation/registry';
import { RestrictedScreen, forbiddenFrom, usePermissions } from '@/shared/navigation/require-permission';
import { formatLongDate, type FormatContext } from '@/shared/utils/format';

// / (design/screens/tenant-today.html; HOM-01, HOM-02). "Coming up" is the
// same short list on a phone and on a desktop; the lead card marks the
// week's most urgent open change with the brand pill "Lead" and carries
// "Read the briefing" (c6-briefing-screen); "Decide now" reads the queue
// counts on GET /me (D-23), never a second source; "Where we stand" reads
// `standing` on GET /home, each line leading to the list it counts; the foot
// names how the source watching is going.

function LeadCard({ home, briefing, t, ctx }: { home: Home; briefing: Briefing | undefined; t: Translate; ctx: FormatContext }) {
  if (home.lead === null) return null;
  const lead = home.lead;
  // The briefing's own lead is the same selector Today's is (HOM-01, HOM-02):
  // "more items this week" counts the rest of the running week's briefing.
  const moreThisWeek = briefing === undefined ? 0 : Math.max(0, briefing.items.length - 1);
  return (
    <div className="flex flex-col gap-3 rounded-card border border-line bg-surface p-4" data-lead-card={lead.stableKey}>
      <div className="flex flex-wrap items-center gap-2">
        <PillRow pills={presentLead(lead, t)} />
        <span className="text-meta text-muted">{authorityAndDate(lead, t, ctx)}</span>
      </div>
      <Link href={`/watch/${lead.id}`} prefetch={false}>
        <h2 className="hover:underline">{lead.title}</h2>
      </Link>
      {lead.case !== null && lead.case.soWhatText !== null && lead.case.soWhatText !== '' ? (
        <div className="rounded-control border border-line bg-subtle px-3 py-2.5 text-meta">
          {lead.case.soWhatConfirmed ? null : <span className="mb-0.5 block font-semibold text-brass">{t('watch.soWhat.aiDraft')}</span>}
          <span className="font-semibold text-fg">{t('watch.soWhat.label')}</span> <span>{lead.case.soWhatText}</span>
        </div>
      ) : null}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-3">
        <Link href="/briefing" className="inline-flex h-9 items-center rounded-control border border-button bg-button px-4 font-medium text-on-button no-underline">
          {t('today.lead.readBriefing')}
        </Link>
        {moreThisWeek > 0 ? <span className="text-meta text-muted">{t('today.lead.moreThisWeek', { count: moreThisWeek })}</span> : null}
      </div>
    </div>
  );
}

function StandingPanel({ standing, statuses, t }: { standing: Standing; statuses: readonly VocabularyRow[] | undefined; t: Translate }) {
  const presented = presentStanding(standing, statuses);
  return (
    <Panel title={t('today.standing.title')} data-standing="">
      {presented.empty ? (
        <p className="text-muted" data-empty-state="">
          {t('today.standing.empty')}{' '}
          <Link href="/inventory" className="text-fg underline underline-offset-2">
            {t('today.standing.emptyAction')}
          </Link>
        </p>
      ) : (
        <>
          <Link href={presented.applyingHref} className="text-meta text-muted underline underline-offset-2" data-standing-applying="">
            {t('today.standing.applying', { count: standing.applying })}
          </Link>
          {/* The bar repeats the counts below in their category tones, so a screen reader skips it. */}
          <div aria-hidden="true" className="mb-2 mt-1 flex gap-0.5">
            {presented.lines
              .filter((line) => line.count > 0)
              .map((line) => (
                <i key={line.key} className="block h-2 rounded-sm" style={{ flex: `${line.count} 1 0`, background: line.color }} />
              ))}
          </div>
          {presented.lines.map((line) => (
            <p key={line.key} className="mb-0 flex justify-between gap-3 py-0.5" data-standing-line={line.key}>
              {line.href === null ? (
                <span>{t(line.message)}</span>
              ) : (
                <Link href={line.href} className="underline-offset-2 hover:underline">
                  {t(line.message)}
                </Link>
              )}
              <span className="font-medium tabular-nums">{line.count}</span>
            </p>
          ))}
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <span className="text-meta text-muted">{t('today.standing.openGaps', { count: standing.openGaps })}</span>
            <Link
              href={presented.gapsHref}
              className="inline-flex h-8 items-center rounded-control border border-line-control bg-surface px-3 font-medium no-underline hover:hover-fill"
            >
              {t('today.standing.seeGaps')}
            </Link>
          </div>
        </>
      )}
    </Panel>
  );
}

export function TodayScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const { me } = useSession();
  const permissions = usePermissions() ?? [];
  const query = useHome();
  const forbidden = forbiddenFrom(query.error);
  // Independent of GET /home's own fan-out (never chained behind it): the
  // lead card's "Read the briefing" and "N more items this week" read the
  // running week, which a reader without watch.read cannot see either.
  const briefingQuery = useCurrentBriefing(query.data?.lead !== null && query.data?.lead !== undefined);
  // The statuses the standing lines filter the inventory by, fetched beside GET /home and
  // never after it: the reader's own permission says whether the panel can show.
  const statuses = useVocabularyValues('compliance_status', false, permissions.includes('register.read'));

  if (query.isPending) return <LoadingState rows={3} />;
  if (forbidden !== null) return <RestrictedScreen {...forbidden} />;
  if (query.isError) return <ErrorState title={t('today.errorTitle')} onRetry={() => void query.refetch()} />;

  const home = query.data;
  const kicker = formatLongDate(home.date, ctx);
  const counts = me?.counts ?? null;
  const lines = counts === null ? [] : decideNowLines(counts, permissions);
  const nothingToDecide = lines.every((line) => line.count === 0);
  const nothingAtAll = home.comingUp.length === 0 && home.lead === null && home.sources === null && home.standing === null && nothingToDecide;
  // The way to the regulatory scope shows only to someone the scope page opens for.
  const scope = findDestination('admin-footprint');
  const scopeAction = scope !== undefined && unlocks(scope.anyOfPermissions, permissions) ? { label: t('today.empty.action'), href: scope.href } : undefined;

  return (
    <>
      <PageHead kicker={kicker} title={t('today.title')} />
      {nothingAtAll ? (
        <EmptyState title={t('today.empty.title')} body={t('today.empty.body')} action={scopeAction} />
      ) : (
        <>
          <div className="mb-4 grid gap-4 lg:grid-cols-[1fr_1.6fr] lg:items-stretch">
            <ComingUpPanel items={home.comingUp} roadmapCount={home.roadmapCount} ctx={ctx} />
            <LeadCard home={home} briefing={briefingQuery.data} t={t} ctx={ctx} />
          </div>

          <div className="grid gap-x-4 md:grid-cols-2">
            {counts !== null ? (
              <Panel title={t('today.decideNow.title')} data-decide-now="">
                <div className="grid gap-1.5">
                  {lines.map((line) =>
                    line.href === null ? (
                      <p key={line.key} className="text-muted">
                        {t(line.message, { count: line.count })}
                      </p>
                    ) : (
                      <p key={line.key}>
                        <Link href={line.href} className="underline underline-offset-2" data-decide={line.key}>
                          {t(line.message, { count: line.count })}
                        </Link>
                      </p>
                    ),
                  )}
                </div>
              </Panel>
            ) : null}
            {home.standing !== null ? <StandingPanel standing={home.standing} statuses={statuses.data} t={t} /> : null}
          </div>

          {home.sources !== null ? (
            <p className="mt-1 flex flex-wrap items-center justify-between gap-3 text-meta text-muted" data-source-health="">
              <span>
                {[
                  t('today.sources.summary', { checked: home.sources.checked, total: home.sources.total }),
                  ...home.sources.failed.map((row) => t('today.sources.failed', { name: row.source.name })),
                ].join(' ')}
              </span>
              <Link href="/watch?tab=coverage" className="underline underline-offset-2">
                {t('today.sources.coverageLink')}
              </Link>
            </p>
          ) : null}
        </>
      )}
    </>
  );
}
