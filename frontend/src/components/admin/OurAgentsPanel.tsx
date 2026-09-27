'use client';

import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';

import {
  ADDABLE_DEFINITIONS,
  bankAgentKeys,
  bankAgentName,
  bankAgentWhat,
  hourLabel,
  HOURS,
  NEXT_RUN_KEY,
  nextRunOf,
  RECENT_RUNS,
  refusals,
  scopeMarkets,
  spendOf,
  useBankBudget,
  WEEKDAYS,
  weekdayLabel,
} from '@/components/admin/admin-agents';
import { AgentRunsList } from '@/components/admin/AgentRunsList';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { CheckGroup, CheckRow, Field, Select } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { CADENCE_KEY, presentTenantAgentState } from '@/features/agents/agents-presentation';
import {
  createTenantAgent,
  interruptAgentRun,
  listAgentRuns,
  listPlatformWatch,
  MAX_PAGE,
  pauseTenantAgent,
  resumeTenantAgent,
  runTenantAgentNow,
  updateTenantAgent,
} from '@/features/agents/api';
import type { AgentCadence, TenantAgent, TenantAgentPage, TenantAgentUpdate } from '@/features/agents/types';
import { useFootprint } from '@/features/footprint/hooks';
import { useFormatContext } from '@/features/identity/hooks';
import { useLocale, useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// Our agents (admin-agents.html sections 1 to 8; AGT-04): the agents this
// bank added for itself, each with its switch, pause, run now and stop, its
// cadence, run day and hour, the markets it covers and its recent runs. Every
// refusal renders in place from its code, and the old value stays until the
// server accepts a new one. The list comes from `GET /agents`, which never
// holds one of bleqq's agents; a row whose key is one of bleqq's would still
// render without a single control.

const CADENCES: readonly AgentCadence[] = ['daily', 'weekly', 'monthly', 'manual'];
const WEEKDAY_CADENCES: readonly AgentCadence[] = ['weekly', 'monthly'];

interface Schedule {
  cadence: AgentCadence;
  runWeekday: number;
  runHour: number;
  jurisdictions: string[];
}

const DEFAULT_WEEKDAY = 1;
const DEFAULT_HOUR = 6;

function scheduleOf(agent: TenantAgent): Schedule {
  return { cadence: agent.cadence, runWeekday: agent.runWeekday ?? DEFAULT_WEEKDAY, runHour: agent.runHour ?? DEFAULT_HOUR, jurisdictions: agent.scope.jurisdictions ?? [] };
}

/** What the route takes for a schedule: no day for daily or manual, no hour for manual. */
export function scheduleBody(schedule: Schedule, terms: string[]): { cadence: AgentCadence; runWeekday: number | null; runHour: number | null; scope: { jurisdictions: string[]; terms: string[] } } {
  return {
    cadence: schedule.cadence,
    runWeekday: WEEKDAY_CADENCES.includes(schedule.cadence) ? schedule.runWeekday : null,
    runHour: schedule.cadence === 'manual' ? null : schedule.runHour,
    scope: { jurisdictions: schedule.jurisdictions, terms },
  };
}

function ScheduleFields({ id, schedule, onChange }: { id: string; schedule: Schedule; onChange: (next: Schedule) => void }) {
  const t = useT();
  const locale = useLocale();
  const footprint = useFootprint();
  const markets = scopeMarkets(footprint.data?.markets ?? []);
  // A key already chosen stays offered even if the bank stopped following it.
  const extra = schedule.jurisdictions.filter((key) => !markets.some((m) => m.jurisdiction.key === key));
  const toggle = (key: string, on: boolean) =>
    onChange({ ...schedule, jurisdictions: on ? [...schedule.jurisdictions, key] : schedule.jurisdictions.filter((k) => k !== key) });

  return (
    <>
      <Field id={`${id}-cadence`} label={t('adminAgents.runs')}>
        <Select id={`${id}-cadence`} value={schedule.cadence} onChange={(e) => onChange({ ...schedule, cadence: e.target.value as AgentCadence })}>
          {CADENCES.map((cadence) => (
            <option key={cadence} value={cadence}>
              {t(CADENCE_KEY[cadence])}
            </option>
          ))}
        </Select>
      </Field>
      {WEEKDAY_CADENCES.includes(schedule.cadence) ? (
        <Field id={`${id}-day`} label={schedule.cadence === 'monthly' ? t('adminAgents.schedule.monthlyDay') : t('adminAgents.schedule.day')}>
          <Select id={`${id}-day`} value={schedule.runWeekday} onChange={(e) => onChange({ ...schedule, runWeekday: Number(e.target.value) })}>
            {WEEKDAYS.map((day) => (
              <option key={day} value={day}>
                {weekdayLabel(day, locale)}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}
      {schedule.cadence === 'manual' ? null : (
        <Field id={`${id}-hour`} label={t('adminAgents.schedule.hour')} hint={t('adminAgents.schedule.hourHint')}>
          <Select id={`${id}-hour`} value={schedule.runHour} onChange={(e) => onChange({ ...schedule, runHour: Number(e.target.value) })}>
            {HOURS.map((hour) => (
              <option key={hour} value={hour}>
                {hourLabel(hour)}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <CheckGroup legend={t('adminAgents.covers')} hint={t('adminAgents.schedule.coversHint')}>
        {markets.map((market) => (
          <CheckRow
            key={market.jurisdiction.key}
            id={`${id}-market-${market.jurisdiction.key}`}
            label={market.jurisdiction.label}
            hint={market.level === 'operating' ? t('adminAgents.schedule.operating') : t('adminAgents.schedule.watched')}
            checked={schedule.jurisdictions.includes(market.jurisdiction.key)}
            onChange={(on) => toggle(market.jurisdiction.key, on)}
          />
        ))}
        {extra.map((key) => (
          <CheckRow key={key} id={`${id}-market-${key}`} label={key.toUpperCase()} checked onChange={(on) => toggle(key, on)} />
        ))}
      </CheckGroup>
    </>
  );
}

function useInvalidateAgent(tenantAgentId: string): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: bankAgentKeys.list });
    await queryClient.invalidateQueries({ queryKey: bankAgentKeys.runs(tenantAgentId) });
  };
}

function AgentCard({ agent, aiEnabled, capReached, platform }: { agent: TenantAgent; aiEnabled: boolean; capReached: boolean; platform: boolean }) {
  const t = useT();
  const ctx = useFormatContext();
  const locale = useLocale();
  const footprint = useFootprint();
  const invalidate = useInvalidateAgent(agent.id);
  const runs = useQuery({
    queryKey: bankAgentKeys.runs(agent.id),
    queryFn: () => listAgentRuns({ tenantAgentId: agent.id, limit: RECENT_RUNS, offset: 0 }),
  });
  const [editing, setEditing] = useState(false);
  const [schedule, setSchedule] = useState<Schedule>(() => scheduleOf(agent));
  const [confirmingStop, setConfirmingStop] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const act = useMutation({
    mutationFn: (action: { kind: 'patch'; body: TenantAgentUpdate } | { kind: 'pause' | 'resume' | 'run' } | { kind: 'stop'; runId: string }): Promise<unknown> => {
      switch (action.kind) {
        case 'patch':
          return updateTenantAgent(agent.id, action.body);
        case 'pause':
          return pauseTenantAgent(agent.id);
        case 'resume':
          return resumeTenantAgent(agent.id);
        case 'run':
          return runTenantAgentNow(agent.id);
        case 'stop':
          return interruptAgentRun(action.runId);
      }
    },
    onMutate: () => setStatus(null),
    onSuccess: invalidate,
  });

  const name = bankAgentName(agent.agent, t);
  const what = bankAgentWhat(agent.agent, t);
  const next = nextRunOf(agent, { aiEnabled, capReached });
  const running = (runs.data?.items ?? []).find((run) => run.status === 'running' && run.interruptedAt === null);
  const marketLabel = (key: string) => footprint.data?.markets.find((m) => m.jurisdiction.key === key)?.jurisdiction.label ?? key.toUpperCase();
  const chosen = agent.scope.jurisdictions ?? [];
  const covers = chosen.length === 0 ? t('adminAgents.coversDefault') : chosen.map(marketLabel).join(', ');
  const when = [
    t(CADENCE_KEY[agent.cadence]),
    WEEKDAY_CADENCES.includes(agent.cadence) && agent.runWeekday !== null ? weekdayLabel(agent.runWeekday, locale) : null,
    agent.runHour === null ? null : hourLabel(agent.runHour),
  ].filter((part): part is string => part !== null);

  const run = (action: Parameters<typeof act.mutate>[0], done: string) => act.mutate(action, { onSuccess: () => setStatus(done) });
  const saveSchedule = (event: FormEvent) => {
    event.preventDefault();
    act.mutate(
      { kind: 'patch', body: scheduleBody(schedule, agent.scope.terms ?? []) },
      {
        onSuccess: () => {
          setEditing(false);
          setStatus(t('adminAgents.saved'));
        },
      },
    );
  };

  return (
    <Row data-tenant-agent={agent.id} data-agent-key={agent.agent}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{name}</h3>
        <PillRow pills={[presentTenantAgentState(agent, t)]} />
      </div>
      {what === null ? null : <p className="mt-1 text-meta text-muted">{what}</p>}
      <dl className="mt-2 grid grid-cols-1 gap-x-3.5 gap-y-1.5 text-meta md:grid-cols-[120px_1fr]">
        <dt className="text-muted">{t('adminAgents.runs')}</dt>
        <dd className="m-0">{when.join(' · ')}</dd>
        <dt className="text-muted">{t('adminAgents.nextRun')}</dt>
        <dd className="m-0" data-next-run={next.kind}>
          {running !== undefined ? t('adminAgents.next.running') : next.kind === 'at' ? formatDateTime(next.at, ctx) : t(NEXT_RUN_KEY[next.kind])}
        </dd>
        <dt className="text-muted">{t('adminAgents.covers')}</dt>
        <dd className="m-0">{covers}</dd>
        <dt className="text-muted">{t('adminAgents.writesTo')}</dt>
        <dd className="m-0">{t('adminAgents.ownRecords')}</dd>
      </dl>

      {platform ? null : (
        <>
          {status === null ? null : <StatusLine tone="positive">{status}</StatusLine>}
          {act.isError ? <ProblemAlert error={act.error} codes={refusals(t)} /> : null}
          {confirmingStop && running !== undefined ? (
            <div className="mt-3" data-stop-confirm="">
              <p className="font-medium">{t('adminAgents.stop.title')}</p>
              <p className="text-meta text-muted">{t('adminAgents.stop.body', { name })}</p>
              <ButtonBar>
                <Button variant="outline" size="small" onClick={() => setConfirmingStop(false)}>
                  {t('adminAgents.stop.keep')}
                </Button>
                <Button
                  variant="danger"
                  size="small"
                  disabled={act.isPending}
                  onClick={() => act.mutate({ kind: 'stop', runId: running.id }, { onSuccess: () => setStatus(t('adminAgents.stop.done')), onSettled: () => setConfirmingStop(false) })}
                >
                  {t('adminAgents.stop.confirm')}
                </Button>
              </ButtonBar>
            </div>
          ) : (
            <ButtonBar>
              <Button variant="outline" size="small" disabled={act.isPending} onClick={() => run({ kind: 'patch', body: { enabled: !agent.enabled } }, agent.enabled ? t('adminAgents.switchedOff') : t('adminAgents.switchedOn'))}>
                {agent.enabled ? t('adminAgents.switchOff') : t('adminAgents.switchOn')}
              </Button>
              <Button
                variant="outline"
                size="small"
                aria-expanded={editing}
                onClick={() => {
                  setSchedule(scheduleOf(agent));
                  setEditing(!editing);
                }}
              >
                {t('adminAgents.change')}
              </Button>
              {agent.enabled ? (
                <Button variant="outline" size="small" disabled={act.isPending} onClick={() => run({ kind: agent.pausedAt === null ? 'pause' : 'resume' }, agent.pausedAt === null ? t('adminAgents.pausedStatus') : t('adminAgents.resumedStatus'))}>
                  {agent.pausedAt === null ? t('adminAgents.pause') : t('adminAgents.resume')}
                </Button>
              ) : null}
              {agent.enabled && running !== undefined ? (
                <Button variant="danger" size="small" onClick={() => setConfirmingStop(true)}>
                  {t('adminAgents.stopRun')}
                </Button>
              ) : null}
              {agent.enabled && running === undefined ? (
                <Button size="small" disabled={act.isPending || capReached || !aiEnabled} onClick={() => run({ kind: 'run' }, t('adminAgents.runStarted'))}>
                  {t('adminAgents.runNow')}
                </Button>
              ) : null}
            </ButtonBar>
          )}
          {editing ? (
            <form onSubmit={saveSchedule} noValidate aria-busy={act.isPending} className="mt-3 border-t border-line pt-3" data-schedule-form="">
              <ScheduleFields id={`agent-${agent.id}`} schedule={schedule} onChange={setSchedule} />
              <ButtonBar>
                <Button
                  variant="outline"
                  size="small"
                  onClick={() => {
                    setSchedule(scheduleOf(agent));
                    setEditing(false);
                  }}
                >
                  {t('common.cancel')}
                </Button>
                <Button type="submit" size="small" disabled={act.isPending}>
                  {t('adminAgents.save')}
                </Button>
              </ButtonBar>
            </form>
          ) : null}
        </>
      )}

      <h4 className="mt-4 microlabel text-muted">{t('adminAgents.recentRuns')}</h4>
      {runs.isPending ? (
        <LoadingState rows={1} />
      ) : runs.isError ? (
        <ErrorState title={t('adminAgents.runsErrorTitle')} onRetry={() => void runs.refetch()} />
      ) : (
        <AgentRunsList runs={runs.data.items} />
      )}
    </Row>
  );
}

function AddAgentModal({ open, onClose, taken, onAdded }: { open: boolean; onClose: () => void; taken: readonly string[]; onAdded: (name: string) => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const offered = Object.keys(ADDABLE_DEFINITIONS).filter((key) => !taken.includes(key));
  const [agentKey, setAgentKey] = useState(offered[0] ?? '');
  const [schedule, setSchedule] = useState<Schedule>({ cadence: 'weekly', runWeekday: DEFAULT_WEEKDAY, runHour: DEFAULT_HOUR, jurisdictions: [] });
  const add = useMutation({
    mutationFn: () => createTenantAgent({ agent: agentKey, ...scheduleBody(schedule, []) }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: bankAgentKeys.list });
      onAdded(bankAgentName(agentKey, t));
      onClose();
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate();
  };

  return (
    <Modal open={open} onOpenChange={(isOpen) => (isOpen ? undefined : onClose())} title={t('adminAgents.add.title')} description={t('adminAgents.add.note')}>
      <form onSubmit={submit} noValidate aria-busy={add.isPending} data-add-agent-form="">
        <fieldset className="mb-3 grid gap-0 border-0 p-0">
          <legend className="mb-1 font-medium">{t('adminAgents.add.what')}</legend>
          {offered.map((key) => (
            <label key={key} className="flex items-start gap-2.5 border-b border-line py-2 last:border-b-0">
              <input type="radio" name="agent-definition" className="mt-0.5 size-4 accent-button" value={key} checked={agentKey === key} onChange={() => setAgentKey(key)} />
              <span>
                {bankAgentName(key, t)}
                <small className="block text-meta text-muted">{bankAgentWhat(key, t)}</small>
              </span>
            </label>
          ))}
        </fieldset>
        <ScheduleFields id="new-agent" schedule={schedule} onChange={setSchedule} />
        {add.isError ? <ProblemAlert error={add.error} codes={refusals(t)} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={add.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={add.isPending || agentKey === ''}>
            {t('adminAgents.add.submit')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

export function OurAgentsPanel({ agents, aiEnabled }: { agents: UseQueryResult<TenantAgentPage>; aiEnabled: boolean }) {
  const t = useT();
  const budget = useBankBudget(true);
  // bleqq's keys, from the same read the watch panel makes: a row with one never gets a control.
  const watch = useQuery({ queryKey: bankAgentKeys.platform, queryFn: () => listPlatformWatch({ limit: MAX_PAGE, offset: 0 }) });
  const platformKeys = new Set((watch.data?.items ?? []).map((item) => item.key));
  const [adding, setAdding] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const items = agents.data?.items ?? [];
  const taken = items.map((agent) => agent.agent);
  const canAdd = Object.keys(ADDABLE_DEFINITIONS).some((key) => !taken.includes(key));
  const capReached = budget.data === undefined ? false : spendOf(budget.data).reached;
  const addButton = canAdd ? (
    <Button onClick={() => setAdding(true)} data-add-agent="">
      {t('adminAgents.add.open')}
    </Button>
  ) : null;

  return (
    <Panel data-our-agents="">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2>{t('adminAgents.our.title')}</h2>
        {items.length > 0 ? addButton : null}
      </div>
      {status === null ? null : <StatusLine tone="positive">{status}</StatusLine>}
      {agents.isPending ? (
        <LoadingState rows={2} />
      ) : agents.isError ? (
        <ErrorState title={t('adminAgents.our.errorTitle')} onRetry={() => void agents.refetch()} />
      ) : items.length === 0 ? (
        <>
          <EmptyState title={t('adminAgents.our.emptyTitle')} body={t('adminAgents.our.emptyBody')} />
          {addButton === null ? null : <div className="mt-3 flex justify-center">{addButton}</div>}
        </>
      ) : (
        <Rows>
          {items.map((agent) => (
            <AgentCard key={agent.id} agent={agent} aiEnabled={aiEnabled} capReached={capReached} platform={platformKeys.has(agent.agent)} />
          ))}
        </Rows>
      )}
      {adding ? <AddAgentModal open onClose={() => setAdding(false)} taken={taken} onAdded={(name) => setStatus(t('adminAgents.add.done', { name }))} /> : null}
    </Panel>
  );
}
