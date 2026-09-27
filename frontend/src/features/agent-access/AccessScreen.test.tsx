import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AgentsTabs } from '@/components/admin/AgentsScreen';
import { AccessScreen } from '@/features/agent-access/AccessScreen';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// The Access tab (ACC-01, ACC-02, ACC-08, J-11): the bank's own agents with
// what each reads now, the organisation's switch named with a link and never
// drawn, and Register with its pickers, its own refusals and a passkey.

const V1 = '/api/v1';
const ACCESS = `${V1}/agent-access`;
const REACH = `${V1}/tenant/reach`;
const ADMIN = ['agent_access.manage', 'security.manage', 'watch.read'];
const ACCESS_ONLY = ['agent_access.manage', 'watch.read'];

export const accessEntry = (extra: Record<string, unknown> = {}) => ({
  id: 'e1',
  name: 'Trading platform coding agent',
  purpose: 'Designs and reviews the order-routing service.',
  ownerTeam: { key: 'trading', kind: 'team', label: 'Trading platform team' },
  departments: [{ id: 'd-trading', name: 'Trading' }],
  products: [{ id: 'p-deriv', name: 'Derivatives' }],
  tenantReach: true,
  active: true,
  createdBy: { id: 'u-erik', name: 'Erik Holm' },
  createdAt: '2026-09-12T08:00:00Z',
  revokedAt: null,
  revokedBy: null,
  version: 3,
  keys: [
    { id: 'k1', name: 'Order router CI', keyPrefix: '7c1e40aa', kind: 'service', scopes: ['library:read'], createdAt: '2026-09-12T08:00:00Z', expiresAt: '2099-12-11T08:00:00Z', revokedAt: null, lastUsedAt: '2026-09-25T06:41:00Z', person: null },
    { id: 't1', name: "Anna Berg's token", keyPrefix: 'b44f0e92', kind: 'personal', scopes: ['library:read'], createdAt: '2026-09-20T08:00:00Z', expiresAt: '2099-12-19T08:00:00Z', revokedAt: null, lastUsedAt: null, person: { id: 'u-anna', name: 'Anna Berg' } },
  ],
  ...extra,
});

const unit = (id: string, name: string, parentId: string | null = null) => ({ id, kind: 'business_area', name, parentId, orgNumber: '', lei: '', countryCode: 'SE', entityTerm: null, head: null, active: true, version: 1 });
const product = (id: string, name: string, orgUnitId: string, terms: string[]) => ({ id, name, description: '', status: 'live', launchDate: null, orgUnitId, owner: null, terms: terms.map((key) => ({ key, label: key })), version: 1 });

interface World {
  entries: unknown[];
  reach: { enabled: boolean; changedAt: string | null; changedBy: null; pending: null };
}

function server(world: Partial<World> = {}, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  const w: World = { entries: [accessEntry()], reach: { enabled: true, changedAt: '2026-09-25T07:40:00Z', changedBy: null, pending: null }, ...world };
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.method !== 'get') return { status: 500 };
    if (sent.path === ACCESS) return { status: 200, data: { items: w.entries, total: w.entries.length } };
    if (sent.path === REACH) return { status: 200, data: w.reach };
    if (sent.path === `${V1}/vocab/team`) return { status: 200, data: { items: [{ key: 'trading', label: 'Trading platform team' }, { key: 'procurement', label: 'Procurement' }], total: 2 } };
    if (sent.path === `${V1}/tenant/org-units`) return { status: 200, data: { items: [unit('d-trading', 'Trading'), unit('d-proc', 'Procurement')], total: 2 } };
    if (sent.path === `${V1}/tenant/products`) return { status: 200, data: { items: [product('p-deriv', 'Derivatives', 'd-trading', ['derivatives'])], total: 1 } };
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

function open(permissions: readonly string[], ui = <AccessScreen />) {
  const { wrapper: Query } = queryWrapper();
  return render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <LocaleProvider locale="en">{ui}</LocaleProvider>
      </PermissionsProvider>
    </Query>,
  );
}

const row = () => document.querySelector('[data-entry-id="e1"]') as HTMLElement;
const problem = (code: string, status = 422): Answer => ({ status, data: { code, detail: 'Server words the screen never shows.' } });

describe('agent access tab', () => {
  beforeEach(() => resetApiForTests());

  it('lists an entry with its state, what it reads now, its scope and its credentials', async () => {
    server();
    open(ADMIN);
    await waitFor(() => expect(row()).not.toBeNull());
    expect(within(row()).getByRole('link', { name: 'Trading platform coding agent' })).toHaveAttribute('href', '/admin/agents/access/e1');
    expect(within(row()).getByText('Active')).toHaveAttribute('data-pill', 'positive');
    expect(await within(row()).findByText('Reads our register')).toHaveAttribute('data-pill', 'notice');
    expect(within(row()).getByText('Trading')).toHaveAttribute('data-pill', 'brand');
    expect(within(row()).getByText('Derivatives')).toHaveAttribute('data-pill', 'brand');
    expect(within(row()).getByText('Owned by Trading platform team')).toBeInTheDocument();
    expect(within(row()).getByText(/^1 key, 1 personal token · last used /)).toBeInTheDocument();
    const line = document.querySelector('[data-reach-line="on"]') as HTMLElement;
    expect(within(line).getByRole('link', { name: 'Change it under Security' })).toHaveAttribute('href', '/admin/security');
  });

  it('reads every entry as Library only while the organisation switch is off, and says where to change it', async () => {
    server({ reach: { enabled: false, changedAt: null, changedBy: null, pending: null } });
    open(ADMIN);
    expect(await screen.findByText('Library only')).toHaveAttribute('data-pill', 'information');
    expect(screen.queryByText('Reads our register')).toBeNull();
    const line = document.querySelector('[data-reach-line="off"]') as HTMLElement;
    expect(within(line).getByRole('link', { name: 'Go to Security' })).toHaveAttribute('href', '/admin/security');
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('never reads tenant reach without security.manage, and draws no reach pill it cannot know', async () => {
    const sent = server();
    open(ACCESS_ONLY);
    await waitFor(() => expect(row()).not.toBeNull());
    expect(document.querySelector('[data-reach-line="unknown"]')).not.toBeNull();
    expect(screen.queryByText('Reads our register')).toBeNull();
    expect(screen.queryByText('Library only')).toBeNull();
    expect(sent.some((s) => s.path === REACH)).toBe(false);
  });

  it('shows a revoked entry with who revoked it and no credential line, and an entry naming nothing as the whole scope', async () => {
    server({ entries: [accessEntry({ active: false, revokedAt: '2026-09-19T09:00:00Z', revokedBy: { id: 'u-erik', name: 'Erik Holm' }, departments: [], products: [] })] });
    open(ADMIN);
    await waitFor(() => expect(row()).not.toBeNull());
    expect(within(row()).getByText('Revoked')).toHaveAttribute('data-pill', 'information');
    expect(within(row()).getByText(/^Revoked .* by Erik Holm$/)).toBeInTheDocument();
    expect(within(row()).getByText('All of our regulatory scope')).toBeInTheDocument();
    expect(within(row()).queryByText('Credentials')).toBeNull();
  });

  it('has an empty state', async () => {
    server({ entries: [] });
    open(ADMIN);
    expect(await screen.findByText('No agents registered')).toBeInTheDocument();
  });

  it('says so when the list cannot load', async () => {
    server({}, (s) => (s.path === ACCESS ? { status: 500 } : undefined));
    open(ADMIN);
    expect(await screen.findByText('Could not load the agents')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('registers an agent with its team, departments and products, and refuses a missing name before sending', async () => {
    const sent = server({}, (s) => (s.method === 'post' && s.path === ACCESS ? { status: 201, data: accessEntry({ id: 'e2' }) } : undefined));
    open(ADMIN);
    fireEvent.click(await screen.findByRole('button', { name: 'Register an agent' }));
    const dialog = await screen.findByRole('dialog', { name: 'Register an agent' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Register' }));
    expect(await within(dialog).findByText('Give it a name.')).toBeInTheDocument();
    expect(sent.some((s) => s.method === 'post' && s.path === ACCESS)).toBe(false);

    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: '  Supplier contract reader ' } });
    fireEvent.change(within(dialog).getByLabelText('Purpose'), { target: { value: 'Reads supplier contracts.' } });
    await within(dialog).findByRole('option', { name: 'Procurement' });
    fireEvent.change(within(dialog).getByLabelText('Owned by'), { target: { value: 'procurement' } });
    fireEvent.click(await within(dialog).findByLabelText(/^Trading/));
    fireEvent.click(within(dialog).getByLabelText('Derivatives'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Register' }));

    expect(await screen.findByText('Registered. Issue it a key to let it read.')).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'post' && s.path === ACCESS).map((s) => s.body)).toEqual([
      { name: 'Supplier contract reader', purpose: 'Reads supplier contracts.', ownerTeam: 'procurement', departmentIds: ['d-trading'], productIds: ['p-deriv'] },
    ]);
  });

  it('warns that a department bringing no product would read nothing, and names what each department brings', async () => {
    server();
    open(ADMIN);
    fireEvent.click(await screen.findByRole('button', { name: 'Register an agent' }));
    const dialog = await screen.findByRole('dialog', { name: 'Register an agent' });
    expect(await within(dialog).findByText('No products')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByLabelText(/^Procurement/));
    expect(within(dialog).getByText(/so this agent would read nothing/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByLabelText('Derivatives'));
    expect(within(dialog).queryByText(/so this agent would read nothing/)).toBeNull();
  });

  it('renders a refusal from its code, never the server’s words', async () => {
    server({}, (s) => (s.method === 'post' ? problem('unknown_key') : undefined));
    open(ADMIN);
    fireEvent.click(await screen.findByRole('button', { name: 'Register an agent' }));
    const dialog = await screen.findByRole('dialog', { name: 'Register an agent' });
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'A' } });
    fireEvent.change(within(dialog).getByLabelText('Purpose'), { target: { value: 'B' } });
    await within(dialog).findByRole('option', { name: 'Procurement' });
    fireEvent.change(within(dialog).getByLabelText('Owned by'), { target: { value: 'procurement' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Register' }));
    expect(await within(dialog).findByText('Something you chose is no longer ours to choose. Reload and try again.')).toBeInTheDocument();
    expect(screen.queryByText('Server words the screen never shows.')).toBeNull();
  });

  it('still registers when a picker cannot load, and says the list is missing', async () => {
    server({}, (s) => (s.path === `${V1}/tenant/products` ? problem('not_built', 501) : undefined));
    open(ADMIN);
    fireEvent.click(await screen.findByRole('button', { name: 'Register an agent' }));
    const dialog = await screen.findByRole('dialog', { name: 'Register an agent' });
    expect(await within(dialog).findByText('Could not load this list. You can still save without it.')).toBeInTheDocument();
  });

  it('offers the Access tab only to agent_access.manage', () => {
    const { unmount } = open(['watch.read'], <AgentsTabs current="watch" />);
    expect(screen.queryByRole('link', { name: 'Access' })).toBeNull();
    unmount();
    open(ACCESS_ONLY, <AgentsTabs current="access" />);
    expect(screen.getByRole('link', { name: 'Access' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Watch and research' })).toHaveAttribute('href', '/admin/agents');
  });
});
