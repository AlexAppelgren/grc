'use client';

import { Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { formatEuro, presentRunState, runMinutes, runStateOf, TRIGGER_KEY } from '@/features/agents/agents-presentation';
import type { AgentRun } from '@/features/agents/types';
import { useFormatContext } from '@/features/identity/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime, type FormatContext } from '@/shared/utils/format';

// Recent runs of one of our agents (admin-agents.html section 1; AGT-04):
// when it ran, what started it and who asked, how long it took, what it
// found, how it ended and what it cost. A run lists findings, never
// proposals: our own agent writes only to our own records.

/** The facts line of one run, in the order the card reads them. */
export function runFacts(run: AgentRun, t: Translate, ctx: FormatContext): string[] {
  const minutes = runMinutes(run);
  const trigger = run.requestedBy === null ? t(TRIGGER_KEY[run.trigger]) : t('adminAgents.run.by', { trigger: t(TRIGGER_KEY[run.trigger]), name: run.requestedBy.name });
  const state = runStateOf(run);
  return [
    formatDateTime(run.startedAt, ctx),
    trigger,
    minutes === null ? null : t('adminAgents.run.minutes', { count: minutes }),
    state === 'done' ? t('adminAgents.run.findings', { count: run.stats.changesRegistered }) : null,
  ].filter((fact): fact is string => fact !== null);
}

export function AgentRunsList({ runs }: { runs: readonly AgentRun[] }) {
  const t = useT();
  const ctx = useFormatContext();
  if (runs.length === 0) return <p className="mt-1 text-meta text-muted">{t('adminAgents.run.none')}</p>;
  return (
    <Rows className="mt-1 gap-0">
      {runs.map((run) => (
        <div key={run.id} data-run-id={run.id} data-run-state={runStateOf(run)} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line py-2 last:border-b-0">
          <span className="min-w-0 grow text-meta">{runFacts(run, t, ctx).join(' · ')}</span>
          <PillRow pills={[presentRunState(run, t)]} />
          <span className="text-meta tabular-nums">{formatEuro(run.cost, ctx) ?? t('adminAgents.run.noCost')}</span>
        </div>
      ))}
    </Rows>
  );
}
