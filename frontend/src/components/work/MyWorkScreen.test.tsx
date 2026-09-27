import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { identityKeys } from '@/features/identity/hooks';
import type { Me } from '@/features/identity/types';
import type { WorkItem, WorkPage } from '@/features/my-work/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { MyWorkScreen } from './MyWorkScreen';

// /work (design/screens/tenant-my-work.html): four sections in order with
// their counts, reasons as text, a permission-limited line, the line to
// Today, the empty and error states, and a department head's switch that
// this device remembers.

const nav = vi.hoisted(() => ({ search: '', replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/work',
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const RETAIL = { id: 'unit-retail', name: 'Retail Banking' };

const me: Me = {
  user: { id: 'u-anna', email: 'owner@example-bank.test', name: 'Anna Nilsson', locale: 'en' },
  tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm' },
  roles: [],
  permissions: ['register.read', 'cases.read'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
  counts: null,
  lastVisitAt: null,
  notificationPrefs: null,
  headOf: [],
} as unknown as Me;

const ANNA = { person: { id: 'u-anna', name: 'Anna Nilsson' }, team: null };
const TEAM = { person: null, team: { key: 'retail_compliance', kind: null, label: 'Retail compliance' } };
const subject = (title: string, ids: Partial<WorkItem['subject']> = {}) => ({ obligationId: null, changeId: null, internalItemId: null, title, ...ids });

const overdue: WorkItem = {
  bucket: 'overdue',
  itemKind: 'tenant_obligation',
  subject: subject('Pay for third-party research only under the permitted models', { obligationId: 'ob-1' }),
  entity: null,
  date: { value: '2026-09-07', kind: 'review', precision: 'day' },
  reasons: [{ reason: 'owner', who: ANNA, via: null }],
  status: { key: 'partly', kind: 'partly', label: 'Partly compliant' },
  urgency: null,
  openChangeCount: 1,
};
const aware: WorkItem = {
  bucket: 'aware',
  itemKind: 'change_case',
  subject: subject('FI adopts amended rules on paying for investment research', { changeId: 'ch-1' }),
  entity: null,
  date: { value: '2026-09-17', kind: 'linked', precision: 'day' },
  reasons: [{ reason: 'owner', who: ANNA, via: { obligationId: 'ob-1', title: 'Pay for third-party research only under the permitted models' } }],
  status: null,
  urgency: { key: 'act_now', kind: null, label: 'Act now' },
  openChangeCount: 0,
};
const open: WorkItem = {
  bucket: 'open',
  itemKind: 'internal_item',
  subject: subject('Complaints procedure', { internalItemId: 'ii-1' }),
  entity: null,
  date: null,
  reasons: [{ reason: 'participant', who: TEAM, via: null }],
  status: null,
  urgency: null,
  openChangeCount: 0,
};

function page(items: WorkItem[], extra: Partial<WorkPage> = {}): WorkPage {
  const count = (bucket: WorkItem['bucket']) => items.filter((item) => item.bucket === bucket).length;
  return {
    scope: 'mine',
    unit: null,
    counts: { overdue: count('overdue'), dueSoon: count('due_soon'), aware: count('aware'), open: count('open') },
    permissionLimited: [],
    items,
    total: items.length,
    ...extra,
  };
}

// The session gate renders a screen only once the session is in, as here.
function shell(children: ReactNode, session: Me = me): ReactNode {
  const { wrapper: Query, queryClient } = queryWrapper();
  queryClient.setQueryData(identityKeys.me, session);
  return (
    <Query>
      <PermissionsProvider permissions={me.permissions}>
        <LocaleProvider locale="en">{children}</LocaleProvider>
      </PermissionsProvider>
    </Query>
  );
}

function serve(work: (sent: Sent) => { status: number; data?: unknown }, session: Me = me): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: session };
    if (sent.path === '/api/v1/me/work') return work(sent);
    if (sent.path === '/api/v1/me/comments') return { status: 200, data: { items: [], total: 0, permissionLimitedKinds: [] } };
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
  nav.search = '';
  nav.replace.mockReset();
  window.localStorage.clear();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-09-19T10:00:00Z'));
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('MyWorkScreen', () => {
  it('draws the four sections in order with counts, dates, days and reasons, and the line to Today', async () => {
    serve(() => ({ status: 200, data: page([overdue, aware, open]) }));
    render(shell(<MyWorkScreen />));

    expect(await screen.findByRole('heading', { level: 1, name: 'My work' })).toBeInTheDocument();
    await screen.findByText('12 days overdue');
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Overdue',
      'Due soon',
      'Changes on your items',
      "Everything you're responsible for",
      'Comments and mentions',
    ]);
    const overdueSection = document.querySelector('[data-work-section="overdue"]') as HTMLElement;
    expect(within(overdueSection).getByRole('link', { name: overdue.subject.title })).toHaveAttribute('href', '/inventory/obligations/ob-1');
    expect(within(overdueSection).getByText('Partly compliant')).toBeInTheDocument();
    expect(within(overdueSection).getByText('Review 7 Sept 2026')).toBeInTheDocument();
    expect(within(overdueSection).getByText("You're responsible")).toBeInTheDocument();
    expect(within(document.querySelector('[data-work-section="due_soon"]') as HTMLElement).getByText('Nothing due in the coming weeks.')).toBeInTheDocument();

    const awareSection = document.querySelector('[data-work-section="aware"]') as HTMLElement;
    expect(within(awareSection).getByRole('link', { name: aware.subject.title })).toHaveAttribute('href', '/watch/ch-1');
    expect(within(awareSection).getByText('Act now')).toBeInTheDocument();
    expect(within(awareSection).getByText('2 days ago')).toBeInTheDocument();
    expect(within(awareSection).getByText(`Linked to ${overdue.subject.title}`)).toBeInTheDocument();

    const openSection = document.querySelector('[data-work-section="open"]') as HTMLElement;
    expect(within(openSection).queryByRole('link')).not.toBeInTheDocument();
    expect(within(openSection).getByText('No date')).toBeInTheDocument();
    expect(within(openSection).getByText('Your team takes part')).toBeInTheDocument();

    expect(screen.getByText('Sign-offs and other decisions waiting for you are on Today.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Today' })).toHaveAttribute('href', '/');
  });

  it('names a kind the role cannot open instead of saying there is nothing to do', async () => {
    serve(() => ({ status: 200, data: page([], { permissionLimited: ['tenant_obligation'] }) }));
    render(shell(<MyWorkScreen />));

    expect(await screen.findByText('Obligations are not shown here, and are left out of the counts, because your role cannot open them.')).toBeInTheDocument();
    expect(screen.queryByText('Nothing needs you right now')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Overdue' })).toBeInTheDocument();
  });

  it('says nothing needs you when every section is empty, with the way to Today', async () => {
    serve(() => ({ status: 200, data: page([]) }));
    render(shell(<MyWorkScreen />));

    expect(await screen.findByText('Nothing needs you right now')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Today' })).toHaveAttribute('href', '/');
    expect(screen.queryByRole('group', { name: 'Whose work' })).not.toBeInTheDocument();
  });

  it('shows the error with Try again, which reads again', async () => {
    let calls = 0;
    serve(() => (++calls === 1 ? { status: 500, data: { code: 'server_error', detail: 'Down.' } } : { status: 200, data: page([overdue]) }));
    render(shell(<MyWorkScreen />));

    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('12 days overdue')).toBeInTheDocument();
  });

  it('opens a head on their department, names who is responsible, and remembers a switch to their own work', async () => {
    const head = { ...me, headOf: [RETAIL] } as Me;
    const sent = serve((s) => ({ status: 200, data: page([overdue], (s.params as { scope: string }).scope === 'unit' ? { scope: 'unit', unit: RETAIL.id } : {}) }), head);
    render(shell(<MyWorkScreen />, head));

    const group = await screen.findByRole('group', { name: 'Whose work' });
    expect(within(group).getByRole('button', { name: 'Retail Banking' })).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByText('Anna Nilsson is responsible')).toBeInTheDocument();

    fireEvent.click(within(group).getByRole('button', { name: 'Mine' }));
    expect(await screen.findByText("You're responsible")).toBeInTheDocument();
    expect(window.localStorage.getItem('cw.myWork.scope')).toBe('mine');
    const reads = sent.filter((s) => s.path === '/api/v1/me/work').map((s) => s.params);
    expect(reads).toEqual([
      { scope: 'unit', unit: RETAIL.id, limit: 100, offset: 0 },
      { scope: 'mine', limit: 100, offset: 0 },
    ]);
  });

  it('opens a department named in the address for a member who heads none, and grants nothing', async () => {
    nav.search = 'unit=unit-retail';
    const sent = serve(() => ({ status: 200, data: page([overdue], { scope: 'unit', unit: RETAIL.id }) }));
    render(shell(<MyWorkScreen />));

    const group = await screen.findByRole('group', { name: 'Whose work' });
    expect(within(group).getByRole('button', { name: 'This department' })).toHaveAttribute('aria-pressed', 'true');
    await screen.findByText('Anna Nilsson is responsible');
    expect(sent.find((s) => s.path === '/api/v1/me/work')?.params).toEqual({ scope: 'unit', unit: RETAIL.id, limit: 100, offset: 0 });

    fireEvent.click(within(group).getByRole('button', { name: 'Mine' }));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/work'));
  });
});
