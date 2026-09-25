import { act, fireEvent, render, screen, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '@/components/shell/AppShell';
import type { Me } from '@/features/identity/types';
import { createT } from '@/shared/i18n';
import { PermissionsProvider } from '@/shared/navigation/require-permission';

import { withUnread } from './NotificationBell';

// The bell (design/screens/tenant-notifications.html, blocks 1 and 2): a dot
// on the account row's icon from 1024 px and on More below it while anything
// is unread, Notifications first in the account menu and in the More sheet's
// account group with the count at the end of the row, and the count in the
// accessible names. Driven by GET /me's counts.unreadNotifications alone.

const session = vi.hoisted(() => ({ me: null as Me | null }));

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: ComponentProps<'a'> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('@/features/identity/hooks', () => ({
  useSession: () => ({ status: 'signed-in', me: session.me, error: null, refetch: () => {} }),
  useSignOut: () => ({ mutate: vi.fn(), isPending: false }),
  useSetLanguage: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}));

vi.mock('@/features/tenant-admin/hooks', () => ({
  useLanguages: () => ({ data: [] }),
}));

const t = createT('en');

function me(unreadNotifications: number | null): Me {
  return {
    user: { id: 'u1', email: 'sara@example.test', name: 'Sara Lindqvist', locale: 'en' },
    tenant: { id: 't1', name: 'Example Bank AB', slug: 'example', timezone: 'Europe/Stockholm' },
    roles: [{ key: 'officer', kind: null, label: 'Compliance officer' }],
    permissions: ['watch.read', 'library.read'],
    platformRoles: [],
    enrolmentPending: false,
    passkeyCount: 1,
    stepUpValidUntil: null,
    counts: unreadNotifications === null ? null : { triage: 0, proposals: 0, assignedToMe: 0, unreadNotifications },
    lastVisitAt: null,
    notificationPrefs: null,
    headOf: [],
  };
}

beforeEach(() => {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    },
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderShell(unread: number | null, platform = false) {
  session.me = platform ? { ...me(unread), tenant: null, permissions: ['proposals.review'] } : me(unread);
  return render(
    <PermissionsProvider permissions={session.me.permissions}>
      <AppShell surface={platform ? 'console' : 'tenant'}>
        <h1>{'Page'}</h1>
      </AppShell>
    </PermissionsProvider>,
  );
}

const rail = () => document.querySelector('[data-slot="sidebar"]') as HTMLElement;
const tabBar = () => document.querySelector('[data-slot="tab-bar"]') as HTMLElement;
const accountRow = () => within(rail()).getByRole('button', { name: /, account menu$/ });

// Radix opens a menu on a primary-button pointer press. Under jsdom a menu
// opened once is hard to open again, or after a sheet was open
// (shell.test.tsx), so one test opens it, and it runs first.
function openAccountMenu(): HTMLElement {
  const trigger = accountRow();
  act(() => {
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
  });
  return screen.getByRole('menu');
}

describe('withUnread', () => {
  it('adds the count to a label, singular and plural, and leaves the label alone at 0', () => {
    expect(withUnread('More', 1, t)).toBe('More, 1 unread notification');
    expect(withUnread('More', 3, t)).toBe('More, 3 unread notifications');
    expect(withUnread('More', 0, t)).toBe('More');
  });

  it('says the count in Swedish too', () => {
    expect(withUnread('Mer', 2, createT('sv'))).toBe('Mer, 2 olästa aviseringar');
  });
});

describe('the bell in the shell', () => {
  it('lists Notifications first in the account menu, with the count at the end of the row', () => {
    renderShell(3);
    const items = within(openAccountMenu()).getAllByRole('menuitem');
    expect(items[0]).toHaveAccessibleName('Notifications, 3 unread notifications');
    expect(items[0]).toHaveAttribute('href', '/notifications');
    expect(items[0]?.querySelector('[data-unread-count]')).toHaveTextContent('3');
  });

  it('puts the dot on the account row and on More, and says the count in both names', () => {
    renderShell(3);
    const row = accountRow();
    expect(row).toHaveAccessibleName('Sara Lindqvist, 3 unread notifications, account menu');
    expect(row.querySelector('[data-unread-dot]')).not.toBeNull();
    const more = within(tabBar()).getByRole('button', { name: 'More, 3 unread notifications' });
    expect(more.querySelector('[data-unread-dot]')).not.toBeNull();
  });

  it('shows no dot, no number and the plain names while nothing is unread', () => {
    renderShell(0);
    expect(accountRow()).toHaveAccessibleName('Sara Lindqvist, account menu');
    expect(within(tabBar()).getByRole('button', { name: 'More' })).toBeInTheDocument();
    expect(document.querySelector('[data-unread-dot]')).toBeNull();
    fireEvent.click(within(tabBar()).getByRole('button', { name: 'More' }));
    const account = within(screen.getByRole('dialog', { name: 'More' })).getByRole('group', { name: 'Account' });
    expect(within(account).getByRole('link', { name: 'Notifications' })).toHaveAttribute('href', '/notifications');
    expect(account.querySelector('[data-unread-count]')).toBeNull();
  });

  it('treats a session without counts as nothing unread', () => {
    renderShell(null);
    expect(accountRow()).toHaveAccessibleName('Sara Lindqvist, account menu');
    expect(document.querySelector('[data-unread-dot]')).toBeNull();
  });

  it('lists Notifications first in the More sheet account group, with the count', () => {
    renderShell(2);
    fireEvent.click(within(tabBar()).getByRole('button', { name: 'More, 2 unread notifications' }));
    const account = within(screen.getByRole('dialog', { name: 'More' })).getByRole('group', { name: 'Account' });
    const first = within(account).getAllByRole('link')[0];
    expect(first).toHaveAccessibleName('Notifications, 2 unread notifications');
    expect(first).toHaveAttribute('href', '/notifications');
    expect(first?.querySelector('[data-unread-count]')).toHaveTextContent('2');
  });

  it('offers platform staff, who belong to no bank, no Notifications row and no dot', () => {
    renderShell(null, true);
    fireEvent.click(within(tabBar()).getByRole('button', { name: 'More' }));
    const account = within(screen.getByRole('dialog', { name: 'More' })).getByRole('group', { name: 'Account' });
    expect(within(account).queryByRole('link', { name: /Notifications/ })).toBeNull();
    expect(within(account).getByRole('link', { name: 'My passkeys' })).toBeInTheDocument();
    expect(document.querySelector('[data-unread-dot]')).toBeNull();
  });
});
