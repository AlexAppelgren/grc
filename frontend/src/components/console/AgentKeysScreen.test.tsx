import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ConsoleAgentKeysPage from '@/app/(console)/console/agent-keys/page';
import { AgentKeysScreen } from '@/components/console/AgentKeysScreen';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// Platform agent keys (ID-10, AGT-01, ADM-02): the list bound to its agent,
// creating one behind a passkey, revoking one, and the invariant that decides
// this screen — the plain key is shown once and reaches nothing that survives
// the render.

const ME_PATH = '/api/v1/me';
const KEYS_PATH = '/api/v1/agent-keys';
const DEFINITIONS_PATH = '/api/v1/agent-definitions';

const definitions = {
  items: [
    { id: 'ag2', key: 'proposal-confirmer', description: 'Confirms a proposal another agent made.', currentVersion: 2, active: true },
    { id: 'ag1', key: 'watch-sweeper', description: 'Sweeps the watched sources.', currentVersion: 1, active: true },
  ],
  total: 2,
};

const NOW = new Date('2026-09-19T08:00:00Z');
const PLAIN = 'cw_live_zK9s2Qv7aL4pR1tN6yX3bM8dW5hJ0gC2';

const sweeper = {
  id: 'k1',
  name: 'Watch sweeper, nightly',
  keyPrefix: 'cw_live_zK9s',
  scopes: ['agent-runs:write', 'sources:write'],
  agentId: 'ag1',
  agent: { key: 'watch-sweeper', kind: 'agent', label: 'Watch sweeper v1' },
  createdAt: '2026-09-10T08:00:00Z',
  expiresAt: null,
  revokedAt: null,
  lastUsedAt: '2026-09-19T06:02:00Z',
};

const revoked = { ...sweeper, id: 'k2', name: 'Old sweeper key', revokedAt: '2026-09-12T09:00:00Z', lastUsedAt: null };

const platformAdmin = {
  user: { id: 'u11', email: 'platform@bleqq.test', name: 'Per Ström', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['tenants.manage', 'agent_definitions.manage', 'support_access.grant', 'system.health'],
  platformRoles: [{ key: 'platform_admin', kind: null, label: 'Platform administrator' }],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

function server(keys: Answer, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: platformAdmin };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === KEYS_PATH && sent.method === 'get') return keys;
    if (sent.path === DEFINITIONS_PATH && sent.method === 'get') return { status: 200, data: definitions };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const rowOf = (id: string) => document.querySelector(`[data-agent-key-id="${id}"]`) as HTMLElement;
const writes = (sent: Sent[]) => sent.filter((s) => s.method === 'post' && s.path !== REFRESH_PATH);

async function fillAndSubmit(): Promise<void> {
  fireEvent.click(await screen.findByRole('button', { name: 'Create a key' }));
  const form = await screen.findByRole('dialog', { name: 'Create a key' });
  fireEvent.change(within(form).getByLabelText('Name'), { target: { value: 'Watch sweeper, nightly' } });
  await within(form).findByRole('option', { name: 'watch-sweeper v1' });
  fireEvent.change(within(form).getByLabelText('Agent'), { target: { value: 'ag1' } });
  fireEvent.click(within(form).getByLabelText('agent runs write'));
  fireEvent.click(within(form).getByRole('button', { name: 'Create the key' }));
}

describe('console agent keys', () => {
  beforeEach(() => {
    resetApiForTests();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('lists each key with its agent, its scopes and what it is doing now', async () => {
    server({ status: 200, data: { items: [sweeper, revoked], total: 2 } });
    renderIn(<AgentKeysScreen />);
    await screen.findByText(sweeper.name);

    const live = rowOf('k1');
    expect(within(live).getByText('Watch sweeper v1')).toBeInTheDocument();
    expect(within(live).getByText('agent runs write')).toBeInTheDocument();
    expect(within(live).getByText('sources write')).toBeInTheDocument();
    expect(within(live).getByText('Active')).toBeInTheDocument();
    expect(within(live).getByText('Key cw_live_zK9s')).toBeInTheDocument();
    expect(within(live).getByText('No expiry')).toBeInTheDocument();

    // A revoked key stays listed so the security log has something to point
    // at, and it offers nothing to press.
    const dead = rowOf('k2');
    expect(within(dead).getByText('Revoked')).toBeInTheDocument();
    expect(within(dead).queryByRole('button', { name: 'Revoke' })).toBeNull();
  });

  it('shows the plain key once, and never puts it anywhere that outlives the render', async () => {
    const sent = server({ status: 200, data: { items: [], total: 0 } }, (s) =>
      s.path === KEYS_PATH && s.method === 'post' ? { status: 201, data: { id: 'k3', name: 'Watch sweeper, nightly', keyPrefix: 'cw_live_zK9s', scopes: ['agent-runs:write'], agentId: 'ag1', createdAt: NOW.toISOString(), expiresAt: null, plainKey: PLAIN } } : undefined,
    );
    const { container, unmount } = renderIn(<AgentKeysScreen />);
    await fillAndSubmit();

    const panel = await screen.findByText(PLAIN);
    expect(panel).toBeInTheDocument();
    expect(screen.getByText('Shown once. We keep only a hash of it, so we cannot show it to you again.')).toBeInTheDocument();

    // Nowhere but this one render: not in storage, not in the address, not in
    // a request the screen made afterwards.
    expect(JSON.stringify(Object.entries(window.localStorage))).not.toContain(PLAIN);
    expect(JSON.stringify(Object.entries(window.sessionStorage))).not.toContain(PLAIN);
    expect(window.location.href).not.toContain(PLAIN);
    expect(JSON.stringify(sent.filter((s) => s.method === 'get'))).not.toContain(PLAIN);

    // And there is no way to ask for it again.
    expect(screen.queryByRole('button', { name: /show/i })).toBeNull();
    unmount();
    const again = renderIn(<AgentKeysScreen />);
    await waitFor(() => expect(again.container.textContent).not.toContain(PLAIN));
    expect(container.textContent).toBe('');
  });

  it('offers the agent from the platform definitions, and the confirming scope', async () => {
    server({ status: 200, data: { items: [], total: 0 } });
    renderIn(<AgentKeysScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Create a key' }));
    const form = await screen.findByRole('dialog', { name: 'Create a key' });

    const agent = within(form).getByRole('combobox', { name: 'Agent' });
    await within(agent).findByRole('option', { name: 'watch-sweeper v1' });
    expect(within(agent).getAllByRole('option').map((o) => [o.getAttribute('value'), o.textContent])).toEqual([
      ['', 'Choose an agent'],
      ['ag2', 'proposal-confirmer v2'],
      ['ag1', 'watch-sweeper v1'],
    ]);

    // The confirming agent's key (D-62): it approves through the proposal
    // door, so the hint no longer says a library editor is the only approver.
    expect(within(form).getByLabelText('proposals review')).toBeInTheDocument();
    expect(form).not.toHaveTextContent(/library editor/i);
  });

  it('refuses to create a key without an agent', async () => {
    const sent = server({ status: 200, data: { items: [], total: 0 } });
    renderIn(<AgentKeysScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Create a key' }));
    const form = await screen.findByRole('dialog', { name: 'Create a key' });
    fireEvent.change(within(form).getByLabelText('Name'), { target: { value: 'Watch sweeper, nightly' } });
    fireEvent.click(within(form).getByLabelText('agent runs write'));
    fireEvent.click(within(form).getByRole('button', { name: 'Create the key' }));
    expect(await within(form).findByText('Name the agent this key runs as.')).toBeInTheDocument();
    expect(writes(sent)).toHaveLength(0);
  });

  it('sends the agent, the scopes and the expiry the person chose', async () => {
    const sent = server({ status: 200, data: { items: [], total: 0 } }, (s) =>
      s.path === KEYS_PATH && s.method === 'post' ? { status: 201, data: { id: 'k3', name: 'n', keyPrefix: 'p', scopes: ['agent-runs:write'], agentId: 'ag1', createdAt: NOW.toISOString(), expiresAt: null, plainKey: PLAIN } } : undefined,
    );
    renderIn(<AgentKeysScreen />);
    await fillAndSubmit();
    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    expect(writes(sent)[0]?.body).toEqual({ name: 'Watch sweeper, nightly', agentId: 'ag1', scopes: ['agent-runs:write'] });
  });

  it('says nothing changed when the passkey step-up is refused', async () => {
    server({ status: 200, data: { items: [], total: 0 } }, (s) =>
      s.path === KEYS_PATH && s.method === 'post' ? { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } } : undefined,
    );
    renderIn(<AgentKeysScreen />);
    await fillAndSubmit();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveAttribute('data-problem-code', 'step_up_required');
    expect(alert).toHaveTextContent('The action was not confirmed, so nothing changed.');
    expect(screen.queryByText(PLAIN)).toBeNull();
  });

  it('asks before revoking, and revokes through the real route', async () => {
    const sent = server({ status: 200, data: { items: [sweeper], total: 1 } }, (s) => (s.method === 'post' ? { status: 200, data: { ...sweeper, revokedAt: NOW.toISOString() } } : undefined));
    renderIn(<AgentKeysScreen />);
    await screen.findByText(sweeper.name);

    fireEvent.click(within(rowOf('k1')).getByRole('button', { name: 'Revoke' }));
    expect(within(rowOf('k1')).getByText(/The agent stops working the moment you do/)).toBeInTheDocument();
    fireEvent.click(within(rowOf('k1')).getByRole('button', { name: 'Revoke the key' }));

    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    expect(writes(sent)[0]?.path).toBe('/api/v1/agent-keys/k1/revoke');
  });

  it('says there are no keys yet when the list is empty', async () => {
    server({ status: 200, data: { items: [], total: 0 } });
    renderIn(<AgentKeysScreen />);
    expect(await screen.findByText('No agent keys')).toBeInTheDocument();
  });

  it('offers a retry when the list could not be read', async () => {
    server({ status: 501, data: { code: 'not_built', detail: 'The agent key list is not built yet.' } });
    renderIn(<AgentKeysScreen />);
    expect(await screen.findByText('Could not load the agent keys')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('is loading before the list arrives', () => {
    server({ status: 200, data: { items: [], total: 0 } });
    const { container } = renderIn(<AgentKeysScreen />);
    expect(container.querySelector('[data-loading-state]')).not.toBeNull();
  });

  it('shows the Restricted screen, naming the grant, to a console session without agent_definitions.manage', async () => {
    server({ status: 200, data: { items: [], total: 0 } });
    renderIn(
      <PermissionsProvider permissions={['proposals.review', 'sources.manage']}>
        <ConsoleAgentKeysPage />
      </PermissionsProvider>,
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Needs agent definitions manage');
    expect(screen.queryByRole('button', { name: 'Create a key' })).toBeNull();
  });
});
