import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { TokensScreen } from '@/features/personal-tokens/TokensScreen';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// My access tokens (ACC-03, me-tokens.html): minted with scopes the member's
// own permissions back, an optional entry and a required expiry, shown once,
// listed and revoked; without tokens.create there is no Create button and
// what the member holds stays revocable.

const TOKENS = '/api/v1/me/tokens';
const ENTRIES = '/api/v1/agent-access';
/** A token shown once; test data, never a real secret. */
const PLAIN = 'shown-once-test-value';
const OFFICER = ['tokens.create', 'library.read', 'search.use', 'roadmap.read'];

const token = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  name: 'Order router, my laptop',
  keyPrefix: 'b44f0e92',
  scopes: ['library:read'],
  agentAccess: null,
  createdAt: '2026-09-20T09:00:00Z',
  expiresAt: '2099-12-19T23:59:59Z',
  revokedAt: null,
  lastUsedAt: null,
  ...extra,
});

function server(items: unknown[], extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.method === 'get' && sent.path === TOKENS) return { status: 200, data: { items, total: items.length } };
    if (sent.method === 'get' && sent.path === ENTRIES) {
      return { status: 200, data: { items: [{ id: 'e1', name: 'Trading platform coding agent', active: true }, { id: 'e2', name: 'Retired helper', active: false }], total: 2 } };
    }
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

function open(permissions: readonly string[]) {
  const { wrapper: Query } = queryWrapper();
  return render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <LocaleProvider locale="en">
          <TokensScreen />
        </LocaleProvider>
      </PermissionsProvider>
    </Query>,
  );
}

const writes = (sent: Sent[]) => sent.filter((s) => s.method !== 'get' && s.path !== REFRESH_PATH).map((s) => ({ method: s.method, path: s.path, body: s.body }));
const form = () => document.querySelector('[data-token-form]') as HTMLElement;
/** The element once it renders; waitFor retries until the query finds it. */
const found = (selector: string): Promise<HTMLElement> =>
  waitFor(() => {
    const element = document.querySelector<HTMLElement>(selector);
    expect(element).not.toBeNull();
    return element as HTMLElement;
  });

describe('my access tokens', () => {
  beforeEach(() => {
    resetApiForTests();
  });

  it('lists the member own tokens with what each reads as and its state', async () => {
    server([token('t1', { agentAccess: { id: 'e1', name: 'Trading platform coding agent' } }), token('t2', { name: 'Old notebook', revokedAt: '2026-09-10T08:00:00Z' })]);
    open(OFFICER);

    const live = await found('[data-token-id="t1"]');
    expect(live).toHaveTextContent('cw_b44f0e92…');
    expect(live).toHaveTextContent('reads as me within Trading platform coding agent');
    expect(live).toHaveTextContent('library read');
    expect(within(live).getByRole('button', { name: 'Revoke' })).toBeInTheDocument();

    const revoked = document.querySelector('[data-token-id="t2"]') as HTMLElement;
    expect(revoked).toHaveTextContent('Revoked');
    expect(within(revoked).queryByRole('button', { name: 'Revoke' })).toBeNull();
  });

  it('mints a token with its scopes, entry and expiry, and shows it once', async () => {
    const sent = server([], (s) =>
      s.method === 'post' && s.path === TOKENS ? { status: 201, data: { ...token('t9', { scopes: ['library:read', 'tenant:read'], agentAccess: { id: 'e1', name: 'Trading platform coding agent' } }), plainKey: PLAIN } } : undefined,
    );
    open([...OFFICER, 'register.read', 'agent_access.manage']);

    fireEvent.click((await screen.findAllByRole('button', { name: 'Create a token' }))[0] as HTMLElement);
    fireEvent.change(within(form()).getByLabelText('Name'), { target: { value: '  Order router, my laptop ' } });
    fireEvent.click(within(form()).getByLabelText(/^library read/));
    fireEvent.click(within(form()).getByLabelText(/^tenant read/));
    // tenant:read reaches the register only through a named entry.
    fireEvent.click(within(form()).getByRole('button', { name: 'Create token' }));
    expect(await within(form()).findByText('Reading our register decisions needs a named agent.')).toBeInTheDocument();

    const entry = within(form()).getByLabelText('Read as an agent');
    await waitFor(() => expect(within(entry).getByRole('option', { name: 'Trading platform coding agent' })).toBeInTheDocument());
    expect(within(entry).queryByRole('option', { name: 'Retired helper' })).toBeNull();
    fireEvent.change(entry, { target: { value: 'e1' } });
    fireEvent.change(within(form()).getByLabelText('Expires'), { target: { value: '2026-12-19' } });
    fireEvent.click(within(form()).getByRole('button', { name: 'Create token' }));

    expect(await screen.findByText(PLAIN)).toBeInTheDocument();
    expect(writes(sent)).toEqual([
      { method: 'post', path: TOKENS, body: { name: 'Order router, my laptop', scopes: ['library:read', 'tenant:read'], expiresAt: '2026-12-19T23:59:59Z', agentAccessId: 'e1' } },
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByText(PLAIN)).toBeNull();
  });

  it('offers only the scopes the member own permissions back, and no entry without the entry list', async () => {
    const sent = server([]);
    open(OFFICER);

    fireEvent.click((await screen.findAllByRole('button', { name: 'Create a token' }))[0] as HTMLElement);
    const tenantRead = within(form()).getByLabelText(/^tenant read/);
    expect(tenantRead).toBeDisabled();
    expect(form()).toHaveTextContent('Needs register read, which your role does not include.');
    expect(within(form()).getByLabelText(/^library read/)).not.toBeDisabled();
    expect(within(form()).queryByLabelText('Read as an agent')).toBeNull();
    expect(sent.some((s) => s.path === ENTRIES)).toBe(false);

    // Nothing picked and no expiry: refused in place, before any call.
    fireEvent.change(within(form()).getByLabelText('Name'), { target: { value: 'Policy drafting assistant' } });
    fireEvent.click(within(form()).getByRole('button', { name: 'Create token' }));
    expect(await within(form()).findByText('Pick at least one thing it may read.')).toBeInTheDocument();
    fireEvent.click(within(form()).getByLabelText(/^search read/));
    fireEvent.click(within(form()).getByRole('button', { name: 'Create token' }));
    expect(await within(form()).findByText('Choose when it expires.')).toBeInTheDocument();
    expect(writes(sent)).toEqual([]);
  });

  it('renders the server refusal of a too distant expiry from its code', async () => {
    server([], (s) => (s.method === 'post' ? { status: 422, data: { code: 'expiry_too_late', detail: 'Server words the screen never shows.' } } : undefined));
    open(OFFICER);

    fireEvent.click((await screen.findAllByRole('button', { name: 'Create a token' }))[0] as HTMLElement);
    fireEvent.change(within(form()).getByLabelText('Name'), { target: { value: 'Laptop' } });
    fireEvent.click(within(form()).getByLabelText(/^library read/));
    fireEvent.change(within(form()).getByLabelText('Expires'), { target: { value: '2099-01-01' } });
    fireEvent.click(within(form()).getByRole('button', { name: 'Create token' }));
    expect(await within(form()).findByText('That is further ahead than a token may live. Choose an earlier date.')).toBeInTheDocument();
  });

  it('without tokens.create says why and still revokes a token held', async () => {
    const sent = server([token('t1')], (s) => (s.method === 'delete' ? { status: 204 } : undefined));
    open(['library.read']);

    const row = await found('[data-token-id="t1"]');
    expect(screen.queryByRole('button', { name: 'Create a token' })).toBeNull();
    expect(screen.getByText('Creating tokens needs tokens create, which your role does not include. Ask your administrator if you need one.')).toBeInTheDocument();

    fireEvent.click(within(row).getByRole('button', { name: 'Revoke' }));
    const dialog = await screen.findByRole('dialog', { name: 'Revoke Order router, my laptop?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke token' }));
    expect(await within(row).findByText('Revoked. The token no longer works.')).toBeInTheDocument();
    expect(writes(sent)).toEqual([{ method: 'delete', path: `${TOKENS}/t1`, body: null }]);
  });

  it('shows the empty state without a Create action to a member who may not mint', async () => {
    server([]);
    open(['library.read']);
    const empty = await found('[data-empty-state]');
    expect(empty).toHaveTextContent('No tokens');
    expect(within(empty).queryByText('Create a token')).toBeNull();
  });
});
