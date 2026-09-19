import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '@/components/shell/AppShell';
import { groupDestinations, AppSidebar } from '@/components/shell/AppSidebar';
import { secondLine } from '@/components/shell/AccountMenu';
import { SIDEBAR_STORAGE_KEY, SidebarProvider } from '@/components/ui/sidebar';
import type { Me } from '@/features/identity/types';
import { createT } from '@/shared/i18n';
import { childDestinations, ACCOUNT_PARENT, visibleDestinations } from '@/shared/navigation/registry';
import { PermissionsProvider } from '@/shared/navigation/require-permission';

// The shell on the shadcn Sidebar: the registry's destinations grouped as
// the registry groups them, the active row from the pathname, the person as one row with a menu, collapse to icons with
// tooltips, and the off-canvas sheet on phones. The list is read from the
// registry, never hard-coded, because destinations are added there.

const nav = vi.hoisted(() => ({ pathname: '/', replace: vi.fn() }));
const session = vi.hoisted(() => ({ me: null as Me | null, mutate: vi.fn(), isPending: false }));

vi.mock('next/navigation', () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
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
  useSignOut: () => ({ mutate: session.mutate, isPending: session.isPending }),
}));

const t = createT('en');
const PERMISSIONS = ['watch.read', 'library.read', 'members.manage'];

function me(overrides: Partial<Me> = {}): Me {
  return {
    user: { id: 'u1', email: 'sara@example.test', name: 'Sara Lindqvist', locale: 'en' },
    tenant: { id: 't1', name: 'Example Bank AB', slug: 'example', timezone: 'Europe/Stockholm' },
    roles: [{ key: 'officer', kind: null, label: 'Compliance officer' }],
    permissions: PERMISSIONS,
    platformRoles: [],
    enrolmentPending: false,
    passkeyCount: 2,
    stepUpValidUntil: null,
    ...overrides,
  };
}

let mobile = false;

beforeEach(() => {
  mobile = false;
  nav.pathname = '/';
  nav.replace.mockReset();
  session.me = me();
  session.mutate.mockReset();
  session.isPending = false;
  window.localStorage.clear();
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() {
      return mobile;
    },
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
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

function renderShell(props: { permissions?: string[] } = {}) {
  return render(
    <PermissionsProvider permissions={props.permissions ?? PERMISSIONS}>
      <AppShell surface="tenant">
        <h1>{'Page'}</h1>
      </AppShell>
    </PermissionsProvider>,
  );
}

const mainNav = () => screen.getByRole('navigation', { name: 'Main' });
const minimise = () => document.querySelector('[data-sidebar-minimise]') as HTMLElement;

describe('the rail on desktop', () => {
  it('renders every destination the registry unlocks, and nothing it does not', () => {
    renderShell();
    const expected = visibleDestinations('tenant', PERMISSIONS);
    const links = within(mainNav()).getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual(groupDestinations(expected).flat().map((d) => d.href));
    expect(within(mainNav()).getByRole('link', { name: 'Watch' })).toBeInTheDocument();
    expect(within(mainNav()).queryByRole('link', { name: 'Roadmap' })).toBeNull();
  });

  it('keeps the registry groups, in order, separated by space and no headings', () => {
    renderShell();
    const groups = [...mainNav().querySelectorAll('[data-nav-group]')].map((g) => g.getAttribute('data-nav-group'));
    expect(groups).toEqual(['primary', 'admin']);
    expect(within(mainNav()).queryAllByRole('heading')).toHaveLength(0);
    expect(within(mainNav()).queryAllByRole('separator')).toHaveLength(0);
  });

  it('derives the active row from the pathname, nested routes included', () => {
    nav.pathname = '/watch/change-12';
    renderShell();
    const watch = within(mainNav()).getByRole('link', { name: 'Watch' });
    expect(watch).toHaveAttribute('aria-current', 'page');
    expect(watch).toHaveAttribute('data-active', 'true');
    const today = within(mainNav()).getByRole('link', { name: 'Today' });
    expect(today).not.toHaveAttribute('aria-current');
    expect(today).toHaveAttribute('data-active', 'false');
  });

  it('shows the phonetic wordmark, and a small icon on every row', () => {
    renderShell();
    expect(screen.getAllByRole('img', { name: 'bleqq, pronounced blek' }).length).toBeGreaterThan(0);
    for (const link of within(mainNav()).getAllByRole('link')) {
      expect(link.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    }
  });

  it('minimises to icons with tooltips, and the choice survives a remount', async () => {
    const first = renderShell();
    expect(minimise()).toHaveAccessibleName('Minimise menu');
    fireEvent.focus(within(mainNav()).getByRole('link', { name: 'Watch' }));
    expect(screen.queryByRole('tooltip')).toBeNull();

    fireEvent.click(minimise());
    expect(minimise()).toHaveAccessibleName('Expand menu');
    expect(minimise()).toHaveAttribute('aria-expanded', 'false');
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('false');
    fireEvent.focus(within(mainNav()).getByRole('link', { name: 'Watch' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Watch');
    first.unmount();

    renderShell();
    expect(minimise()).toHaveAccessibleName('Expand menu');
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true });
    expect(minimise()).toHaveAccessibleName('Minimise menu');
  });

  it('has a skip link and puts the page in the inset', () => {
    renderShell();
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
    expect(within(screen.getByRole('main')).getByRole('heading', { name: 'Page' })).toBeInTheDocument();
  });
});

describe('the signed-in person', () => {
  it('is one quiet row with name, organisation and role, still found by data-who-panel', () => {
    renderShell();
    const who = document.querySelector('[data-who-panel]') as HTMLElement;
    expect(who).toHaveTextContent('Sara Lindqvist');
    expect(who).toHaveTextContent('Example Bank AB · Compliance officer');
    expect(within(who).getByRole('button', { name: 'Sara Lindqvist, account menu' })).toBeInTheDocument();
  });

  // One test opens the menu: Radix keeps focus and dismiss bookkeeping at
  // module level, and under jsdom a menu opened in one test stops the next
  // from opening. The browser has no such carry-over (shell.journey).
  it('opens a menu with the account destinations, a pending state and sign out', () => {
    const view = renderShell();
    const who = document.querySelector('[data-who-panel]') as HTMLElement;
    // Radix opens a menu on a primary-button pointer press.
    fireEvent.pointerDown(within(who).getByRole('button', { name: 'Sara Lindqvist, account menu' }), { button: 0, ctrlKey: false, pointerType: 'mouse' });
    const menu = within(who).getByRole('menu');
    for (const d of childDestinations(ACCOUNT_PARENT, PERMISSIONS)) {
      expect(within(menu).getByRole('menuitem', { name: t(d.labelKey) })).toHaveAttribute('href', d.href);
    }
    expect(within(menu).getByText('Signed in as')).toBeInTheDocument();

    session.isPending = true;
    view.rerender(
      <PermissionsProvider permissions={PERMISSIONS}>
        <AppShell surface="tenant">
          <h1>{'Page'}</h1>
        </AppShell>
      </PermissionsProvider>,
    );
    expect(within(menu).getByRole('menuitem', { name: t('shell.signingOut') })).toHaveAttribute('aria-disabled', 'true');
    session.isPending = false;
    view.rerender(
      <PermissionsProvider permissions={PERMISSIONS}>
        <AppShell surface="tenant">
          <h1>{'Page'}</h1>
        </AppShell>
      </PermissionsProvider>,
    );

    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Sign out' }));
    expect(session.mutate).toHaveBeenCalledOnce();
    const options = session.mutate.mock.calls[0]?.[1] as { onSettled: () => void };
    options.onSettled();
    expect(nav.replace).toHaveBeenCalledWith('/sign-in');
  });

  it('drops the second line when there is neither organisation nor role', () => {
    session.me = me({ tenant: null, roles: [] });
    renderShell();
    const who = document.querySelector('[data-who-panel]') as HTMLElement;
    expect(who.querySelectorAll('.truncate')).toHaveLength(1);
  });

  it('renders no account row without a session', () => {
    session.me = null;
    renderShell({ permissions: [] });
    expect(document.querySelector('[data-who-panel]')).toBeNull();
  });

  it('builds the second line from what is there', () => {
    expect(secondLine('Example Bank AB', 'Admin, Approver', t)).toBe('Example Bank AB · Admin, Approver');
    expect(secondLine('Example Bank AB', '', t)).toBe('Example Bank AB');
    expect(secondLine(null, 'Admin', t)).toBe('Admin');
    expect(secondLine(null, '', t)).toBe('');
  });
});

describe('at phone width', () => {
  it('replaces the dock with a header trigger that opens every destination in a sheet', () => {
    mobile = true;
    renderShell({ permissions: [...PERMISSIONS, 'roadmap.read'] });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(minimise()).toBeNull();

    const header = document.querySelector('[data-mobile-header]') as HTMLElement;
    expect(within(header).getByRole('img', { name: 'bleqq, pronounced blek' })).toBeInTheDocument();
    fireEvent.click(within(header).getByRole('button', { name: 'Toggle the menu' }));

    const sheet = screen.getByRole('dialog', { name: 'Navigation' });
    // Roadmap has no dock rank, so the old dock never reached it on a phone.
    expect(within(sheet).getByRole('link', { name: 'Roadmap' })).toBeInTheDocument();
    for (const d of visibleDestinations('tenant', [...PERMISSIONS, 'roadmap.read'])) {
      expect(within(sheet).getByRole('link', { name: t(d.labelKey) })).toHaveAttribute('href', d.href);
    }
    expect(within(sheet).getByRole('button', { name: 'Sara Lindqvist, account menu' })).toBeInTheDocument();

    fireEvent.click(within(sheet).getByRole('link', { name: 'Watch' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('closes the sheet from the wordmark link too', () => {
    mobile = true;
    renderShell();
    fireEvent.click(screen.getByRole('button', { name: 'Toggle the menu' }));
    const sheet = screen.getByRole('dialog', { name: 'Navigation' });
    fireEvent.click(within(sheet).getAllByRole('link')[0] as HTMLElement);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('the console surface and the helpers', () => {
  it('renders the console destinations the same way', () => {
    const perms = ['proposals.review'];
    render(
      <PermissionsProvider permissions={perms}>
        <SidebarProvider>
          <AppSidebar surface="console" />
        </SidebarProvider>
      </PermissionsProvider>,
    );
    const links = within(mainNav()).getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual(visibleDestinations('console', perms).map((d) => d.href));
  });

  it('gives a destination without its own icon a quiet dot, so the rail never shows a gap', () => {
    renderShell({ permissions: [...PERMISSIONS, 'roadmap.read', 'search.use'] });
    for (const link of within(mainNav()).getAllByRole('link')) {
      expect(link.querySelectorAll('svg path').length).toBeGreaterThan(0);
    }
  });

  it('groups destinations in the rail order and drops empty groups', () => {
    const all = visibleDestinations('tenant', ['watch.read', 'roadmap.read']);
    expect(groupDestinations(all).map((g) => g[0]?.group)).toEqual(['primary', 'secondary']);
  });
});
