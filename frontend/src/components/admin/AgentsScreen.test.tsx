import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AgentsScreen } from '@/components/admin/AgentsScreen';
import { watchFacts } from '@/components/admin/PlatformWatchPanel';
import { requestBody } from '@/components/admin/ResearchRequestPanel';
import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';
import { defaultFormatContext } from '@/shared/utils/format';

// /admin/agents (AGT-03, AGT-04, AGT-05, ADM-01): bleqq's watch read-only for
// every member with watch.read, and for agents.manage the bank's own agents
// with their controls, the one monthly cap and research requests. Every
// refusal renders from its code; no control reaches one of bleqq's agents.

const V1 = '/api/v1';
const PLATFORM = `${V1}/agents/platform`;
const AGENTS = `${V1}/agents`;
const BUDGET = `${V1}/tenant/agent-budget`;
const RUNS = `${V1}/agent-runs`;
const REQUESTS = `${V1}/research-requests`;

const READER = ['watch.read', 'library.read'];
const ADMIN = [...READER, 'agents.manage'];

const watchItem = {
  key: 'watch-sweeper',
  name: 'watch-sweeper',
  purpose: 'Checks the authorities’ sources for new and changed rules.',
  jurisdictions: ['eu', 'se'],
  cadence: 'daily',
  nextRunAt: '2026-09-26T04:00:00Z',
  lastRun: { finishedAt: '2026-09-25T04:00:00Z', status: 'succeeded' },
};

const ownAgent = (extra: Record<string, unknown> = {}) => ({
  id: 'ta1',
  agent: 'tenant-source-watch',
  enabled: true,
  cadence: 'weekly',
  runWeekday: 1,
  runHour: 6,
  nextRunAt: '2026-09-28T04:00:00Z',
  scope: { jurisdictions: ['se'], terms: ['pensions'] },
  pausedAt: null,
  pausedBy: null,
  updatedAt: '2026-09-20T08:00:00Z',
  ...extra,
});

const run = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  agent: 'tenant-source-watch',
  startedAt: '2026-09-22T04:02:00Z',
  finishedAt: '2026-09-22T04:16:00Z',
  status: 'succeeded',
  model: 'large-eu',
  pipelineVersion: '1',
  stats: { modelCalls: 2, fetches: 9, sourcesChecked: 4, changesRegistered: 3, proposalsSubmitted: 0, outOfScope: 0, recordsRechecked: 0, correctionsProposed: 0 },
  outputRef: null,
  error: null,
  tenantAgentId: 'ta1',
  agentVersion: 1,
  trigger: 'schedule',
  requestedBy: null,
  cost: '2.10',
  interruptedAt: null,
  ...extra,
});

const tenant = (aiEnabled = true) => ({ id: 't1', name: 'Example Bank AB', aiEnabled, timezone: 'Europe/Stockholm' });

const footprint = {
  dimensions: [],
  pendingRequest: null,
  markets: [
    { jurisdiction: { key: 'no', kind: 'country', label: 'Norway' }, level: 'watching' },
    { jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' }, level: 'operating' },
  ],
};

interface World {
  agents: ReturnType<typeof ownAgent>[];
  runs: ReturnType<typeof run>[];
  budget: { monthlyCap: string | null; currency: 'EUR'; spentThisMonth: string };
  aiEnabled: boolean;
  requests: unknown[];
}

function server(world: Partial<World> = {}, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  const w: World = { agents: [], runs: [], budget: { monthlyCap: '40.00', currency: 'EUR', spentThisMonth: '7.35' }, aiEnabled: true, requests: [], ...world };
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.method !== 'get') return { status: 500 };
    if (sent.path === PLATFORM) return { status: 200, data: { items: [watchItem], total: 1 } };
    if (sent.path === AGENTS) return { status: 200, data: { items: w.agents, total: w.agents.length } };
    if (sent.path === BUDGET) return { status: 200, data: w.budget };
    if (sent.path === RUNS) return { status: 200, data: { items: w.runs, total: w.runs.length } };
    if (sent.path === REQUESTS) return { status: 200, data: { items: w.requests, total: w.requests.length } };
    if (sent.path === `${V1}/tenant`) return { status: 200, data: tenant(w.aiEnabled) };
    if (sent.path === `${V1}/tenant/footprint`) return { status: 200, data: footprint };
    if (sent.path === `${V1}/reference/jurisdictions`) return { status: 200, data: [{ key: 'eu', kind: 'supranational', label: 'European Union', parentKey: null }, { key: 'se', kind: 'country', label: 'Sweden', parentKey: 'eu' }] };
    if (sent.path === `${V1}/sources`) return { status: 200, data: [{ id: 's1', name: 'Finansinspektionen news', active: true, authorityId: null, checkFrequency: 'daily', kind: { key: 'rss', kind: null, label: 'RSS' }, url: 'https://fi.se' }] };
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

function open(permissions: readonly string[]) {
  const { wrapper: Query } = queryWrapper();
  return render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <LocaleProvider locale="en">
          <AgentsScreen />
        </LocaleProvider>
      </PermissionsProvider>
    </Query>,
  );
}

/** The element once it renders; waitFor retries until the query finds it. */
const found = (selector: string): Promise<HTMLElement> =>
  waitFor(() => {
    const element = document.querySelector<HTMLElement>(selector);
    expect(element).not.toBeNull();
    return element as HTMLElement;
  });
const card = () => document.querySelector('[data-tenant-agent="ta1"]') as HTMLElement;
const problem = (code: string, status = 422): Answer => ({ status, data: { code, detail: 'Server words the screen never shows.' } });

describe('admin agents screen', () => {
  beforeEach(() => resetApiForTests());

  it('shows a reader bleqq’s watch and a line on what changing agents needs, and fetches nothing only a manager may read', async () => {
    const sent = server();
    open(READER);

    const watch = await screen.findByText('Watch sweeper');
    const row = watch.closest('[data-platform-agent]') as HTMLElement;
    expect(within(row).getByText(watchItem.purpose)).toBeInTheDocument();
    expect(within(row).getByText('European Union')).toHaveAttribute('data-pill', 'brand');
    expect(within(row).getByText('Daily')).toBeInTheDocument();
    expect(within(row).getByText('Done')).toHaveAttribute('data-pill', 'positive');
    expect(screen.getByText('Changing agents needs agents manage.')).toBeInTheDocument();
    expect(screen.queryAllByRole('button')).toEqual([]);
    expect(sent.some((s) => [AGENTS, BUDGET, RUNS, REQUESTS].includes(s.path))).toBe(false);
  });

  it('reads bleqq’s agents as five facts and a last-run status, and nothing more', () => {
    const facts = watchFacts(watchItem as never, createT('en'), defaultFormatContext);
    expect(Object.keys(facts).sort()).toEqual(['cadence', 'jurisdictions', 'key', 'lastRun', 'name', 'nextRun', 'purpose']);
    expect(Object.keys(facts.lastRun ?? {}).sort()).toEqual(['at', 'state']);
    expect(facts.lastRun?.state.tone).toBe('positive');
  });

  it('says the organisation’s AI switch is off and links to Organisation, with no switch of its own', async () => {
    server({ aiEnabled: false });
    open(READER);
    const line = await screen.findByText(/AI features are off for Example Bank AB/);
    expect(within(line).getByRole('link', { name: 'Change it under Organisation' })).toHaveAttribute('href', '/admin/organisation');
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('gives a bank with no agent of its own the empty state and Add, the spend, and no research panel', async () => {
    server({ budget: { monthlyCap: null, currency: 'EUR', spentThisMonth: '0.00' } });
    open(ADMIN);
    expect(await screen.findByText('No agents of our own yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add an agent' })).toBeInTheDocument();
    expect(await screen.findByText('€0.00 spent, no cap set yet')).toBeInTheDocument();
    expect(screen.queryByRole('meter')).toBeNull();
    expect(screen.getByText("Our own agents only. bleqq's watch runs at bleqq's cost and is not counted here.")).toBeInTheDocument();
    expect(document.querySelector('[data-research-panel]')).toBeNull();
  });

  it('draws the meter with its percentage and sets the cap', async () => {
    const sent = server({}, (s) => (s.method === 'put' && s.path === BUDGET ? { status: 200, data: { monthlyCap: '5.00', currency: 'EUR', spentThisMonth: '7.35' } } : undefined));
    open(ADMIN);
    expect(await screen.findByText('€7.35 of €40.00')).toBeInTheDocument();
    expect(screen.getByRole('meter', { name: "18% of this month's cap spent" })).toHaveAttribute('aria-valuenow', '18');

    fireEvent.change(screen.getByLabelText('Monthly cap in euro'), { target: { value: 'lots' } });
    fireEvent.click(screen.getByRole('button', { name: 'Set cap' }));
    expect(await screen.findByText('Enter an amount in euro, such as 40 or 40.00.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Monthly cap in euro'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Set cap' }));
    expect(await screen.findByText(/This month's cap is reached\. Scheduled runs wait/)).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'put').map((s) => s.body)).toEqual([{ monthlyCap: '5' }]);
  });

  it('shows one of our agents with its state, schedule, markets and recent runs', async () => {
    server({ agents: [ownAgent()], runs: [run('r1', { trigger: 'manual', requestedBy: { id: 'u1', name: 'Erik Holm' } }), run('r2', { interruptedAt: '2026-09-15T04:05:00Z', status: 'failed' })] });
    open(ADMIN);
    await waitFor(() => expect(card()).not.toBeNull());
    expect(within(card()).getByText('Source checker')).toBeInTheDocument();
    expect(within(card()).getByText('On')).toHaveAttribute('data-pill', 'positive');
    expect(within(card()).getByText('Weekly · Monday · 06:00')).toBeInTheDocument();
    expect(within(card()).getByText('Our own records')).toBeInTheDocument();
    expect(await within(card()).findByText(/Run now by Erik Holm · 14 min · 3 findings/)).toBeInTheDocument();
    expect(within(card()).getByText('Stopped')).toHaveAttribute('data-pill', 'warning');
    expect(within(card()).getByText('€2.10', { selector: '[data-run-id="r1"] *' })).toBeInTheDocument();
    expect(within(card()).getByText('Sweden')).toBeInTheDocument();
  });

  it('runs an agent now and says where the run is', async () => {
    const sent = server({ agents: [ownAgent()] }, (s) => (s.method === 'post' && s.path === `${AGENTS}/ta1/runs` ? { status: 200, data: run('r9', { status: 'running', finishedAt: null, cost: null }) } : undefined));
    open(ADMIN);
    await waitFor(() => expect(card()).not.toBeNull());
    fireEvent.click(await within(card()).findByRole('button', { name: 'Run now' }));
    expect(await within(card()).findByText('Run started. It is at the top of Recent runs.')).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'post' && s.path !== REFRESH_PATH).map((s) => s.path)).toEqual([`${AGENTS}/ta1/runs`]);
  });

  it('stops a running run after one confirmation', async () => {
    const sent = server({ agents: [ownAgent()], runs: [run('r9', { status: 'running', finishedAt: null, cost: null })] }, (s) =>
      s.method === 'post' && s.path === `${RUNS}/r9/interrupt` ? { status: 200, data: run('r9', { interruptedAt: '2026-09-25T07:36:00Z' }) } : undefined,
    );
    open(ADMIN);
    await waitFor(() => expect(card()).not.toBeNull());
    expect(await within(card()).findByText('Running now')).toBeInTheDocument();
    expect(within(card()).queryByRole('button', { name: 'Run now' })).toBeNull();
    fireEvent.click(within(card()).getByRole('button', { name: 'Stop run' }));
    expect(within(card()).getByText('Stop this run?')).toBeInTheDocument();
    fireEvent.click(within(card()).getByRole('button', { name: 'Stop the run' }));
    expect(await within(card()).findByText('Stopped. The run shows as stopped under Recent runs.')).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'post' && s.path !== REFRESH_PATH).map((s) => s.path)).toEqual([`${RUNS}/r9/interrupt`]);
  });

  it('renders a cadence above the plan limit in place and keeps the old one', async () => {
    const sent = server({ agents: [ownAgent()] }, (s) => (s.method === 'patch' ? problem('above_plan_limit') : undefined));
    open(ADMIN);
    await waitFor(() => expect(card()).not.toBeNull());
    fireEvent.click(within(card()).getByRole('button', { name: 'Change when and what' }));
    fireEvent.change(within(card()).getByLabelText('Runs'), { target: { value: 'daily' } });
    fireEvent.click(within(card()).getByLabelText(/Norway/));
    fireEvent.click(within(card()).getByRole('button', { name: 'Save' }));

    expect(await within(card()).findByText('Our plan does not allow this, so nothing changed.')).toBeInTheDocument();
    expect(within(card()).getByText('Weekly · Monday · 06:00')).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'patch').map((s) => s.body)).toEqual([
      { cadence: 'daily', runWeekday: null, runHour: 6, scope: { jurisdictions: ['se', 'no'], terms: ['pensions'] } },
    ]);
  });

  it.each([
    ['switching on without a cap', 'budget_cap_required', 'Set the monthly cap before switching an agent on.'],
    ['a paused agent', 'agent_paused', 'The agent is paused. Resume it first.'],
    ['the cap', 'budget_cap_reached', "This month's cap is reached, so nothing more runs until next month or until the cap is raised."],
    ['AI features off', 'feature_off', 'AI features are off for the organisation, so our agents do not run.'],
  ])('renders the refusal for %s from its code, never its detail', async (_case, code, sentence) => {
    server({ agents: [ownAgent({ enabled: false })] }, (s) => (s.method === 'patch' ? problem(code) : undefined));
    open(ADMIN);
    await waitFor(() => expect(card()).not.toBeNull());
    fireEvent.click(within(card()).getByRole('button', { name: 'Switch on' }));
    expect(await within(card()).findByText(sentence)).toBeInTheDocument();
    expect(screen.queryByText('Server words the screen never shows.')).toBeNull();
  });

  it('pauses and resumes, and a pause the cap made reads as the cap', async () => {
    const sent = server({ agents: [ownAgent({ pausedAt: '2026-09-24T00:00:00Z' })] }, (s) => (s.method === 'delete' ? { status: 200, data: ownAgent() } : undefined));
    open(ADMIN);
    await waitFor(() => expect(card()).not.toBeNull());
    expect(within(card()).getByText('Paused, monthly cap reached')).toBeInTheDocument();
    fireEvent.click(within(card()).getByRole('button', { name: 'Resume' }));
    expect(await within(card()).findByText('Resumed.')).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'delete').map((s) => s.path)).toEqual([`${AGENTS}/ta1/pause`]);
  });

  it('adds an agent switched off with its schedule, and renders unknown_key from its code', async () => {
    let refuse = true;
    const sent = server({}, (s) => {
      if (s.method !== 'post' || s.path !== AGENTS) return undefined;
      return refuse ? problem('unknown_key') : { status: 201, data: ownAgent({ enabled: false }) };
    });
    open(ADMIN);
    fireEvent.click(await screen.findByRole('button', { name: 'Add an agent' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add an agent' });
    expect(within(dialog).getByText('It starts switched off, so nothing runs until you switch it on.')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add the agent' }));
    expect(await within(dialog).findByText('That choice is no longer offered. Reload the page and choose again.')).toBeInTheDocument();

    refuse = false;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add the agent' }));
    expect(await screen.findByText('Added Source checker. It is switched off until you switch it on.')).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'post' && s.path !== REFRESH_PATH).map((s) => s.body)[1]).toEqual({
      agent: 'tenant-source-watch',
      cadence: 'weekly',
      runWeekday: 1,
      runHour: 6,
      scope: { jurisdictions: [], terms: [] },
    });
  });

  it('draws no control on a row whose key is one of bleqq’s, were one ever listed', async () => {
    server({ agents: [ownAgent({ agent: 'watch-sweeper' })] });
    open(ADMIN);
    await waitFor(() => expect(card()).not.toBeNull());
    await waitFor(() => expect(within(card()).queryByRole('button', { name: 'Switch off' })).toBeNull());
    expect(within(card()).queryAllByRole('button')).toEqual([]);
  });
});

describe('research requests', () => {
  beforeEach(() => resetApiForTests());

  it('sends only the chosen kind’s own field', () => {
    const draft = { kind: 'check_url' as const, tenantAgentId: 'ta1', sourceId: 's1', url: ' https://fi.se/news ', topic: 'DORA' };
    expect(requestBody(draft)).toEqual({ kind: 'check_url', tenantAgentId: 'ta1', url: 'https://fi.se/news' });
    expect(requestBody({ ...draft, kind: 'check_source' })).toEqual({ kind: 'check_source', tenantAgentId: 'ta1', sourceId: 's1' });
    expect(requestBody({ ...draft, kind: 'research_topic' })).toEqual({ kind: 'research_topic', tenantAgentId: 'ta1', topic: 'DORA' });
    expect(requestBody({ ...draft, url: 'http://fi.se' })).toBe('url');
    expect(requestBody({ ...draft, kind: 'research_topic', topic: ' ' })).toBe('topic');
    expect(requestBody({ ...draft, kind: 'check_source', sourceId: '' })).toBe('source');
  });

  it.each([
    ['no_tenant_agent', 409, "Add an agent of our own first. bleqq's watch runs on its own schedule and takes no requests."],
    ['plan_limit_reached', 429, "Our plan's requests for this period are used up. Try again later."],
    ['budget_cap_reached', 422, "This month's cap is reached, so nothing more runs until next month or until the cap is raised."],
  ])('renders %s from its code', async (code, status, sentence) => {
    server({ agents: [ownAgent()] }, (s) => (s.method === 'post' && s.path === REQUESTS ? problem(code, status) : undefined));
    open(ADMIN);
    const panel = await found('[data-research-panel]');
    await within(panel).findByRole('option', { name: 'Finansinspektionen news' });
    fireEvent.change(within(panel).getByLabelText('Source'), { target: { value: 's1' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Ask' }));
    expect(await within(panel).findByText(sentence)).toBeInTheDocument();
  });

  it('asks for a topic, and re-reads an open request from its status endpoint until it settles', async () => {
    const queued = { id: 'rq1', kind: 'research_topic', tenantAgentId: 'ta1', topic: 'DORA subcontracting', sourceId: null, url: null, status: 'queued', requestedBy: { id: 'u1', name: 'Erik Holm' }, createdAt: '2026-09-25T07:00:00Z', completedAt: null };
    let reads = 0;
    const sent = server({ agents: [ownAgent()], requests: [queued] }, (s) => {
      if (s.method === 'post' && s.path === REQUESTS) return { status: 201, data: queued };
      if (s.path === `${REQUESTS}/rq1`) {
        reads += 1;
        return { status: 200, data: { ...queued, status: 'done', completedAt: '2026-09-25T07:10:00Z' } };
      }
      return undefined;
    });
    open(ADMIN);
    const panel = await found('[data-research-panel]');
    fireEvent.click(within(panel).getByLabelText('Research a topic'));
    fireEvent.change(within(panel).getByLabelText('Topic'), { target: { value: 'DORA subcontracting' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Ask' }));
    expect(await within(panel).findByText('Asked. The request is at the top of Our requests.')).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'post' && s.path !== REFRESH_PATH).map((s) => s.body)).toEqual([{ kind: 'research_topic', tenantAgentId: 'ta1', topic: 'DORA subcontracting' }]);

    const row = await found('[data-research-request="rq1"]');
    await waitFor(() => expect(row).toHaveAttribute('data-request-status', 'done'));
    expect(within(row).getByText('Done')).toHaveAttribute('data-pill', 'positive');
    expect(reads).toBeGreaterThan(0);
  });
});
