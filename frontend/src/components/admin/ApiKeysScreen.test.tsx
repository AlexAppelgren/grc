import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { API_KEY_SCOPES, ApiKeysScreen } from '@/components/admin/ApiKeysScreen';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
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

function renderScreen(): void {
  installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === '/api/v1/me') return { status: 200, data: admin };
    if (sent.path === '/api/v1/tenant/api-keys') return { status: 200, data: { items: [], total: 0 } };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <ApiKeysScreen />
    </Query>,
  );
}

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
});
