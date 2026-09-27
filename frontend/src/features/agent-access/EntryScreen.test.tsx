import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

  it('renders a refused reach change from its code', async () => {
    server({}, (s) => (s.method === 'put' ? problem('invalid_transition', 409) : undefined));
    open();
    const toggle = await screen.findByLabelText(/^Reads our register decisions/);
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);
    const panel = await found('[data-entry-reach]');
    expect(await within(panel).findByText('This agent is revoked, so it cannot change.')).toBeInTheDocument();
    expect(screen.queryByText('Server words the screen never shows.')).toBeNull();
  });

  it('keeps the entry when Revoke is dismissed, and renders a refused revoke from its code', async () => {
    const sent = server({}, (s) => (s.method === 'post' && s.path === `${ENTRY}/revoke` ? problem('stale_write', 409) : undefined));
    open();
    const head = await screen.findByRole('heading', { name: 'Trading platform coding agent' });
    const actions = head.parentElement?.parentElement as HTMLElement;
    fireEvent.click(within(actions).getByRole('button', { name: 'Revoke' }));
    let dialog = await screen.findByRole('dialog', { name: 'Revoke Trading platform coding agent?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep it' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    fireEvent.click(within(actions).getByRole('button', { name: 'Revoke' }));
    dialog = await screen.findByRole('dialog', { name: 'Revoke Trading platform coding agent?' });
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([]);

    fireEvent.click(within(actions).getByRole('button', { name: 'Revoke' }));
    dialog = await screen.findByRole('dialog', { name: 'Revoke Trading platform coding agent?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke the agent' }));
    expect(await within(dialog).findByText('Someone else changed this agent first. Nothing was saved.')).toBeInTheDocument();
    expect(screen.queryByText('Revoked. Its credentials stopped working.')).toBeNull();
  });

  it('dates a revoked entry nobody is named for from when it was registered, with nothing left to issue or revoke', async () => {
    server({ entry: accessEntry({ active: false, revokedAt: null, revokedBy: null }) });
    open();
    const note = await found('[data-entry-revoked]');
    expect(note.textContent).toMatch(/^Revoked .*2026/);
    expect(note.textContent).not.toContain(' by ');
    expect(note).toHaveTextContent('Its credentials stopped working. The entry and its access log stay, read-only.');
    expect(screen.queryByRole('button', { name: 'Revoke' })).toBeNull();
    expect(screen.queryByText('Changing it asks for your passkey.')).toBeNull();
  });

  it('names who revoked an entry that carries no revocation date', async () => {
    server({ entry: accessEntry({ active: false, revokedAt: null, revokedBy: { id: 'u-erik', name: 'Erik Holm' } }) });
    open();
    const note = await found('[data-entry-revoked]');
    expect(note.textContent).toMatch(/^Revoked .*2026.* by Erik Holm /);
  });

  it('says so when the entry cannot load, and tries again', async () => {
    let failed = false;
    const sent = server({}, (s) => {
      if (s.path !== ENTRY || failed) return undefined;
      failed = true;
      return { status: 500 };
    });
    open();
    expect(await screen.findByText('Could not load this agent')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Trading platform coding agent' })).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'get' && s.path === ENTRY)).toHaveLength(2);
  });

  it('saves an edit with its version and closes, and Cancel closes without sending', async () => {
    const sent = server({}, (s) => (s.method === 'patch' ? { status: 200, data: accessEntry({ name: 'Order router agent', version: 4 }) } : undefined));
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    let dialog = await screen.findByRole('dialog', { name: 'Edit Trading platform coding agent' });
    expect(within(dialog).getByText('A change applies to its next call.')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    dialog = await screen.findByRole('dialog', { name: 'Edit Trading platform coding agent' });
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Order router agent' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([
      { method: 'patch', path: ENTRY, body: { name: 'Order router agent', purpose: 'Designs and reviews the order-routing service.', ownerTeam: 'trading', departmentIds: ['d-trading'], productIds: ['p-deriv'] } },
    ]);
    expect(await screen.findByRole('heading', { name: 'Order router agent' })).toBeInTheDocument();
  });

  it('refuses an issue without a name, lets a chosen scope go again, and closes on Cancel or Escape without sending', async () => {
    const sent = server();
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Issue a key' }));
    let dialog = await screen.findByRole('dialog', { name: 'Issue a key for Trading platform coding agent' });
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: '   ' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Issue key' }));
    expect(await within(dialog).findByText('Give the key a name.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true');
    const library = within(dialog).getByLabelText(/^library read/);
    fireEvent.click(library);
    expect(library).toBeChecked();
    fireEvent.click(library);
    expect(library).not.toBeChecked();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Issue a key' }));
    dialog = await screen.findByRole('dialog', { name: 'Issue a key for Trading platform coding agent' });
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([]);
  });

  it('sends a chosen expiry as the end of that day in UTC', async () => {
    const created = { id: 'k9', name: 'Nightly', keyPrefix: '9a1f3c7e', kind: 'service', scopes: ['library:read'], createdAt: '2026-09-25T08:00:00Z', expiresAt: '2026-12-24T23:59:59Z', revokedAt: null, lastUsedAt: null, person: null, plainKey: PLAIN };
    const sent = server({}, (s) => (s.method === 'post' && s.path === `${ENTRY}/keys` ? { status: 201, data: created } : undefined));
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Issue a key' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Nightly' } });
    fireEvent.click(within(dialog).getByLabelText(/^library read/));
    fireEvent.change(within(dialog).getByLabelText('Expires'), { target: { value: '2026-12-24' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Issue key' }));
    expect(await screen.findByText(PLAIN)).toBeInTheDocument();
    expect(writes(sent)).toEqual([{ method: 'post', path: `${ENTRY}/keys`, body: { name: 'Nightly', scopes: ['library:read'], expiresAt: '2026-12-24T23:59:59Z' } }]);
  });

  describe('copying a new key', () => {
    const created = { id: 'k9', name: 'Nightly', keyPrefix: '9a1f3c7e', kind: 'service', scopes: ['search:read'], createdAt: '2026-09-25T08:00:00Z', expiresAt: null, revokedAt: null, lastUsedAt: null, person: null, plainKey: PLAIN };
    const original = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
    afterEach(() => {
      if (original) Object.defineProperty(navigator, 'clipboard', original);
      else Reflect.deleteProperty(navigator, 'clipboard');
    });

    async function issue(): Promise<HTMLElement> {
      server({}, (s) => (s.method === 'post' && s.path === `${ENTRY}/keys` ? { status: 201, data: created } : undefined));
      open();
      fireEvent.click(await screen.findByRole('button', { name: 'Issue a key' }));
      const dialog = await screen.findByRole('dialog');
      fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Nightly' } });
      fireEvent.click(within(dialog).getByLabelText(/^search read/));
      fireEvent.click(within(dialog).getByRole('button', { name: 'Issue key' }));
      return found('[data-new-key]');
    }

    it('copies the plain key and says so', async () => {
      const writeText = vi.fn(() => Promise.resolve());
      Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
      const panel = await issue();
      fireEvent.click(within(panel).getByRole('button', { name: 'Copy key' }));
      expect(await within(panel).findByText('Copied.')).toBeInTheDocument();
      expect(writeText).toHaveBeenCalledWith(PLAIN);
    });

    it('claims no copy when the clipboard refuses', async () => {
      const writeText = vi.fn(() => Promise.reject(new Error('denied')));
      Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
      const panel = await issue();
      fireEvent.click(within(panel).getByRole('button', { name: 'Copy key' }));
      await waitFor(() => expect(writeText).toHaveBeenCalledWith(PLAIN));
      expect(within(panel).queryByText('Copied.')).toBeNull();
      expect(within(panel).getByText(PLAIN)).toBeInTheDocument();
    });
  });

  it('says when there is no key yet, and dates expired, revoked and open-ended keys without a revoke for the dead ones', async () => {
    const base = { kind: 'service', scopes: ['library:read'], createdAt: '2026-01-10T08:00:00Z', lastUsedAt: null, person: null, revokedAt: null };
    server({
      entry: accessEntry({
        keys: [
          { ...base, id: 'kx', name: 'Old CI', keyPrefix: 'aa000001', expiresAt: '2026-02-01T08:00:00Z' },
          { ...base, id: 'kr', name: 'Retired CI', keyPrefix: 'aa000002', expiresAt: null, revokedAt: '2026-03-01T08:00:00Z' },
          { ...base, id: 'ko', name: 'Open CI', keyPrefix: 'aa000003', expiresAt: null },
        ],
      }),
    });
    const { unmount } = open();
    const expired = await found('[data-key-id="kx"]');
    expect(within(expired).getByText('Expired')).toHaveAttribute('data-pill', 'warning');
    expect(within(expired).getByText(/^Issued .* · expired .* · never used$/)).toBeInTheDocument();
    expect(within(expired).queryByRole('button', { name: 'Revoke' })).toBeNull();
    const revoked = document.querySelector('[data-key-id="kr"]') as HTMLElement;
    expect(within(revoked).getByText(/^Issued .* · revoked .* · never used$/)).toBeInTheDocument();
    expect(within(revoked).queryByRole('button', { name: 'Revoke' })).toBeNull();
    const openEnded = document.querySelector('[data-key-id="ko"]') as HTMLElement;
    expect(within(openEnded).getByText(/^Issued [^·]+ · never used$/)).toBeInTheDocument();
    expect(within(openEnded).getByRole('button', { name: 'Revoke' })).toBeInTheDocument();
    unmount();

    resetApiForTests();
    server({ entry: accessEntry({ keys: [] }) });
    open();
    expect(await screen.findByText('No keys yet. Issue one so the agent can read.')).toBeInTheDocument();
    expect(document.querySelector('[data-keys-list]')).toBeNull();
  });

  it('keeps a key when its revoke is dismissed, and renders a refused revoke from its code', async () => {
    const sent = server({}, (s) => (s.method === 'post' && s.path === `${ENTRY}/keys/k1/revoke` ? problem('invalid_transition', 409) : undefined));
    open();
    const service = await found('[data-key-id="k1"]');
    fireEvent.click(within(service).getByRole('button', { name: 'Revoke' }));
    let dialog = await screen.findByRole('dialog', { name: 'Revoke Order router CI?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep it' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    fireEvent.click(within(service).getByRole('button', { name: 'Revoke' }));
    dialog = await screen.findByRole('dialog', { name: 'Revoke Order router CI?' });
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([]);

    fireEvent.click(within(service).getByRole('button', { name: 'Revoke' }));
    dialog = await screen.findByRole('dialog', { name: 'Revoke Order router CI?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke key' }));
    expect(await within(dialog).findByText('This agent is revoked, so it cannot change.')).toBeInTheDocument();
  });

  it('names a call with no filter, no count and the whole scope, and pages back to newer calls', async () => {
    const sent = server({ calls: [call('c1', { filters: {}, recordCount: null, scope: { narrowed: false, terms: {} } })], total: 45 });
    open();
    const row = await found('[data-call-id="c1"]');
    expect(within(row).getByText('None')).toBeInTheDocument();
    expect(within(row).getByText('Not counted')).toBeInTheDocument();
    expect(within(row).getByText('Whole scope')).toBeInTheDocument();
    expect(within(row).getByText('—')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Older' }));
    await waitFor(() => expect(screen.getByText('21 to 21 of 45')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Newer' }));
    await waitFor(() => expect(screen.getByText('1 to 1 of 45')).toBeInTheDocument());
    const pages = sent.filter((s) => s.path === CALLS).map((s) => s.params);
    expect(pages.slice(0, 2)).toEqual([
      { limit: 20, offset: 0 },
      { limit: 20, offset: 20 },
    ]);
    expect(pages.at(-1)).toEqual({ limit: 20, offset: 0 });
  });

  it('says so when the access log cannot load, and tries again', async () => {
    let failed = false;
    const sent = server({}, (s) => {
      if (s.path !== CALLS || failed) return undefined;
      failed = true;
      return { status: 500 };
    });
    open();
    expect(await screen.findByText('Could not load the access log')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await found('[data-call-id="c1"]')).toBeInTheDocument();
    expect(sent.filter((s) => s.path === CALLS)).toHaveLength(2);
  });

  it('answers another bank’s entry, or none, with Not found', async () => {
    server({}, (s) => (s.path === ENTRY ? problem('not_found', 404) : undefined));
    open();
    expect(await screen.findByText('There is nothing at this address in your organisation.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Access' })).toHaveAttribute('href', '/admin/agents/access');
  });
});
