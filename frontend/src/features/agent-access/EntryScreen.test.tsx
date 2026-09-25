import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { accessEntry } from '@/features/agent-access/AccessScreen.test';
import { EntryScreen } from '@/features/agent-access/EntryScreen';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// One entry (ACC-01, ACC-02, ACC-03, ACC-08, J-11): what it reads, its own
// half of tenant reach, credentials issued once and revoked, revoking the
// entry for good, the access log paged, and Not found for another bank's.

const V1 = '/api/v1';
const ENTRY = `${V1}/agent-access/e1`;
const CALLS = `${ENTRY}/calls`;
const REACH = `${V1}/tenant/reach`;
const ADMIN = ['agent_access.manage', 'security.manage'];
/** A key shown once; test data, never a real secret. */
const PLAIN = 'shown-once-test-value';

const call = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  at: '2026-09-25T06:41:00Z',
  credential: { id: 'k1', keyPrefix: '7c1e40aa', kind: 'service' },
  person: null,
  tool: 'listObligations',
  filters: { jurisdiction: ['se'], binding: [] },
  recordCount: 11,
  scopes: ['library:read'],
  scope: { narrowed: true, terms: { product_type: ['derivatives', 'securities'] } },
  durationMs: 412,
  status: 200,
  ...extra,
});

interface World {
  entry: Record<string, unknown>;
  orgReach: boolean;
  calls: unknown[];
  total: number;
}

function server(world: Partial<World> = {}, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  const w: World = { entry: accessEntry(), orgReach: true, calls: [call('c1')], total: 1, ...world };
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.method !== 'get') return { status: 500 };
    if (sent.path === ENTRY) return { status: 200, data: w.entry };
    if (sent.path === CALLS) return { status: 200, data: { items: w.calls, total: w.total } };
    if (sent.path === REACH) return { status: 200, data: { enabled: w.orgReach, changedAt: null, changedBy: null, pending: null } };
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

function open(permissions: readonly string[] = ADMIN) {
  const { wrapper: Query } = queryWrapper();
  return render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <LocaleProvider locale="en">
          <EntryScreen entryId="e1" />
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
const writes = (sent: Sent[]) => sent.filter((s) => s.method !== 'get' && s.path !== REFRESH_PATH).map((s) => ({ method: s.method, path: s.path, body: s.body }));
const problem = (code: string, status = 422): Answer => ({ status, data: { code, detail: 'Server words the screen never shows.' } });

describe('agent access entry page', () => {
  beforeEach(() => resetApiForTests());

  it('shows what the entry reads, who registered it and its credentials with their kind', async () => {
    server();
    open();
    expect(await screen.findByRole('heading', { name: 'Trading platform coding agent' })).toBeInTheDocument();
    expect(screen.getByText(/^Registered .* by Erik Holm$/)).toBeInTheDocument();
    const token = document.querySelector('[data-key-id="t1"]') as HTMLElement;
    expect(within(token).getByText('Personal')).toHaveAttribute('data-pill', 'information');
    expect(within(token).getByText('acts as Anna Berg')).toBeInTheDocument();
    const service = document.querySelector('[data-key-id="k1"]') as HTMLElement;
    expect(within(service).getByText('Service')).toHaveAttribute('data-pill', 'information');
    expect(within(service).getByText('cw_7c1e40aa…')).toBeInTheDocument();
  });

  it('switches the entry’s own reach with its version, and disables it with the reason while the organisation switch is off', async () => {
    const sent = server({}, (s) => (s.method === 'put' ? { status: 200, data: accessEntry({ tenantReach: false, version: 4 }) } : undefined));
    const { unmount } = open();
    const toggle = await screen.findByLabelText(/^Reads our register decisions/);
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    await waitFor(() => expect(writes(sent)).toEqual([{ method: 'put', path: `${ENTRY}/tenant-reach`, body: { enabled: false } }]));
    unmount();

    resetApiForTests();
    server({ orgReach: false });
    open();
    const off = await screen.findByText(/Our register stays in bleqq until two people/);
    expect(within(off).getByRole('link', { name: 'Go to Security' })).toHaveAttribute('href', '/admin/security');
    expect(screen.getByLabelText(/^Reads our register decisions/)).toBeDisabled();
  });

  it('issues a key with the read scopes chosen, shows it once and refuses one without a scope', async () => {
    const created = { id: 'k9', name: 'Nightly', keyPrefix: '9a1f3c7e', kind: 'service', scopes: ['search:read'], createdAt: '2026-09-25T08:00:00Z', expiresAt: '2026-12-24T08:00:00Z', revokedAt: null, lastUsedAt: null, person: null, plainKey: PLAIN };
    const sent = server({}, (s) => (s.method === 'post' && s.path === `${ENTRY}/keys` ? { status: 201, data: created } : undefined));
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Issue a key' }));
    const dialog = await screen.findByRole('dialog', { name: 'Issue a key for Trading platform coding agent' });
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Nightly' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Issue key' }));
    expect(await within(dialog).findByText('Choose at least one thing it may read.')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText(/proposals write/)).toBeNull();

    fireEvent.click(within(dialog).getByLabelText(/^search read/));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Issue key' }));
    expect(await screen.findByText(PLAIN)).toBeInTheDocument();
    expect(writes(sent)).toEqual([{ method: 'post', path: `${ENTRY}/keys`, body: { name: 'Nightly', scopes: ['search:read'], expiresAt: null } }]);
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByText(PLAIN)).toBeNull();
  });

  it('renders an expiry past the limit from its code', async () => {
    server({}, (s) => (s.method === 'post' && s.path === `${ENTRY}/keys` ? problem('expiry_too_late') : undefined));
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Issue a key' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Nightly' } });
    fireEvent.click(within(dialog).getByLabelText(/^library read/));
    fireEvent.change(within(dialog).getByLabelText('Expires'), { target: { value: '2099-01-01' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Issue key' }));
    expect(await within(dialog).findByText(/further ahead than a key may live/)).toBeInTheDocument();
  });

  it('revokes one key after a confirmation', async () => {
    const sent = server({}, (s) => (s.method === 'post' && s.path === `${ENTRY}/keys/k1/revoke` ? { status: 200, data: {} } : undefined));
    open();
    const service = await found('[data-key-id="k1"]');
    fireEvent.click(within(service).getByRole('button', { name: 'Revoke' }));
    const dialog = await screen.findByRole('dialog', { name: 'Revoke Order router CI?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke key' }));
    await waitFor(() => expect(writes(sent)).toEqual([{ method: 'post', path: `${ENTRY}/keys/k1/revoke`, body: {} }]));
  });

  it('revokes the entry after a confirmation and leaves it read-only', async () => {
    let revoked = false;
    const gone = accessEntry({ active: false, revokedAt: '2026-09-25T09:00:00Z', revokedBy: { id: 'u-erik', name: 'Erik Holm' }, version: 4 });
    const sent = server({}, (s) => {
      if (s.method === 'post' && s.path === `${ENTRY}/revoke`) {
        revoked = true;
        return { status: 200, data: gone };
      }
      return s.method === 'get' && s.path === ENTRY && revoked ? { status: 200, data: gone } : undefined;
    });
    open();
    const head = await screen.findByRole('heading', { name: 'Trading platform coding agent' });
    fireEvent.click(within(head.parentElement?.parentElement as HTMLElement).getByRole('button', { name: 'Revoke' }));
    const dialog = await screen.findByRole('dialog', { name: 'Revoke Trading platform coding agent?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke the agent' }));
    expect(await screen.findByText('Revoked. Its credentials stopped working.')).toBeInTheDocument();
    expect(writes(sent)).toEqual([{ method: 'post', path: `${ENTRY}/revoke`, body: {} }]);
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Issue a key' })).toBeNull();
    expect(screen.getByLabelText(/^Reads our register decisions/)).toBeDisabled();
  });

  it('renders a stale edit in place with a way to load the latest', async () => {
    const sent = server({}, (s) => (s.method === 'patch' ? problem('stale_write', 409) : undefined));
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Trading platform coding agent' });
    expect(within(dialog).getByLabelText('Name')).toHaveValue('Trading platform coding agent');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText(/Someone else changed this agent while you were editing/)).toBeInTheDocument();
    const reads = sent.filter((s) => s.method === 'get' && s.path === ENTRY).length;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Load the latest' }));
    await waitFor(() => expect(sent.filter((s) => s.method === 'get' && s.path === ENTRY).length).toBe(reads + 1));
  });

  it('reads the access log without content and pages it', async () => {
    const sent = server({ calls: [call('c1', { person: { id: 'u-anna', name: 'Anna Berg' }, credential: { id: 't1', keyPrefix: 'b44f0e92', kind: 'personal' } })], total: 45 });
    open();
    const row = await found('[data-call-id="c1"]');
    expect(within(row).getAllByText('List obligations').length).toBeGreaterThan(0);
    expect(within(row).getByText('Jurisdiction, Binding')).toBeInTheDocument();
    expect(within(row).getByText('Anna Berg')).toBeInTheDocument();
    expect(within(row).getByText('2 terms')).toBeInTheDocument();
    expect(within(row).getByText('412 ms')).toBeInTheDocument();
    expect(screen.getByText('1 to 1 of 45')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Newer' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Older' }));
    await waitFor(() => expect(sent.filter((s) => s.path === CALLS).map((s) => s.params)).toEqual([{ limit: 20, offset: 0 }, { limit: 20, offset: 20 }]));
  });

  it('says when the agent has made no call yet', async () => {
    server({ calls: [], total: 0 });
    open();
    expect(await screen.findByText('No calls yet')).toBeInTheDocument();
  });

  it('answers another bank’s entry, or none, with Not found', async () => {
    server({}, (s) => (s.path === ENTRY ? problem('not_found', 404) : undefined));
    open();
    expect(await screen.findByText('There is nothing at this address in your organisation.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Access' })).toHaveAttribute('href', '/admin/agents/access');
  });
});
