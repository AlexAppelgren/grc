import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useSignOutToSignIn } from '@/components/shell/AccountMenu';
import { SessionGate } from '@/components/shell/SessionGate';
import type { Me } from '@/features/identity/types';
import { createT } from '@/shared/i18n';
import { queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { api, pathOf, tokenStore } from '@/shared/utils/api-client';

// The gate against the real query client and the real sign-out: while the
// sign-out is pending the screens are down, so none of them asks the server
// for anything once the session has ended, and the redirect to /sign-in still
// runs although the menu that started it went down with them.

const nav = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
}));

const t = createT('en');

const me: Me = {
  user: { id: 'u1', email: 'sara@example.test', name: 'Sara Lindqvist', locale: 'en' },
  tenant: { id: 't1', name: 'Example Bank AB', slug: 'example', timezone: 'Europe/Stockholm' },
  roles: [],
  permissions: ['watch.read'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
  counts: { triage: 0, proposals: 0, assignedToMe: 0 },
  lastVisitAt: null,
};

/** A screen with the account's sign out on it, as the rail's menu and the More sheet have. */
function Screen() {
  const { signOut } = useSignOutToSignIn();
  return (
    <button type="button" onClick={signOut}>
      {t('shell.signOut')}
    </button>
  );
}

/** The server holds the sign-out until the test answers it; anything else is refused. */
function holdSignOut(): { paths: string[]; answer: () => void } {
  const paths: string[] = [];
  let answer = () => {};
  const held = new Promise<void>((resolve) => {
    answer = resolve;
  });
  const adapter: AxiosAdapter = async (config) => {
    paths.push(pathOf(config));
    await held;
    const response: AxiosResponse = { data: null, status: 204, statusText: '204', headers: {}, config: config as InternalAxiosRequestConfig };
    return response;
  };
  api.defaults.adapter = adapter;
  return { paths, answer };
}

beforeEach(() => {
  resetApiForTests();
  nav.replace.mockReset();
  tokenStore.set('tok');
});

afterEach(() => {
  tokenStore.clear();
});

describe('SessionGate', () => {
  it('takes the screens down while a sign-out is pending, then leaves for /sign-in', async () => {
    const server = holdSignOut();
    const { queryClient } = queryWrapper();
    queryClient.setQueryData(['me'], me);
    render(
      <QueryClientProvider client={queryClient}>
        <SessionGate>
          <Screen />
        </SessionGate>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: t('shell.signOut') }));

    // Pending: the screen, and the menu with it, is gone; the gate shows its loading state.
    await waitFor(() => expect(screen.queryByRole('button', { name: t('shell.signOut') })).not.toBeInTheDocument());
    expect(screen.getByRole('status')).toHaveTextContent(t('shell.loading'));
    expect(nav.replace).not.toHaveBeenCalled();

    // Settled: the redirect runs although the component that asked for it has unmounted.
    server.answer();
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/sign-in'));
    expect(server.paths).toEqual(['/api/v1/auth/sign-out']);
    expect(tokenStore.get()).toBeNull();
    expect(screen.queryByRole('button', { name: t('shell.signOut') })).not.toBeInTheDocument();
  });
});
