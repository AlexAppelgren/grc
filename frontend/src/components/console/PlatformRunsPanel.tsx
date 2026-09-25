'use client';

import Link from 'next/link';

import { EmptyState } from '@/components/ui/EmptyState';
import { Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { formatEuro, presentRunState, runMinutes } from '@/features/agents/agents-presentation';
import { useRecentPlatformRuns } from '@/features/agents/hooks';
import type { AgentRun } from '@/features/agents/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// Platform runs (console-agent-definitions.html, section 6): what one of
// bleqq's own agents has run lately, newest first, with its version, how it
// ended, what it checked, found and proposed, and what it cost. A platform run
// reads no bank's row, so no bank's name, count or figure is here. It links to
// the console's Sources page, where the coverage behind "sources checked" is.

/** The most a panel shows; older runs stay in the route's history. */
const SHOWN = 20;

function RunRow({ run }: { run: AgentRun }) {
  const t = useT();
  const ctx = useFormatContext();
  const minutes = runMinutes(run);
  const facts = [
    formatDateTime(run.startedAt, ctx),
    run.agentVersion === null ? null : t('agents.versionNo', { version: run.agentVersion }),
    minutes === null ? null : t('console.agents.runs.minutes', { count: minutes }),
    t('console.agents.runs.sourcesChecked', { count: run.stats.sourcesChecked }),
    t('console.agents.runs.findings', { count: run.stats.changesRegistered }),
    t('console.agents.runs.proposals', { count: run.stats.proposalsSubmitted }),
  ].filter((fact): fact is string => fact !== null);

  return (
    <Row data-run-id={run.id} data-run-state={run.status} className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <span className="min-w-0 grow text-meta">{facts.join(' · ')}</span>
      <PillRow pills={[presentRunState(run, t)]} />
      <span className="text-meta tabular-nums">{formatEuro(run.cost, ctx) ?? t('console.agents.runs.noCost')}</span>
      {run.error === null ? null : <p className="m-0 w-full text-meta text-muted">{run.error}</p>}
    </Row>
  );
}

export function PlatformRunsPanel({ agentKey }: { agentKey: string }) {
  const t = useT();
  const runs = useRecentPlatformRuns();
  // The platform's own runs of this agent only: a bank's run of a definition is that bank's.
  const mine = (runs.data?.items ?? []).filter((run) => run.agent === agentKey && run.tenantAgentId === null).reverse().slice(0, SHOWN);

  return (
    <Panel title={t('console.agents.runs.title')} data-platform-runs="">
      {runs.isPending ? (
        <LoadingState rows={3} />
      ) : runs.isError ? (
        <ErrorState title={t('console.agents.runs.errorTitle')} onRetry={() => void runs.refetch()} />
      ) : mine.length === 0 ? (
        <EmptyState title={t('console.agents.runs.emptyTitle')} body={t('console.agents.runs.emptyBody')} />
      ) : (
        <Rows>
          {mine.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </Rows>
      )}
      <p className="mt-3 text-meta">
        <Link href="/console/sources" className="font-semibold underline">
          {t('console.agents.runs.sources')}
        </Link>
      </p>
    </Panel>
  );
}
