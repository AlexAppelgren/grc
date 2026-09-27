import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

  it('keeps tenant read closed to a member who can read the register but cannot name an agent', async () => {
    server([]);
    open([...OFFICER, 'register.read']);

    fireEvent.click((await screen.findAllByRole('button', { name: 'Create a token' }))[0] as HTMLElement);
    expect(within(form()).getByLabelText(/^tenant read/)).toBeDisabled();
    expect(form()).toHaveTextContent('Reading our register decisions needs a named agent.');
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

  it('says when a token expired and when it was last used, and offers no revoke on an expired one', async () => {
    server([token('t1', { expiresAt: '2026-09-01T23:59:59Z', lastUsedAt: '2026-08-30T10:15:00Z' })]);
    open(OFFICER);

    const row = await found('[data-token-id="t1"]');
    // The last day is read in the bank's own zone, where 23:59:59 UTC is already the next day.
    expect(row).toHaveTextContent('Created 20 Sept 2026 · expired 2 Sept 2026 · last used 30 Aug 2026, 12:15');
    expect(row.querySelector('[data-pill]')).toHaveTextContent('Expired');
    expect(row).not.toHaveTextContent('never used');
    expect(within(row).queryByRole('button', { name: 'Revoke' })).toBeNull();
  });

  it('copies the new token to the clipboard, and says so only when the copy worked', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockRejectedValueOnce(new Error('denied')).mockResolvedValueOnce(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    server([], (s) => (s.method === 'post' && s.path === TOKENS ? { status: 201, data: { ...token('t9'), plainKey: PLAIN } } : undefined));
    open(OFFICER);

    fireEvent.click((await screen.findAllByRole('button', { name: 'Create a token' }))[0] as HTMLElement);
    fireEvent.change(within(form()).getByLabelText('Name'), { target: { value: 'Laptop' } });
    fireEvent.click(within(form()).getByLabelText(/^library read/));
    fireEvent.change(within(form()).getByLabelText('Expires'), { target: { value: '2026-12-19' } });
    fireEvent.click(within(form()).getByRole('button', { name: 'Create token' }));
    await screen.findByText(PLAIN);

    const copy = screen.getByRole('button', { name: 'Copy token' });
    fireEvent.click(copy);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Copied.')).toBeNull();
    fireEvent.click(copy);
    expect(await screen.findByText('Copied.')).toBeInTheDocument();
    expect(writeText).toHaveBeenLastCalledWith(PLAIN);
  });

  it('asks for a name first, drops a scope unticked again, and closes by Cancel or Escape without a call', async () => {
    const sent = server([]);
    open(OFFICER);

    fireEvent.click((await screen.findAllByRole('button', { name: 'Create a token' }))[0] as HTMLElement);
    fireEvent.click(within(form()).getByRole('button', { name: 'Create token' }));
    expect(await within(form()).findByText('Give it a name.')).toBeInTheDocument();
    expect(within(form()).getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true');

    const library = within(form()).getByLabelText(/^library read/);
    fireEvent.click(library);
    expect(library).toBeChecked();
    fireEvent.click(library);
    expect(library).not.toBeChecked();
    fireEvent.change(within(form()).getByLabelText('Name'), { target: { value: 'Laptop' } });
    fireEvent.click(within(form()).getByRole('button', { name: 'Create token' }));
    expect(await within(form()).findByText('Pick at least one thing it may read.')).toBeInTheDocument();

    fireEvent.click(within(form()).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    fireEvent.click((await screen.findAllByRole('button', { name: 'Create a token' }))[0] as HTMLElement);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('Name')).toHaveValue('');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([]);
  });

  it('keeps a token by Keep it or Escape, and shows a refused revoke inside the dialog', async () => {
    const sent = server([token('t1')], (s) => (s.method === 'delete' ? { status: 409, data: { code: 'already_revoked', detail: 'This token was revoked already.' } } : undefined));
    open(OFFICER);

    const row = await found('[data-token-id="t1"]');
    fireEvent.click(within(row).getByRole('button', { name: 'Revoke' }));
    let dialog = await screen.findByRole('dialog', { name: 'Revoke Order router, my laptop?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep it' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    fireEvent.click(within(row).getByRole('button', { name: 'Revoke' }));
    dialog = await screen.findByRole('dialog', { name: 'Revoke Order router, my laptop?' });
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([]);

    fireEvent.click(within(row).getByRole('button', { name: 'Revoke' }));
    dialog = await screen.findByRole('dialog', { name: 'Revoke Order router, my laptop?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke token' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This token was revoked already.');
    expect(within(row).queryByText('Revoked. The token no longer works.')).toBeNull();
    expect(writes(sent)).toEqual([{ method: 'delete', path: `${TOKENS}/t1`, body: null }]);
  });

  it('offers a retry when the tokens cannot be read, and lists them once it succeeds', async () => {
    let failing = true;
    server([token('t1')], (s) => (s.method === 'get' && s.path === TOKENS && failing ? { status: 503, data: { code: 'unavailable', detail: 'Down in this test.' } } : undefined));
    open(OFFICER);

    expect(await screen.findByRole('heading', { name: 'Could not load your tokens' })).toBeInTheDocument();
    failing = false;
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await found('[data-token-id="t1"]')).toHaveTextContent('Order router, my laptop');
  });

  it('treats a screen outside any permissions context as holding no permission', async () => {
    server([]);
    const { wrapper: Query } = queryWrapper();
    render(
      <Query>
        <LocaleProvider locale="en">
          <TokensScreen />
        </LocaleProvider>
      </Query>,
    );
    const empty = await found('[data-empty-state]');
    expect(screen.queryByRole('button', { name: 'Create a token' })).toBeNull();
    expect(empty).toHaveTextContent('Creating tokens needs tokens create');
  });
});
