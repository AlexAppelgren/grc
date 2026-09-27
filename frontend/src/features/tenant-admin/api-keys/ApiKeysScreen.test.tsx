import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API_KEY_SCOPES, ApiKeysScreen } from '@/features/tenant-admin/api-keys/ApiKeysScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// A bank's API keys (ID-10): the create form offers the scopes a bank's key
// may hold and nothing else. The watch writes are the platform's own agents'
// (D-61); offering them here would only earn a refusal from the server.

const admin = {
  user: { id: 'u1', email: 'erik@bank.example', name: 'Erik Holm', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['integrations.manage'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

const KEYS = '/api/v1/tenant/api-keys';
const entry = { id: 'e1', name: 'Trading platform coding agent' };
const credential = (id: string, extra: Record<string, unknown>) => ({
  id,
  name: 'GRC export sync',
  keyPrefix: 'a1b2c3d4',
  scopes: ['library:read'],
  createdAt: '2026-09-19T09:00:00Z',
  expiresAt: null,
  revokedAt: null,
  lastUsedAt: null,
  kind: 'service',
  agentAccess: null,
  person: null,
  ...extra,
});

// `answer` scripts a call before the defaults; returning undefined falls through.
function renderScreen(items: unknown[] = [], answer: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  const sent = installAdapter((sent) => {
    const scripted = answer(sent);
    if (scripted !== undefined) return scripted;
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === '/api/v1/me') return { status: 200, data: admin };
    if (sent.method === 'get' && sent.path === KEYS) return { status: 200, data: { items, total: items.length } };
    if (sent.method === 'delete') return { status: 204 };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <ApiKeysScreen />
    </Query>,
  );
  return sent;
}

const row = (id: string): Promise<HTMLElement> =>
  waitFor(() => {
    const element = document.querySelector<HTMLElement>(`[data-key-id="${id}"]`);
    expect(element).not.toBeNull();
    return element as HTMLElement;
  });

describe('bank API keys', () => {
  beforeEach(() => {
    resetApiForTests();
  });

  it('offers the scopes a bank key may hold and no watch write', async () => {
    renderScreen();
    fireEvent.click((await screen.findAllByRole('button', { name: 'Create a key' }))[0] as HTMLElement);
    const form = document.querySelector('[data-key-form]') as HTMLElement;

    expect(API_KEY_SCOPES).toEqual(['tenant:read', 'library:read', 'upcoming:read', 'search:read', 'proposals:write']);
    for (const label of ['tenant read', 'library read', 'upcoming read', 'search read', 'proposals write']) {
      expect(within(form).getByLabelText(new RegExp(`^${label}`))).toBeInTheDocument();
    }
    for (const label of ['agent runs write', 'sources write', 'changes write', 'proposals review']) {
      expect(within(form).queryByLabelText(new RegExp(`^${label}`))).toBeNull();
    }
  });

  it('lists every credential with its kind and who it reads as', async () => {
    renderScreen([
      credential('k1', {}),
      credential('k2', { name: 'Order router CI', agentAccess: entry }),
      credential('k3', { name: 'Order router, my laptop', kind: 'personal', agentAccess: entry, person: { id: 'u1', name: 'Anna Berg' } }),
      credential('k4', { name: 'Old connector', expiresAt: '2026-09-01T00:00:00Z' }),
    ]);

    expect(await row('k1')).toHaveTextContent('For an integration');
    expect(await row('k1')).toHaveTextContent('Service');
    expect(await row('k2')).toHaveTextContent('Reads as Trading platform coding agent');
    const token = await row('k3');
    expect(token).toHaveTextContent('Personal');
    expect(token).toHaveTextContent('Acts as Anna Berg, within Trading platform coding agent');
    expect(token).toHaveTextContent('cw_a1b2c3d4…');
    const expired = await row('k4');
    expect(expired).toHaveTextContent('Expired');
    expect(within(expired).queryByRole('button', { name: 'Revoke' })).toBeNull();
  });

  it('revokes a member token after naming the person, with no passkey', async () => {
    const sent = renderScreen([credential('k3', { name: 'Order router, my laptop', kind: 'personal', person: { id: 'u1', name: 'Anna Berg' } })]);

    fireEvent.click(within(await row('k3')).getByRole('button', { name: 'Revoke' }));
    const dialog = await screen.findByRole('dialog', { name: 'Revoke Anna Berg\'s token "Order router, my laptop"?' });
    expect(dialog).toHaveTextContent("Its next call is refused. It stays on Anna Berg's list and this one as revoked.");
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke token' }));

    expect(await within(await row('k3')).findByText('Token revoked.')).toBeInTheDocument();
    expect(sent.filter((s) => s.method === 'delete').map((s) => s.path)).toEqual([`${KEYS}/k3`]);
  });

  it('revokes an integration key, showing a refusal and then the revocation', async () => {
    let deletes = 0;
    const sent = renderScreen([credential('k1', {})], (s) => {
      if (s.method !== 'delete') return undefined;
      deletes += 1;
      return deletes === 1 ? { status: 409, data: { code: 'conflict', detail: 'The key is in use by a running export.' } } : undefined;
    });

    fireEvent.click(within(await row('k1')).getByRole('button', { name: 'Revoke' }));
    const dialog = await screen.findByRole('dialog', { name: 'Revoke GRC export sync?' });
    expect(dialog).toHaveTextContent('Anything using it stops working now.');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke key' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('The key is in use by a running export.');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke key' }));
    expect(await within(await row('k1')).findByText('Key revoked.')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(sent.filter((s) => s.method === 'delete').map((s) => s.path)).toEqual([`${KEYS}/k1`, `${KEYS}/k1`]);
  });

  it('keeps a key when the confirmation is dismissed, by button or by Escape', async () => {
    const sent = renderScreen([credential('k1', {})]);

    fireEvent.click(within(await row('k1')).getByRole('button', { name: 'Revoke' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Keep it' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    fireEvent.click(within(await row('k1')).getByRole('button', { name: 'Revoke' }));
    fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    expect(sent.filter((s) => s.method === 'delete')).toEqual([]);
  });

  it('states when a key was used, when it expires and when it was revoked', async () => {
    renderScreen([
      credential('k1', { lastUsedAt: '2026-09-20T10:30:00Z', expiresAt: '2099-01-01T00:00:00Z' }),
      credential('k2', { name: 'Retired feed', revokedAt: '2026-09-10T08:00:00Z' }),
      credential('k3', { name: 'Old connector', expiresAt: '2026-09-01T00:00:00Z' }),
    ]);

    const used = await row('k1');
    expect(used).toHaveTextContent(/Last used /);
    expect(used).toHaveTextContent(/Expires /);
    expect(used).not.toHaveTextContent('Never used');
    expect(within(used).getByRole('button', { name: 'Revoke' })).toBeInTheDocument();

    const revoked = await row('k2');
    expect(revoked).toHaveTextContent(/Revoked /);
    expect(revoked).toHaveTextContent('Never used');
    expect(within(revoked).queryByRole('button', { name: 'Revoke' })).toBeNull();

    expect(await row('k3')).toHaveTextContent(/Expired /);
  });

  it('says so when there is no key yet', async () => {
    renderScreen([]);

    expect(await screen.findByText('No API keys')).toBeInTheDocument();
    expect(screen.getByText("Create a key when an integration needs one. Our agents' keys and our members' tokens show here too.")).toBeInTheDocument();
    expect(document.querySelector('[data-keys-list]')).toBeNull();
  });

  it('shows an error when the list fails and loads it again on retry', async () => {
    let lists = 0;
    renderScreen([credential('k1', {})], (s) => {
      if (s.method !== 'get' || s.path !== KEYS) return undefined;
      lists += 1;
      return lists === 1 ? { status: 500, data: { code: 'server_error', detail: 'Down.' } } : undefined;
    });

    expect(await screen.findByText('Could not load API keys')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await row('k1')).toHaveTextContent('GRC export sync');
    expect(screen.queryByText('Could not load API keys')).toBeNull();
    expect(lists).toBe(2);
  });

  describe('creating a key', () => {
    const plainKey = 'cw_a1b2c3d4_secretpart';
    const createdKey = { ...credential('k9', { name: 'Ledger sync', scopes: ['tenant:read', 'search:read'] }), plainKey };
    let writeText: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    });

    afterEach(() => {
      Reflect.deleteProperty(navigator, 'clipboard');
    });

    const openForm = async (): Promise<HTMLElement> => {
      fireEvent.click((await screen.findAllByRole('button', { name: 'Create a key' }))[0] as HTMLElement);
      return document.querySelector('[data-key-form]') as HTMLElement;
    };
    const posts = (sent: Sent[]) => sent.filter((s) => s.method === 'post' && s.path === KEYS);
    const scope = (form: HTMLElement, label: string) => within(form).getByLabelText(new RegExp(`^${label}`));

    it('describes each scope it offers', async () => {
      renderScreen();
      const form = await openForm();

      for (const hint of ['Read the tenant profile', 'Read instruments and obligations', 'Read upcoming dates', 'Run searches', 'Submit proposals to the library queue']) {
        expect(within(form).getByText(hint)).toBeInTheDocument();
      }
      expect(within(form).getByText('Creating a key asks for your passkey.')).toBeInTheDocument();
    });

    it('asks for a name, then a scope, before sending anything', async () => {
      const sent = renderScreen();
      const form = await openForm();

      fireEvent.click(within(form).getByRole('button', { name: 'Create key' }));
      expect(await within(form).findByText('Enter a name.')).toBeInTheDocument();

      fireEvent.change(document.getElementById('key-name') as HTMLElement, { target: { value: '   ' } });
      fireEvent.click(within(form).getByRole('button', { name: 'Create key' }));
      expect(within(form).getByText('Enter a name.')).toBeInTheDocument();

      fireEvent.change(document.getElementById('key-name') as HTMLElement, { target: { value: 'Ledger sync' } });
      fireEvent.click(scope(form, 'tenant read'));
      fireEvent.click(scope(form, 'tenant read'));
      expect(scope(form, 'tenant read')).not.toBeChecked();
      fireEvent.click(within(form).getByRole('button', { name: 'Create key' }));
      expect(await within(form).findByText('Pick at least one scope.')).toBeInTheDocument();
      expect(within(form).queryByText('Enter a name.')).toBeNull();

      expect(posts(sent)).toEqual([]);
    });

    it('creates a key with an expiry, shows its plain value once and copies it', async () => {
      const sent = renderScreen([], (s) => (s.method === 'post' && s.path === KEYS ? { status: 201, data: createdKey } : undefined));
      const form = await openForm();

      fireEvent.change(document.getElementById('key-name') as HTMLElement, { target: { value: '  Ledger sync  ' } });
      fireEvent.change(document.getElementById('key-expires') as HTMLElement, { target: { value: '2027-03-31' } });
      fireEvent.click(scope(form, 'tenant read'));
      fireEvent.click(scope(form, 'search read'));
      fireEvent.click(within(form).getByRole('button', { name: 'Create key' }));

      const panel = await waitFor(() => {
        const element = document.querySelector<HTMLElement>('[data-new-key]');
        expect(element).not.toBeNull();
        return element as HTMLElement;
      });
      expect(posts(sent).map((s) => s.body)).toEqual([{ name: 'Ledger sync', scopes: ['tenant:read', 'search:read'], expiresAt: '2027-03-31T23:59:59Z' }]);
      expect(document.querySelector('[data-key-form]')).toBeNull();
      expect(within(panel).getByText('Copy your new key now')).toBeInTheDocument();
      expect(panel.querySelector('[data-plain-key]')).toHaveTextContent(plainKey);
      expect(within(panel).getByText('It is not shown again. Store it where your integration keeps secrets.')).toBeInTheDocument();
      expect(within(panel).queryByText('Copied.')).toBeNull();

      fireEvent.click(within(panel).getByRole('button', { name: 'Copy key' }));
      expect(await within(panel).findByText('Copied.')).toBeInTheDocument();
      expect(writeText).toHaveBeenCalledWith(plainKey);

      fireEvent.click(within(panel).getByRole('button', { name: 'Done' }));
      expect(document.querySelector('[data-new-key]')).toBeNull();
    });

    it('sends no expiry when none is picked and says nothing is copied when the clipboard refuses', async () => {
      writeText.mockRejectedValue(new Error('denied'));
      const sent = renderScreen([], (s) => (s.method === 'post' && s.path === KEYS ? { status: 201, data: createdKey } : undefined));
      const form = await openForm();

      fireEvent.change(document.getElementById('key-name') as HTMLElement, { target: { value: 'Ledger sync' } });
      fireEvent.click(scope(form, 'proposals write'));
      fireEvent.click(within(form).getByRole('button', { name: 'Create key' }));

      await waitFor(() => expect(document.querySelector('[data-new-key]')).not.toBeNull());
      expect(posts(sent).map((s) => s.body)).toEqual([{ name: 'Ledger sync', scopes: ['proposals:write'] }]);

      const panel = document.querySelector('[data-new-key]') as HTMLElement;
      fireEvent.click(within(panel).getByRole('button', { name: 'Copy key' }));
      await waitFor(() => expect(writeText).toHaveBeenCalledWith(plainKey));
      expect(within(panel).queryByText('Copied.')).toBeNull();
    });

    it('keeps the form open and says nothing changed when the passkey is not given', async () => {
      renderScreen([], (s) => (s.method === 'post' && s.path === KEYS ? { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } } : undefined));
      const form = await openForm();

      fireEvent.change(document.getElementById('key-name') as HTMLElement, { target: { value: 'Ledger sync' } });
      fireEvent.click(scope(form, 'library read'));
      fireEvent.click(within(form).getByRole('button', { name: 'Create key' }));

      expect(await within(form).findByText('The action was not confirmed, so nothing changed.')).toBeInTheDocument();
      expect(document.querySelector('[data-key-form]')).not.toBeNull();
      expect(document.querySelector('[data-new-key]')).toBeNull();
    });

    it('closes the form on cancel without sending anything', async () => {
      const sent = renderScreen();
      const form = await openForm();

      fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }));

      expect(document.querySelector('[data-key-form]')).toBeNull();
      expect(posts(sent)).toEqual([]);
    });
  });
});
