'use client';

import { useQuery } from '@tanstack/react-query';

import { bankAgentKeys } from '@/components/admin/admin-agents';
import { EmptyState } from '@/components/ui/EmptyState';
import { Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { CADENCE_KEY, definitionName, presentJurisdictions, presentRunState } from '@/features/agents/agents-presentation';
import { listPlatformWatch, MAX_PAGE } from '@/features/agents/api';
import type { PlatformWatchItem } from '@/features/agents/types';
import { useJurisdictions } from '@/features/footprint/hooks';
import { useFormatContext } from '@/features/identity/hooks';
import type { PresentedPill } from '@/features/shared/presentation-types';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime, type FormatContext } from '@/shared/utils/format';

// What bleqq watches (admin-agents.html section 1; AGT-03, ruling 6): bleqq's
// general watch, read-only for every member holding watch.read. Each agent
// shows its name, purpose, the jurisdictions it sweeps, its cadence, its next
// run and how its last run ended, and nothing else. There is nothing to press
// here: no control on this page reaches one of bleqq's agents.

/** The facts a bank may read about one of bleqq's agents, and only those. */
export interface WatchFacts {
  key: string;
  name: string;
  purpose: string;
  jurisdictions: string[];
  cadence: string;
  nextRun: string | null;
  lastRun: { at: string | null; state: PresentedPill } | null;
}

export function watchFacts(item: PlatformWatchItem, t: Translate, ctx: FormatContext): WatchFacts {
  return {
    key: item.key,
    name: definitionName(item.name),
    purpose: item.purpose,
    jurisdictions: item.jurisdictions,
    cadence: t(CADENCE_KEY[item.cadence]),
    nextRun: item.nextRunAt === null ? null : formatDateTime(item.nextRunAt, ctx),
    lastRun:
      item.lastRun === null
        ? null
        : { at: item.lastRun.finishedAt === null ? null : formatDateTime(item.lastRun.finishedAt, ctx), state: presentRunState({ status: item.lastRun.status, interruptedAt: null }, t) },
  };
}

function WatchRow({ item }: { item: PlatformWatchItem }) {
  const t = useT();
  const ctx = useFormatContext();
  const jurisdictions = useJurisdictions();
  const labelOf = (key: string) => jurisdictions.data?.find((j) => j.key === key)?.label ?? key.toUpperCase();
  const facts = watchFacts(item, t, ctx);

  return (
    <Row data-platform-agent={facts.key}>
      <h3 className="font-semibold">{facts.name}</h3>
      <p className="mt-1 text-meta text-muted">{facts.purpose}</p>
      <dl className="mt-2 grid grid-cols-1 gap-x-3.5 gap-y-1.5 text-meta md:grid-cols-[120px_1fr]">
        <dt className="text-muted">{t('adminAgents.watch.jurisdictions')}</dt>
        <dd className="m-0">
          <PillRow pills={presentJurisdictions(facts.jurisdictions, labelOf)} />
        </dd>
        <dt className="text-muted">{t('adminAgents.runs')}</dt>
        <dd className="m-0">{facts.cadence}</dd>
        <dt className="text-muted">{t('adminAgents.nextRun')}</dt>
        <dd className="m-0">{facts.nextRun ?? t('adminAgents.next.unscheduled')}</dd>
        <dt className="text-muted">{t('adminAgents.watch.lastRun')}</dt>
        <dd className="m-0 flex flex-wrap items-center gap-2">
          {facts.lastRun === null ? (
            t('adminAgents.watch.neverRun')
          ) : (
            <>
              {facts.lastRun.at === null ? null : <span>{facts.lastRun.at}</span>}
              <PillRow pills={[facts.lastRun.state]} />
            </>
          )}
        </dd>
      </dl>
    </Row>
  );
}

export function PlatformWatchPanel() {
  const t = useT();
  const watch = useQuery({ queryKey: bankAgentKeys.platform, queryFn: () => listPlatformWatch({ limit: MAX_PAGE, offset: 0 }) });

  return (
    <Panel title={t('adminAgents.watch.title')} data-platform-watch="">
      <p className="-mt-1.5 mb-3 text-meta text-muted">{t('adminAgents.watch.lede')}</p>
      {watch.isPending ? (
        <LoadingState rows={2} />
      ) : watch.isError ? (
        <ErrorState title={t('adminAgents.watch.errorTitle')} onRetry={() => void watch.refetch()} />
      ) : watch.data.items.length === 0 ? (
        <EmptyState title={t('adminAgents.watch.emptyTitle')} body={t('adminAgents.watch.emptyBody')} />
      ) : (
        <Rows>
          {watch.data.items.map((item) => (
            <WatchRow key={item.key} item={item} />
          ))}
        </Rows>
      )}
    </Panel>
  );
}
