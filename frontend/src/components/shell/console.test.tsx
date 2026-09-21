import { render, screen, waitFor, within } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ConsoleLayout from '@/app/(console)/layout';
import ConsolePage from '@/app/(console)/console/page';
import TenantLayout from '@/app/(tenant)/layout';
import TodayPage from '@/app/(tenant)/page';
import { VocabulariesScreen } from '@/components/admin/VocabulariesScreen';
import { VocabularyScreen } from '@/components/admin/VocabularyScreen';
import { SignInScreen } from '@/components/auth/SignInScreen';
import type { Me } from '@/features/identity/types';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// The platform console (ADM-02, design/screens/console-shell.html): its own
// route group behind the session gate, the same shell with surface
// "console", and a landing that sends each person to the first console
// destination their permissions unlock. A person without a tenant is
// platform staff and works there; a tenant member who opens it is refused.
// The permission list decides, never a role name, and the server's 403
// stays the enforcer.
//
// The session and the screens run against the real query client and the
// one axios instance, with the network scripted per test, so a test sees
// every request the console makes.

const nav = vi.hoisted(() => ({ pathname: '/console', replace: vi.fn() }));

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

const ME_PATH = '/api/v1/me';
const VOCAB_PATH = '/api/v1/vocab';
/** What the library editor holds (PRD section 6). */
const EDITOR_PERMISSIONS = ['proposals.review', 'library_vocab.manage', 'sources.manage', 'eval.manage'];
/** What every tenant system role holds, plus an admin's grants. */
const MEMBER_PERMISSIONS = ['library.read', 'watch.read', 'roadmap.read', 'search.use', 'members.manage', 'vocab.manage', 'proposals.create'];

const editor: Me = {
  user: { id: 'u10', email: 'editor@bleqq.test', name: 'Ida Holm', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: EDITOR_PERMISSIONS,
  platformRoles: [{ key: 'library_editor', kind: null, label: 'Library editor' }],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

const member: Me = {
  ...editor,
  user: { id: 'u2', email: 'compliance_officer@example-bank.test', name: 'Sara Lindqvist', locale: 'en' },
  tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm' },
  roles: [{ key: 'compliance_officer', kind: null, label: 'Compliance officer' }],
  permissions: MEMBER_PERMISSIONS,
  platformRoles: [],
};

const LISTS = [
  { list: 'tenant_tag', tier: 3, kind: null, kinds: [], count: 2, retiredCount: 0, proposable: false },
  { list: 'flag', tier: 2, kind: null, kinds: [], count: 6, retiredCount: 0, proposable: true },
  { list: 'library_tag', tier: 2, kind: null, kinds: [], count: 42, retiredCount: 1, proposable: true },
];

const FLAG_ROWS = [
  { key: 'ai', kind: null, label: 'AI', labels: { en: 'AI' }, usageNote: '', sortOrder: 1, active: true, isSystem: false, isDefault: false, usageCount: 1, extra: {} },
];

/** The server: the signed-in person, the vocabulary reads, and a 403 for anything the test did not expect. */
function server(me: Me | null, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return me === null ? { status: 401 } : { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: me };
    return extra(sent) ?? { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function vocabulary(sent: Sent): Answer | undefined {
  if (sent.path === VOCAB_PATH) return { status: 200, data: { items: LISTS, total: LISTS.length } };
  if (sent.path === `${VOCAB_PATH}/flag`) return { status: 200, data: { items: FLAG_ROWS, total: 1 } };
  return undefined;
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

type Listener = () => void;

beforeEach(() => {
  resetApiForTests();
  nav.pathname = '/console';
  nav.replace.mockReset();
  window.localStorage.clear();
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    addEventListener: (_: string, _l: Listener) => undefined,
    removeEventListener: (_: string, _l: Listener) => undefined,
  }));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe(): void {}
      disconnect(): void {}
    },
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const rail = () => document.querySelector('[data-slot="sidebar"]') as HTMLElement;
const railNav = () => within(rail()).getByRole('navigation', { name: 'Main' });

describe('the console landing', () => {
  it('sends a person to the first console destination their permissions unlock', async () => {
    server(editor);
    renderIn(
      <ConsoleLayout>
        <ConsolePage />
      </ConsoleLayout>,
    );
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/console/queue'));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows a tenant member the Restricted screen, naming what the console needs, and sends them nowhere', async () => {
    server(member);
    renderIn(
      <ConsoleLayout>
        <ConsolePage />
      </ConsoleLayout>,
    );
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByRole('heading', { name: 'This page is not available to you' })).toBeInTheDocument();
    expect(alert).toHaveTextContent('Needs proposals review');
    expect(nav.replace).not.toHaveBeenCalled();
    // The console rail holds nothing a tenant member may open.
    expect(within(railNav()).queryAllByRole('link')).toHaveLength(0);
  });

  it('fires no tenant query: the console shell asks for the session and nothing else', async () => {
    const sent = server(editor);
    renderIn(
      <ConsoleLayout>
        <ConsolePage />
      </ConsoleLayout>,
    );
    await waitFor(() => expect(nav.replace).toHaveBeenCalled());
    expect(within(railNav()).getByRole('link', { name: 'Vocabularies' })).toHaveAttribute('href', '/console/vocabularies');
    expect(new Set(sent.map((s) => `${s.method} ${s.path}`))).toEqual(new Set([`post ${REFRESH_PATH}`, `get ${ME_PATH}`]));
  });

  it('carries the console kicker, the person’s platform role, and a logo that leads back to the console', async () => {
    server(editor);
    renderIn(
      <ConsoleLayout>
        <ConsolePage />
      </ConsoleLayout>,
    );
    await waitFor(() => expect(document.querySelector('[data-who-panel]')).not.toBeNull());
    const who = document.querySelector('[data-who-panel]') as HTMLElement;
    expect(who).toHaveTextContent('Ida Holm');
    expect(who).toHaveTextContent('Library editor');
    expect(within(rail()).getByText('Platform console')).toHaveClass('microlabel');
    for (const logo of screen.getAllByRole('img', { name: 'bleqq, pronounced blek' })) {
      expect(logo.closest('a')).toHaveAttribute('href', '/console');
    }
    const header = document.querySelector('[data-mobile-header]') as HTMLElement;
    expect(within(header).getByText('Platform console')).toBeInTheDocument();
  });
});

describe('the surface follows the principal', () => {
  it('gives a person without a tenant the console rail on the pages both share, such as /me/passkeys', async () => {
    nav.pathname = '/me/passkeys';
    server(editor);
    renderIn(
      <TenantLayout>
        <h1>{'My passkeys'}</h1>
      </TenantLayout>,
    );
    expect(await screen.findByRole('heading', { name: 'My passkeys' })).toBeInTheDocument();
    expect(within(railNav()).getAllByRole('link').map((l) => l.getAttribute('href'))).toEqual(['/console/queue', '/console/vocabularies', '/console/change-facts', '/console/sources']);
    expect(within(rail()).getByText('Platform console')).toBeInTheDocument();
  });

  it('keeps a tenant member in their organisation’s rail, without the console kicker, and the logo on Today', async () => {
    nav.pathname = '/me/passkeys';
    server(member);
    renderIn(
      <TenantLayout>
        <h1>{'My passkeys'}</h1>
      </TenantLayout>,
    );
    await screen.findByRole('heading', { name: 'My passkeys' });
    expect(within(railNav()).getByRole('link', { name: 'Today' })).toHaveAttribute('href', '/');
    expect(within(railNav()).queryByRole('link', { name: 'Vocabularies' })).toBeNull();
    expect(screen.queryByText('Platform console')).toBeNull();
    for (const logo of screen.getAllByRole('img', { name: 'bleqq, pronounced blek' })) {
      expect(logo.closest('a')).toHaveAttribute('href', '/');
    }
  });

  it('sends a person without a tenant from / to the console, and never renders Today for them', async () => {
    nav.pathname = '/';
    server(editor);
    renderIn(
      <TenantLayout>
        <TodayPage />
      </TenantLayout>,
    );
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/console'));
    expect(screen.queryByRole('heading', { name: 'What is coming, and where we stand' })).toBeNull();
  });

  it('shows a tenant member Today at / and sends them nowhere', async () => {
    nav.pathname = '/';
    server(member);
    renderIn(
      <TenantLayout>
        <TodayPage />
      </TenantLayout>,
    );
    expect(await screen.findByRole('heading', { name: 'What is coming, and where we stand' })).toBeInTheDocument();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it('lands a signed-in person on their own home after sign in: the console, or Today', async () => {
    server(editor);
    const first = renderIn(<SignInScreen />);
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/console'));
    first.unmount();

    resetApiForTests();
    nav.replace.mockReset();
    server(member);
    renderIn(<SignInScreen />);
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/'));
    expect(nav.replace).not.toHaveBeenCalledWith('/console');
  });
});

describe('console vocabularies', () => {
  function withPermissions(permissions: readonly string[], node: ReactNode) {
    return renderIn(<PermissionsProvider permissions={permissions}>{node}</PermissionsProvider>);
  }

  it('lists the shared library lists only, each opening in the console, with no tabs and no way up to Admin', async () => {
    server(editor, vocabulary);
    withPermissions(EDITOR_PERMISSIONS, <VocabulariesScreen surface="console" />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Vocabularies' })).toBeInTheDocument();
    const rows = [...document.querySelectorAll('[data-vocabulary-list]')];
    expect(rows.map((row) => row.getAttribute('data-vocabulary-list'))).toEqual(['flag', 'library_tag']);
    expect(rows.map((row) => row.getAttribute('href'))).toEqual(['/console/vocabularies/flag', '/console/vocabularies/library_tag']);
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.queryByRole('link', { name: /Admin/ })).toBeNull();
    expect(screen.getByText('Every organisation shares these lists. A change you send waits for a second library editor.')).toBeInTheDocument();
  });

  it('keeps the tenant screen as it was: both tabs and links under Admin', async () => {
    server(member, vocabulary);
    withPermissions(MEMBER_PERMISSIONS, <VocabulariesScreen />);
    expect(await screen.findByRole('tablist')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Admin/ })).toHaveAttribute('href', '/admin');
    expect(document.querySelector('[data-vocabulary-list="tenant_tag"]')).toHaveAttribute('href', '/admin/vocabularies/tenant_tag');
  });

  it('lets library_vocab.manage suggest a change to a library list, which becomes a proposal, and leads back to the console list', async () => {
    server(editor, vocabulary);
    withPermissions(EDITOR_PERMISSIONS, <VocabularyScreen list="flag" surface="console" />);
    expect(await screen.findByRole('button', { name: 'Suggest a change' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '← Vocabularies' })).toHaveAttribute('href', '/console/vocabularies');
    expect(screen.getByText('Shared library list · 1 active')).toBeInTheDocument();
    expect(screen.getByText('Every organisation shares these lists. A change you send waits for a second library editor.')).toBeInTheDocument();
  });

  it('holds no tenant list: one opened by its address is not there', async () => {
    server(editor, vocabulary);
    withPermissions(EDITOR_PERMISSIONS, <VocabularyScreen list="tenant_tag" surface="console" />);
    expect(await screen.findByRole('heading', { name: 'Not found' })).toBeInTheDocument();
    expect(screen.getByText('There is nothing at this address in the console.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Vocabularies' })).toHaveAttribute('href', '/console/vocabularies');
    expect(screen.queryByRole('button', { name: 'Suggest a change' })).toBeNull();
  });
});
