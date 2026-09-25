import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AgentDefinitionScreen } from '@/components/console/AgentDefinitionScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, setStepUpHandler } from '@/shared/utils/api-client';

// One agent definition in the console (AGT-03, ADM-02): its append-only
// versions with publish and retire behind a passkey, and for one of bleqq's
// own agents the settings that change it for every bank and its recent runs,
// which carry nothing of any bank's.

const ME_PATH = '/api/v1/me';
const DEFINITION_PATH = '/api/v1/agent-definitions/watch-sweeper';
const VERSIONS_PATH = `${DEFINITION_PATH}/versions`;
const RETIRE_PATH = `${DEFINITION_PATH}/versions/2/retire`;
const SETTINGS_PATH = `${DEFINITION_PATH}/settings`;
const RUNS_PATH = '/api/v1/console/agent-runs';
const JURISDICTIONS_PATH = '/api/v1/reference/jurisdictions';

const admin = {
  user: { id: 'u1', email: 'platform@bleqq.test', name: 'Kari Nygaard', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['agent_definitions.manage'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

const version = (versionNo: number, retiredAt: string | null = null) => ({
  versionNo,
  model: 'large-eu',
  changeNote: `Change in ${versionNo}.`,
  publishedAt: '2026-09-12T12:30:00Z',
  publishedBy: { id: 'u2', name: 'Maria Ek' },
  retiredAt,
});

const definition = {
  id: 'd1',
  key: 'watch-sweeper',
  description: 'Checks the authorities’ sources for new and changed rules.',
  currentVersion: 3,
  active: true,
  scope: 'platform',
  tenantConfigurable: false,
  publishedAt: '2026-09-21T07:12:00Z',
  versions: [version(3), version(2), version(1, '2026-09-12T12:31:00Z')],
};

const settings = { agentKey: 'watch-sweeper', cadence: 'weekly', jurisdictions: ['se'], monthlyBudget: '200.00' };

const JURISDICTIONS = [
  { key: 'eu', kind: 'supranational', label: 'European Union', parentKey: null },
  { key: 'se', kind: 'country', label: 'Sweden', parentKey: 'eu' },
];

const run = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  agent: 'watch-sweeper',
  startedAt: '2026-09-24T04:00:00Z',
  finishedAt: '2026-09-24T04:14:00Z',
  status: 'succeeded',
  model: 'large-eu',
  pipelineVersion: '3',
  stats: { modelCalls: 4, fetches: 40, sourcesChecked: 40, changesRegistered: 1, proposalsSubmitted: 1, outOfScope: 0, recordsRechecked: 0, correctionsProposed: 0 },
  outputRef: null,
  error: null,
  tenantAgentId: null,
  agentVersion: 3,
  trigger: 'schedule',
  requestedBy: null,
  cost: '2.05',
  interruptedAt: null,
  ...extra,
});

const RUNS = [
  run('r-old', { startedAt: '2026-09-23T04:00:00Z', finishedAt: '2026-09-23T04:02:00Z', status: 'failed', error: 'The Danish authority’s feed did not answer.', cost: '0.30', agentVersion: 2 }),
  run('r-other-agent', { agent: 'library-confirmer' }),
  run('r-bank', { tenantAgentId: 'ta1' }),
  run('r-new'),
];

function server(extra: (sent: Sent) => Answer | undefined = () => undefined, detail: Answer = { status: 200, data: definition }): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: admin };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === DEFINITION_PATH && sent.method === 'get') return detail;
    if (sent.path === SETTINGS_PATH && sent.method === 'get') return { status: 200, data: settings };
    if (sent.path === JURISDICTIONS_PATH) return { status: 200, data: JURISDICTIONS };
    if (sent.path === RUNS_PATH) return { status: 200, data: { items: RUNS, total: RUNS.length } };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const versionRow = (n: number) => document.querySelector(`[data-agent-version="${n}"]`) as HTMLElement;
const stepUpOnce = (answered: { count: number }, body: unknown): Answer => {
  answered.count += 1;
  return answered.count === 1 ? { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } } : { status: 200, data: body };
};

describe('console agent definition', () => {
  let steppedUp = 0;
  beforeEach(() => {
    resetApiForTests();
    steppedUp = 0;
    setStepUpHandler(async () => {
      steppedUp += 1;
      return true;
    });
  });

  it('shows every version with its folder, model, note and publisher, and retire only on an earlier live one', async () => {
    server();
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Watch sweeper' })).toBeInTheDocument();
    expect(within(versionRow(3)).getByText('Current')).toHaveAttribute('data-pill', 'positive');
    expect(within(versionRow(3)).getByText('agents/watch-sweeper/v3')).toBeInTheDocument();
    expect(within(versionRow(3)).getByText('large-eu')).toBeInTheDocument();
    expect(within(versionRow(3)).getByText('Change in 3.')).toBeInTheDocument();
    expect(within(versionRow(3)).getByText(/by Maria Ek$/)).toBeInTheDocument();
    expect(within(versionRow(3)).queryByRole('button', { name: 'Retire' })).toBeNull();
    expect(within(versionRow(2)).getByRole('button', { name: 'Retire' })).toBeInTheDocument();
    expect(within(versionRow(1)).getByText('Retired', { selector: '[data-pill]' })).toHaveAttribute('data-pill', 'information');
    expect(within(versionRow(1)).queryByRole('button', { name: 'Retire' })).toBeNull();
  });

  it('publishes a version with its note after a passkey, and the new version then shows', async () => {
    const answered = { count: 0 };
    let current = definition;
    const sent = server((s) => {
      if (s.path === VERSIONS_PATH && s.method === 'post') {
        const published = { ...version(4), changeNote: 'Reads the consultation feed.', publishedAt: '2026-09-25T08:00:00Z' };
        const answer = stepUpOnce(answered, published);
        if (answer.status === 200) current = { ...definition, currentVersion: 4, versions: [published, ...definition.versions] };
        return answer;
      }
      if (s.path === DEFINITION_PATH && s.method === 'get') return { status: 200, data: current };
      return undefined;
    });
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    await screen.findByRole('heading', { level: 1, name: 'Watch sweeper' });

    fireEvent.click(screen.getByRole('button', { name: 'Publish a version' }));
    const dialog = await screen.findByRole('dialog', { name: 'Publish a new version' });
    expect(within(dialog).getByLabelText('Version')).toHaveValue(4);
    // A version without a note is refused before anything is sent.
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish version 4' }));
    expect(await within(dialog).findByText('Say what changed in this version.')).toBeInTheDocument();
    expect(sent.filter((s) => s.path === VERSIONS_PATH)).toEqual([]);

    fireEvent.change(within(dialog).getByLabelText('What changed'), { target: { value: '  Reads the consultation feed. ' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish version 4' }));

    expect(await screen.findByText('Published. Watch sweeper runs version 4 from its next run.')).toBeInTheDocument();
    expect(steppedUp).toBe(1);
    expect(sent.filter((s) => s.path === VERSIONS_PATH).map((s) => s.body)).toEqual([
      { versionNo: 4, changeNote: 'Reads the consultation feed.' },
      { versionNo: 4, changeNote: 'Reads the consultation feed.' },
    ]);
    await waitFor(() => expect(within(versionRow(4)).getByText('Current')).toBeInTheDocument());
    expect(within(versionRow(3)).getByRole('button', { name: 'Retire' })).toBeInTheDocument();
  });

  it('says nothing changed when the passkey is not given for a publish', async () => {
    setStepUpHandler(async () => false);
    server((s) => (s.path === VERSIONS_PATH ? { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } } : undefined));
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    await screen.findByRole('heading', { level: 1, name: 'Watch sweeper' });

    fireEvent.click(screen.getByRole('button', { name: 'Publish a version' }));
    const dialog = await screen.findByRole('dialog', { name: 'Publish a new version' });
    fireEvent.change(within(dialog).getByLabelText('What changed'), { target: { value: 'A note.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish version 4' }));
    expect(await within(dialog).findByText('The action was not confirmed, so nothing changed.')).toBeInTheDocument();
  });

  it('retires an earlier version after a confirmation and a passkey', async () => {
    const answered = { count: 0 };
    const sent = server((s) => (s.path === RETIRE_PATH ? stepUpOnce(answered, version(2, '2026-09-25T08:00:00Z')) : undefined));
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    await screen.findByRole('heading', { level: 1, name: 'Watch sweeper' });

    fireEvent.click(within(versionRow(2)).getByRole('button', { name: 'Retire' }));
    expect(within(versionRow(2)).getByText(/^Retire version 2\? No run starts on it again\./)).toBeInTheDocument();
    fireEvent.click(within(versionRow(2)).getByRole('button', { name: 'Retire version 2' }));

    expect(await screen.findByText('Retired version 2. No run starts on it again.')).toBeInTheDocument();
    expect(steppedUp).toBe(1);
    expect(sent.filter((s) => s.path === RETIRE_PATH).map((s) => s.method)).toEqual(['post', 'post']);
  });

  it('saves how a platform agent runs for every bank, after a passkey', async () => {
    const answered = { count: 0 };
    const sent = server((s) => (s.path === SETTINGS_PATH && s.method === 'put' ? stepUpOnce(answered, { agentKey: 'watch-sweeper', ...(s.body as object) }) : undefined));
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);

    const panel = (await screen.findByText('How it runs')).closest('[data-platform-settings]') as HTMLElement;
    expect(within(panel).getByText('Changes this for every bank.')).toBeInTheDocument();
    await waitFor(() => expect(within(panel).getByLabelText('Sweden')).toBeChecked());
    expect(within(panel).getByLabelText('Runs')).toHaveValue('weekly');
    expect(within(panel).getByLabelText('Monthly budget in euro')).toHaveValue('200.00');

    fireEvent.change(within(panel).getByLabelText('Runs'), { target: { value: 'daily' } });
    fireEvent.click(within(panel).getByLabelText('European Union'));
    fireEvent.change(within(panel).getByLabelText('Monthly budget in euro'), { target: { value: '250' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Save for every bank' }));

    expect(await within(panel).findByText('Saved for every bank. Watch sweeper runs this way from its next run.')).toBeInTheDocument();
    expect(steppedUp).toBe(1);
    expect(sent.filter((s) => s.path === SETTINGS_PATH && s.method === 'put').map((s) => s.body)).toEqual([
      { cadence: 'daily', jurisdictions: ['se', 'eu'], monthlyBudget: '250' },
      { cadence: 'daily', jurisdictions: ['se', 'eu'], monthlyBudget: '250' },
    ]);
  });

  it('refuses settings with no jurisdiction or a budget that is not an amount, and sends nothing', async () => {
    const sent = server();
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    const panel = (await screen.findByText('How it runs')).closest('[data-platform-settings]') as HTMLElement;
    await waitFor(() => expect(within(panel).getByLabelText('Sweden')).toBeChecked());

    fireEvent.change(within(panel).getByLabelText('Monthly budget in euro'), { target: { value: '12,5' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Save for every bank' }));
    expect(await within(panel).findByText('Enter an amount in euro, such as 250 or 250.00.')).toBeInTheDocument();

    fireEvent.change(within(panel).getByLabelText('Monthly budget in euro'), { target: { value: '' } });
    fireEvent.click(within(panel).getByLabelText('Sweden'));
    fireEvent.click(within(panel).getByRole('button', { name: 'Save for every bank' }));
    expect(await within(panel).findByText('Choose at least one jurisdiction.')).toBeInTheDocument();

    // Cancel puts back what is saved.
    fireEvent.click(within(panel).getByRole('button', { name: 'Cancel' }));
    expect(within(panel).getByLabelText('Sweden')).toBeChecked();
    expect(within(panel).getByLabelText('Monthly budget in euro')).toHaveValue('200.00');
    expect(sent.filter((s) => s.path === SETTINGS_PATH && s.method === 'put')).toEqual([]);
  });

  it("shows this agent's own platform runs newest first, with no bank's run, and links to Sources", async () => {
    server();
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    const panel = (await screen.findByText('Recent runs')).closest('[data-platform-runs]') as HTMLElement;

    await waitFor(() => expect(panel.querySelectorAll('[data-run-id]')).toHaveLength(2));
    expect([...panel.querySelectorAll('[data-run-id]')].map((row) => row.getAttribute('data-run-id'))).toEqual(['r-new', 'r-old']);
    const done = panel.querySelector('[data-run-id="r-new"]') as HTMLElement;
    expect(within(done).getByText('Done')).toHaveAttribute('data-pill', 'positive');
    expect(within(done).getByText(/Version 3 · 14 min · 40 sources checked · 1 finding · 1 proposal$/)).toBeInTheDocument();
    expect(within(done).getByText('€2.05')).toBeInTheDocument();
    const failed = panel.querySelector('[data-run-id="r-old"]') as HTMLElement;
    expect(within(failed).getByText('Failed')).toHaveAttribute('data-pill', 'negative');
    expect(within(failed).getByText('The Danish authority’s feed did not answer.')).toBeInTheDocument();
    expect(within(panel).getByRole('link', { name: 'Sources and coverage' })).toHaveAttribute('href', '/console/sources');
  });

  it('gives a definition for banks no settings and no platform runs', async () => {
    const sent = server(undefined, { status: 200, data: { ...definition, scope: 'tenant' } });
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    expect(await screen.findByText(/^A definition for banks has no settings here/)).toBeInTheDocument();
    expect(screen.queryByText('How it runs')).toBeNull();
    expect(screen.queryByText('Recent runs')).toBeNull();
    expect(sent.filter((s) => s.path === SETTINGS_PATH || s.path === RUNS_PATH)).toEqual([]);
  });

  it('offers the first publish on a definition with no version yet', async () => {
    server(undefined, { status: 200, data: { ...definition, scope: 'tenant', active: false, publishedAt: null, versions: [] } });
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    expect(await screen.findByText('No version published yet')).toBeInTheDocument();
    expect(screen.getByText('Draft')).toHaveAttribute('data-pill', 'information');
    fireEvent.click(screen.getByRole('button', { name: 'Publish a version' }));
    expect(within(await screen.findByRole('dialog')).getByLabelText('Version')).toHaveValue(1);
  });

  it('says so for a key no definition has', async () => {
    server(undefined, { status: 404, data: { code: 'not_found', detail: 'No such definition.' } });
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    expect(await screen.findByText('No agent definition has this key.')).toBeInTheDocument();
  });

  it('renders the server’s refusal as it is', async () => {
    server(undefined, { status: 403, data: { code: 'permission_denied', detail: 'You do not have permission.', requiredPermission: 'agent_definitions.manage' } });
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('You do not have permission. Needs agent definitions manage');
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
  });

  it('offers a retry when the definition cannot be read', async () => {
    server(undefined, { status: 500, data: { code: 'server_error', detail: 'Down.' } });
    renderIn(<AgentDefinitionScreen agentKey="watch-sweeper" />);
    expect(await screen.findByText('Could not load this agent definition')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
