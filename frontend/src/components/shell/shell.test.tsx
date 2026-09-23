import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '@/components/shell/AppShell';
import { groupDestinations, AppSidebar } from '@/components/shell/AppSidebar';
import { secondLine } from '@/components/shell/AccountMenu';
import { NavIcon } from '@/components/shell/NavIcon';
import { COMPACT_QUERY, SIDEBAR_STORAGE_KEY, SidebarProvider } from '@/components/ui/sidebar';
import type { Me } from '@/features/identity/types';
import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { childDestinations, ACCOUNT_PARENT, dockDestinations, visibleDestinations, type Surface } from '@/shared/navigation/registry';
import { PermissionsProvider } from '@/shared/navigation/require-permission';

// The shell: the rail from 1024 px, the tab bar and the More sheet below it
// (design/system/navigation.md). The registry's destinations grouped as the
// registry groups them, the current row and tab from the pathname, the person
// as one row with a menu in the rail and as a flat group in the sheet. The
// lists are read from the registry, never hard-coded, because destinations
// are added there.
//
// jsdom applies no CSS, so the rail and the bar both render at every width:
// every query is scoped to [data-slot="sidebar"] or [data-slot="tab-bar"].

const nav = vi.hoisted(() => ({ pathname: '/', replace: vi.fn() }));
const session = vi.hoisted(() => ({ me: null as Me | null, mutate: vi.fn(), isPending: false }));
const language = vi.hoisted(() => ({
  rows: undefined as { key: string; kind: null; label: string }[] | undefined,
  mutate: vi.fn(),
  isPending: false,
  isError: false,
}));

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
  useSetLanguage: () => ({ mutate: language.mutate, isPending: language.isPending, isError: language.isError }),
}));

vi.mock('@/features/tenant-admin/hooks', () => ({
  useLanguages: () => ({ data: language.rows }),
}));

const t = createT('en');
const PERMISSIONS = ['watch.read', 'library.read', 'members.manage'];
/** What every system role holds, plus an admin grant: four tabs, and Roadmap and Admin in More. */
const EVERYONE_AND_ADMIN = ['watch.read', 'library.read', 'roadmap.read', 'search.use', 'members.manage'];

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
    counts: { triage: 0, proposals: 0, assignedToMe: 0 },
    lastVisitAt: null,
    ...overrides,
  };
}

type Listener = () => void;
let compact = false;
const mediaListeners = new Set<Listener>();
let resize: ((entries: { borderBoxSize: { blockSize: number; inlineSize: number }[] }[]) => void) | null = null;

beforeEach(() => {
  compact = false;
  mediaListeners.clear();
  resize = null;
  nav.pathname = '/';
  nav.replace.mockReset();
  session.me = me();
  session.mutate.mockReset();
  session.isPending = false;
  // The languages the platform serves, as rows: each in its own name, Danish among them.
  language.rows = [
    { key: 'da', kind: null, label: 'Dansk' },
    { key: 'en', kind: null, label: 'English' },
    { key: 'sv', kind: null, label: 'Svenska' },
  ];
  language.mutate.mockReset();
  language.isPending = false;
  language.isError = false;
  window.localStorage.clear();
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() {
      return query === COMPACT_QUERY && compact;
    },
    media: query,
    addEventListener: (_: string, l: Listener) => mediaListeners.add(l),
    removeEventListener: (_: string, l: Listener) => mediaListeners.delete(l),
  }));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: typeof resize) {
        resize = callback;
      }
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    },
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.style.removeProperty('--tabbar-height');
});

function shell(permissions: string[], surface: Surface = 'tenant'): ReactNode {
  return (
    <PermissionsProvider permissions={permissions}>
      <AppShell surface={surface}>
        <h1>{'Page'}</h1>
      </AppShell>
    </PermissionsProvider>
  );
}

function renderShell(props: { permissions?: string[]; surface?: Surface } = {}) {
  return render(shell(props.permissions ?? PERMISSIONS, props.surface));
}

const flipCompact = (value: boolean) => {
  compact = value;
  act(() => mediaListeners.forEach((l) => l()));
};

const rail = () => document.querySelector('[data-slot="sidebar"]') as HTMLElement;
const mainNav = () => within(rail()).getByRole('navigation', { name: 'Main' });
const tabBar = () => document.querySelector('[data-slot="tab-bar"]') as HTMLElement;
const moreButton = () => within(tabBar()).getByRole('button', { name: 'More' });
const minimise = () => document.querySelector('[data-sidebar-minimise]') as HTMLElement;
const sheet = () => screen.getByRole('dialog', { name: 'More' });

/** Opens More and returns the button, read before Radix hides the page from assistive technology. */
function openMore(): HTMLElement {
  const more = moreButton();
  fireEvent.click(more);
  return more;
}

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
      expect(link.querySelector('svg[aria-hidden="true"]')).toHaveClass('size-4');
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

  it('has a skip link and puts the page in the inset, after the rail and the bar', () => {
    renderShell();
    const skip = screen.getByRole('link', { name: 'Skip to content' });
    expect(skip).toHaveAttribute('href', '#main');
    expect(skip.className).toContain('focus:top-[max(8px,env(safe-area-inset-top))]');
    expect(skip.className).toContain('focus:left-[max(8px,env(safe-area-inset-left))]');
    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('id', 'main');
    expect(within(main).getByRole('heading', { name: 'Page' })).toBeInTheDocument();
    // Skip link, rail, bar, main: navigation comes before content at every width.
    const order = [skip, rail(), tabBar(), main];
    for (let i = 1; i < order.length; i += 1) {
      expect((order[i - 1] as HTMLElement).compareDocumentPosition(order[i] as HTMLElement) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it('keeps the rail footer clear of the home indicator', () => {
    renderShell();
    expect(rail().querySelector('[data-who-panel]')?.parentElement?.className).toContain('pb-[max(1rem,env(safe-area-inset-bottom))]');
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

  // One test opens the menu, the rotation case included: under jsdom a Radix
  // menu opened once is hard to open again (see the focus note below), and
  // the browser has no such carry-over (shell.journey, navigation.journey).
  it('opens a menu to the right with the account destinations, a pending state and sign out, and closes it when the width drops below 1024 px', async () => {
    const view = renderShell();
    const who = document.querySelector('[data-who-panel]') as HTMLElement;
    const trigger = within(who).getByRole('button', { name: 'Sara Lindqvist, account menu' });
    // Radix opens a menu on a primary-button pointer press.
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
    const menu = within(who).getByRole('menu');
    expect(menu).toHaveAttribute('data-side', 'right');
    for (const d of childDestinations(ACCOUNT_PARENT, PERMISSIONS)) {
      expect(within(menu).getByRole('menuitem', { name: t(d.labelKey) })).toHaveAttribute('href', d.href);
    }
    expect(within(menu).getByText('Signed in as')).toBeInTheDocument();

    session.isPending = true;
    view.rerender(shell(PERMISSIONS));
    expect(within(menu).getByRole('menuitem', { name: t('shell.signingOut') })).toHaveAttribute('aria-disabled', 'true');
    session.isPending = false;
    view.rerender(shell(PERMISSIONS));

    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Sign out' }));
    expect(session.mutate).toHaveBeenCalledOnce();
    const options = session.mutate.mock.calls[0]?.[1] as { onSettled: () => void };
    options.onSettled();
    expect(nav.replace).toHaveBeenCalledWith('/sign-in');

    // Rotated to portrait with the menu open: the rail is hidden under it, so
    // the menu closes and focus goes to the page, never to the hidden trigger.
    // A real press focuses the trigger first. Without it, jsdom fires a window
    // blur as focus leaves body for the menu, and Radix closes on window blur.
    act(() => trigger.focus());
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
    expect(within(who).getByRole('menu')).toBeInTheDocument();
    flipCompact(true);
    expect(within(who).queryByRole('menu')).toBeNull();
    await waitFor(() => expect(screen.getByRole('main')).toHaveFocus());
  });

  it('switches the interface language from the menu, offering each language the interface is written in by its own name', () => {
    const view = renderShell();
    const who = document.querySelector('[data-who-panel]') as HTMLElement;
    const trigger = within(who).getByRole('button', { name: 'Sara Lindqvist, account menu' });
    act(() => trigger.focus());
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
    const group = within(who).getByRole('group', { name: 'Language' });
    const english = within(group).getByRole('menuitemradio', { name: 'English' });
    const swedish = within(group).getByRole('menuitemradio', { name: 'Svenska' });
    expect(english).toHaveAttribute('aria-checked', 'true');
    expect(swedish).toHaveAttribute('aria-checked', 'false');
    // Read out in its own language, whatever the page is in.
    expect(swedish).toHaveAttribute('lang', 'sv');
    // A language row the interface has no catalog for is a content language only.
    expect(within(group).queryByRole('menuitemradio', { name: 'Dansk' })).toBeNull();

    // The language already in use saves nothing; another is saved on the person,
    // and the menu stays open so the switch is seen to land.
    fireEvent.click(english);
    expect(language.mutate).not.toHaveBeenCalled();
    fireEvent.click(swedish);
    expect(language.mutate).toHaveBeenCalledExactlyOnceWith('sv');
    expect(within(who).getByRole('menu')).toBeInTheDocument();

    language.isPending = true;
    view.rerender(shell(PERMISSIONS));
    expect(within(who).getByRole('menuitemradio', { name: 'Svenska' })).toHaveAttribute('aria-disabled', 'true');
    language.isPending = false;
    language.isError = true;
    view.rerender(shell(PERMISSIONS));
    // Read out from inside the menu, which owns only items and groups, so a live region and never an alert.
    const failed = within(who).getByText('The language could not be changed. Try again.');
    expect(failed).toHaveAttribute('aria-live', 'polite');
    expect(within(who).getByRole('group', { name: 'Language' })).toHaveAttribute('aria-describedby', failed.id);
    expect(within(who).queryByRole('alert')).toBeNull();
  });

  it('offers no language choice before the languages are known', () => {
    language.rows = undefined;
    renderShell();
    const who = document.querySelector('[data-who-panel]') as HTMLElement;
    const trigger = within(who).getByRole('button', { name: 'Sara Lindqvist, account menu' });
    act(() => trigger.focus());
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
    expect(within(who).getByRole('menu')).toBeInTheDocument();
    expect(within(who).queryByRole('group', { name: 'Language' })).toBeNull();
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
    fireEvent.click(moreButton());
    expect(within(sheet()).queryByRole('group', { name: 'Account' })).toBeNull();
  });

  it('builds the second line from what is there', () => {
    expect(secondLine('Example Bank AB', 'Admin, Approver', t)).toBe('Example Bank AB · Admin, Approver');
    expect(secondLine('Example Bank AB', '', t)).toBe('Example Bank AB');
    expect(secondLine(null, 'Admin', t)).toBe('Admin');
    expect(secondLine(null, '', t)).toBe('');
  });
});

describe('at compact width: the tab bar', () => {
  beforeEach(() => {
    compact = true;
  });

  it('is a Main navigation holding one list: the dock destinations in rank order, then More', () => {
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    const bar = tabBar();
    expect(bar.tagName).toBe('NAV');
    expect(bar).toHaveAccessibleName('Main');
    expect(bar).toHaveAttribute('lang', 'en');
    const lists = within(bar).getAllByRole('list');
    expect(lists).toHaveLength(1);
    const items = within(lists[0] as HTMLElement).getAllByRole('listitem');
    expect(items).toHaveLength(5);

    const tabs = dockDestinations('tenant', EVERYONE_AND_ADMIN);
    expect(within(bar).getAllByRole('link').map((l) => [l.textContent, l.getAttribute('href')])).toEqual(
      tabs.map((d) => [t(d.shortLabelKey ?? d.labelKey), d.href]),
    );
    expect(within(bar).getAllByRole('link').map((l) => l.textContent)).toEqual(['Today', 'Watch', 'Inventory', 'Search']);
    expect(within(items[4] as HTMLElement).getByRole('button', { name: 'More' })).toHaveAttribute('type', 'button');
    // One word on a tab; the rail keeps the full label.
    expect(within(bar).queryByText('Search and ask')).toBeNull();
    expect(within(mainNav()).getByRole('link', { name: 'Search and ask' })).toBeInTheDocument();
    // A 20px icon over every label.
    for (const cell of [...within(bar).getAllByRole('link'), moreButton()]) {
      expect(cell.querySelector('svg[aria-hidden="true"]')).toHaveClass('size-5');
    }
  });

  it('reads in the person’s language, with the nav in that language', () => {
    render(<LocaleProvider locale="sv">{shell(EVERYONE_AND_ADMIN)}</LocaleProvider>);
    const bar = tabBar();
    expect(bar).toHaveAttribute('lang', 'sv');
    expect([...bar.querySelectorAll('a, button')].map((cell) => cell.textContent)).toEqual(['Idag', 'Bevakning', 'Inventarie', 'Sök', 'Mer']);
  });

  it('marks the current tab alone, nested routes included', () => {
    nav.pathname = '/watch/change-12';
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    const watch = within(tabBar()).getByRole('link', { name: 'Watch' });
    expect(watch).toHaveAttribute('aria-current', 'page');
    expect(watch).toHaveAttribute('data-active', 'true');
    expect(watch).toHaveClass('rounded-control');
    expect(tabBar().querySelectorAll('[aria-current]')).toHaveLength(1);
    expect(within(tabBar()).getByRole('link', { name: 'Today' })).toHaveAttribute('data-active', 'false');
    expect(moreButton()).toHaveAttribute('data-active', 'false');
    expect(moreButton()).not.toHaveAttribute('aria-current');
  });

  it('shows More as current when the page lives in More, and the page’s own row inside the sheet', () => {
    nav.pathname = '/roadmap';
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    expect(moreButton()).toHaveAttribute('data-active', 'true');
    expect(moreButton()).toHaveAttribute('aria-current', 'true');
    expect(within(tabBar()).getAllByRole('link').filter((l) => l.hasAttribute('aria-current'))).toHaveLength(0);

    openMore();
    const roadmap = within(sheet()).getByRole('link', { name: 'Roadmap' });
    expect(roadmap).toHaveAttribute('aria-current', 'page');
    expect(roadmap).toHaveAttribute('data-active', 'true');
    expect(sheet().querySelectorAll('[aria-current="page"]')).toHaveLength(1);
  });

  it('marks Admin in the sheet on an admin section', () => {
    nav.pathname = '/admin/members';
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    const more = openMore();
    expect(more).toHaveAttribute('aria-current', 'true');
    expect(within(sheet()).getByRole('link', { name: 'Admin' })).toHaveAttribute('aria-current', 'page');
    // Admin's sections stay on the Admin page, as from the rail.
    expect(within(sheet()).queryByRole('link', { name: 'Members' })).toBeNull();
  });

  it('opens a dialog from More, which says it does', () => {
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    const more = moreButton();
    expect(more).toHaveAttribute('aria-haspopup', 'dialog');
    expect(more).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(more);
    expect(more).toHaveAttribute('aria-expanded', 'true');
    expect(sheet()).toHaveAttribute('aria-modal', 'true');
    expect(sheet()).not.toHaveAttribute('aria-describedby');
  });

  it('lists the other destinations in the rail’s groups, then the account laid flat', () => {
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    openMore();
    const dialog = sheet();
    expect(within(dialog).getByRole('heading', { name: 'More' })).toHaveClass('text-title');
    const close = within(dialog).getByRole('button', { name: 'Close' });
    expect(close).toHaveClass('size-11');

    const groups = [...dialog.querySelectorAll('[data-nav-group]')];
    expect(groups.map((g) => g.getAttribute('data-nav-group'))).toEqual(['secondary', 'admin']);
    expect(groups.flatMap((g) => within(g as HTMLElement).getAllByRole('link').map((l) => l.getAttribute('href')))).toEqual(['/roadmap', '/admin']);
    for (const link of groups.flatMap((g) => within(g as HTMLElement).getAllByRole('link'))) {
      expect(link.className).toContain('min-h-11');
      expect(link.querySelector('svg[aria-hidden="true"]')).toHaveClass('size-4');
    }

    const account = within(dialog).getByRole('group', { name: 'Account' });
    expect(within(account).getByText('Sara Lindqvist')).toHaveClass('font-medium');
    expect(within(account).getByText('Example Bank AB · Compliance officer')).toHaveClass('text-meta', 'text-muted');
    expect(within(account).getAllByRole('link').map((l) => [l.textContent, l.getAttribute('href')])).toEqual(
      childDestinations(ACCOUNT_PARENT, EVERYONE_AND_ADMIN).map((d) => [t(d.labelKey), d.href]),
    );
    expect(within(account).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    // The marker stays on the rail's row alone, so Playwright finds one.
    expect(dialog.querySelector('[data-who-panel]')).toBeNull();
  });

  it('never truncates the account lines, however long', () => {
    const long = 'Förenade Sparbanker och Hypoteksinstitut i Norden AB';
    const roles = 'Compliance officer, approver, auditor, obligation owner, contributor';
    session.me = me({ tenant: { id: 't1', name: long, slug: 'long', timezone: 'Europe/Stockholm' }, roles: [{ key: 'a', kind: null, label: roles }] });
    expect(secondLine(long, roles, t).length).toBeGreaterThanOrEqual(120);
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    openMore();
    expect(sheet().querySelectorAll('[class*="truncate"]')).toHaveLength(0);
  });

  it('signs out from the sheet, disabled while pending, then leaves for sign in', () => {
    const view = renderShell({ permissions: EVERYONE_AND_ADMIN });
    openMore();
    session.isPending = true;
    view.rerender(shell(EVERYONE_AND_ADMIN));
    expect(within(sheet()).getByRole('button', { name: 'Signing out…' })).toBeDisabled();
    session.isPending = false;
    view.rerender(shell(EVERYONE_AND_ADMIN));

    fireEvent.click(within(sheet()).getByRole('button', { name: 'Sign out' }));
    expect(session.mutate).toHaveBeenCalledOnce();
    const options = session.mutate.mock.calls[0]?.[1] as { onSettled: () => void };
    options.onSettled();
    expect(nav.replace).toHaveBeenCalledWith('/sign-in');
  });

  it('closes when a destination is chosen, even the current page', () => {
    nav.pathname = '/roadmap';
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    openMore();
    fireEvent.click(within(sheet()).getByRole('link', { name: 'Roadmap' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    openMore();
    fireEvent.click(within(sheet()).getByRole('link', { name: 'My passkeys' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('closes on Escape and gives focus back to More', async () => {
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    const more = openMore();
    fireEvent.keyDown(sheet(), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => expect(more).toHaveFocus());
  });

  it('closes from its Close button', () => {
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    openMore();
    fireEvent.click(within(sheet()).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('closes on any route change, such as the back gesture', () => {
    const view = renderShell({ permissions: EVERYONE_AND_ADMIN });
    openMore();
    nav.pathname = '/watch';
    view.rerender(shell(EVERYONE_AND_ADMIN));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('closes when the width crosses 1024 px, and focuses the page because More is hidden', async () => {
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    openMore();
    flipCompact(false);
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => expect(screen.getByRole('main')).toHaveFocus());
  });

  it('is shaped as a floating layer, never a pill', () => {
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    expect(tabBar()).toHaveClass('rounded-overlay', 'shadow-float', 'fixed', 'lg:hidden', 'print:hidden');
    expect(within(tabBar()).getByRole('link', { name: 'Today' })).toHaveClass('rounded-control');
    openMore();
    expect(sheet()).toHaveClass('rounded-t-overlay');
    for (const root of [tabBar(), sheet()]) {
      expect(root.querySelectorAll('[class*="rounded-full"]')).toHaveLength(0);
      expect(root.className).not.toContain('rounded-full');
    }
  });

  it('measures its own height for the page clearance, ignores a hidden bar, and cleans up', () => {
    const view = renderShell();
    const root = document.documentElement;
    act(() => resize?.([{ borderBoxSize: [{ blockSize: 72, inlineSize: 343 }] }]));
    expect(root.style.getPropertyValue('--tabbar-height')).toBe('72px');
    act(() => resize?.([{ borderBoxSize: [{ blockSize: 0, inlineSize: 0 }] }]));
    expect(root.style.getPropertyValue('--tabbar-height')).toBe('72px');
    view.unmount();
    expect(root.style.getPropertyValue('--tabbar-height')).toBe('');
  });

  it('switches the interface language from the sheet, as the rail does, and stays open to show it land', () => {
    const view = renderShell({ permissions: EVERYONE_AND_ADMIN });
    openMore();
    const account = within(sheet()).getByRole('group', { name: 'Account' });
    const group = within(account).getByRole('group', { name: 'Language' });
    const english = within(group).getByRole('radio', { name: 'English' });
    const swedish = within(group).getByRole('radio', { name: 'Svenska' });
    expect(english).toBeChecked();
    expect(swedish).not.toBeChecked();
    expect(swedish.closest('label')).toHaveAttribute('lang', 'sv');
    expect(within(group).queryByRole('radio', { name: 'Dansk' })).toBeNull();
    // Between the account's pages and sign out.
    expect(within(account).getByRole('link', { name: 'My passkeys' }).compareDocumentPosition(group)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(group.compareDocumentPosition(within(account).getByRole('button', { name: 'Sign out' }))).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    fireEvent.click(english);
    expect(language.mutate).not.toHaveBeenCalled();
    fireEvent.click(swedish);
    expect(language.mutate).toHaveBeenCalledExactlyOnceWith('sv');
    expect(sheet()).toBeInTheDocument();

    language.isPending = true;
    view.rerender(shell(EVERYONE_AND_ADMIN));
    expect(within(sheet()).getByRole('radio', { name: 'Svenska' })).toBeDisabled();
    language.isPending = false;
    language.isError = true;
    view.rerender(shell(EVERYONE_AND_ADMIN));
    expect(within(sheet()).getByRole('alert')).toHaveTextContent('The language could not be changed. Try again.');
  });

  it('offers no language choice in the sheet before the languages are known', () => {
    language.rows = undefined;
    renderShell({ permissions: EVERYONE_AND_ADMIN });
    openMore();
    expect(within(sheet()).getByRole('group', { name: 'Account' })).toBeInTheDocument();
    expect(within(sheet()).queryByRole('group', { name: 'Language' })).toBeNull();
  });

  it('shows only what the permissions unlock: Today and More, and the account in the sheet', () => {
    renderShell({ permissions: [] });
    expect(within(tabBar()).getAllByRole('link').map((l) => l.textContent)).toEqual(['Today']);
    openMore();
    expect(sheet().querySelectorAll('[data-nav-group]')).toHaveLength(0);
    expect(within(sheet()).getByRole('group', { name: 'Account' })).toBeInTheDocument();
  });

  it('serves the console the same way: its ranked destinations, and the rest in More', () => {
    renderShell({ surface: 'console', permissions: ['proposals.review', 'library_vocab.manage', 'sources.manage'] });
    expect([...tabBar().querySelectorAll('a, button')].map((cell) => cell.textContent)).toEqual(['Queue', 'Vocabularies', 'Sources', 'More']);
    openMore();
    // Change facts takes no dock rank, so the console's unranked destination
    // sits in the sheet above the account, as a tenant's Roadmap does.
    expect(within(sheet()).getByRole('link', { name: 'Change facts' })).toHaveAttribute('href', '/console/change-facts');
    expect(within(sheet()).getByRole('group', { name: 'Account' })).toBeInTheDocument();
  });

  it('keeps the wordmark line on top, a link to Today with no menu button', () => {
    renderShell();
    const header = document.querySelector('[data-mobile-header]') as HTMLElement;
    expect(header).toHaveClass('lg:hidden');
    expect(within(header).getByRole('link')).toHaveAttribute('href', '/');
    expect(within(header).getByRole('img', { name: 'bleqq, pronounced blek' })).toBeInTheDocument();
    expect(within(header).queryByRole('button')).toBeNull();
    expect(document.querySelector('[data-sidebar="trigger"]')).toBeNull();
  });

  it('pads the page clear of the safe areas at both steps, and of the bar at the bottom', () => {
    renderShell();
    const page = screen.getByRole('main').firstElementChild as HTMLElement;
    for (const utility of [
      'pl-[max(1rem,env(safe-area-inset-left))]',
      'pr-[max(1rem,env(safe-area-inset-right))]',
      'md:pl-[max(2rem,env(safe-area-inset-left))]',
      'md:pr-[max(2rem,env(safe-area-inset-right))]',
      'pt-[max(12px,env(safe-area-inset-top))]',
      'md:pt-6',
      'max-lg:pb-[calc(var(--tabbar-top)+16px)]',
      'lg:pb-16',
    ]) {
      expect(page).toHaveClass(utility);
    }
    expect([...page.classList].filter((c) => /^(md:)?px-/.test(c))).toEqual([]);
  });
});

describe('the console surface and the helpers', () => {
  it('renders the console destinations the same way', () => {
    const perms = ['library_vocab.manage'];
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

  it('draws their own icons for the console destinations that join the rail next', () => {
    const paths = (id: string) => {
      const { container, unmount } = render(<NavIcon id={id} />);
      const d = [...container.querySelectorAll('path')].map((p) => p.getAttribute('d'));
      unmount();
      return d;
    };
    const dot = paths('no-such-destination');
    for (const id of ['console-tenants', 'console-problem-reports']) {
      expect(paths(id)).not.toEqual(dot);
    }
  });

  it('groups destinations in the rail order and drops empty groups', () => {
    const all = visibleDestinations('tenant', ['watch.read', 'roadmap.read']);
    expect(groupDestinations(all).map((g) => g[0]?.group)).toEqual(['primary', 'secondary']);
  });
});
