import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { API_KEY_SCOPES, ApiKeysScreen } from '@/features/tenant-admin/api-keys/ApiKeysScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
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

function renderScreen(items: unknown[] = []): Sent[] {
  const sent = installAdapter((sent) => {
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
});
