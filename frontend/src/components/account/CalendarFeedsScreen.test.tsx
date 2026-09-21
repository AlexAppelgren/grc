import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CalendarFeedsPage from '@/app/(tenant)/me/calendar-feeds/page';
import { CalendarFeedsScreen } from '@/components/account/CalendarFeedsScreen';
import type { Me } from '@/features/identity/types';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// My calendar feeds (design/screens/tenant-calendar-feeds.html, HOM-04,
// D-52, ADR 0045): the list bound to when each one was last fetched,
// subscribing with no body to fill in, and the invariant that decides this
// screen — the address is shown once and reaches nothing that survives the
// render.

const ME_PATH = '/api/v1/me';
const FEEDS_PATH = '/api/v1/calendar-feeds';
const NOW = new Date('2026-09-22T08:00:00Z');
const ADDRESS = 'https://compliance.bleqq.test/api/v1/calendar/feed.ics?token=a1b2c3d4e5f6a1b2.shown-once-secret';

const me: Me = {
  user: { id: 'u1', email: 'sara@example.test', name: 'Sara Lindqvist', locale: 'en' },
  tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm' },
  roles: [{ key: 'compliance_officer', kind: null, label: 'Compliance officer' }],
  permissions: ['roadmap.read'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
  counts: null,
  lastVisitAt: null,
};

const live = { id: 'f1', createdAt: '2026-09-10T08:00:00Z', lastUsedAt: '2026-09-22T06:02:00Z', revokedAt: null };
const revoked = { id: 'f2', createdAt: '2026-08-01T08:00:00Z', lastUsedAt: null, revokedAt: '2026-09-12T09:00:00Z' };

function server(feeds: Answer, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: me };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === FEEDS_PATH && sent.method === 'get') return feeds;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const rowOf = (id: string) => document.querySelector(`[data-feed-id="${id}"]`) as HTMLElement;
const writes = (sent: Sent[]) => sent.filter((s) => (s.method === 'post' || s.method === 'delete') && s.path !== REFRESH_PATH);

describe('my calendar feeds', () => {
  beforeEach(() => {
    resetApiForTests();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('lists each subscription with its status, when it was made and when it was last fetched', async () => {
    server({ status: 200, data: [live, revoked] });
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('Active');

    const first = rowOf('f1');
    expect(within(first).getByText('Active')).toBeInTheDocument();
    expect(within(first).getByText('Subscribed 10 Sept 2026, 10:00')).toBeInTheDocument();
    expect(within(first).getByText(/Last fetched/)).toBeInTheDocument();
    expect(within(first).getByRole('button', { name: 'Revoke' })).toBeInTheDocument();

    // A revoked subscription stays listed, dated, and offers nothing to press.
    const second = rowOf('f2');
    expect(within(second).getByText('Revoked')).toBeInTheDocument();
    expect(within(second).getByText('Never fetched')).toBeInTheDocument();
    expect(within(second).getByText(/Revoked 12 Sept 2026/)).toBeInTheDocument();
    expect(within(second).queryByRole('button', { name: 'Revoke' })).toBeNull();
  });

  it('shows the address once, and never puts it anywhere that outlives the render', async () => {
    const sent = server({ status: 200, data: [] }, (s) => (s.path === FEEDS_PATH && s.method === 'post' ? { status: 201, data: { feed: live, url: ADDRESS } } : undefined));
    const { container, unmount } = renderIn(<CalendarFeedsScreen />);
    await screen.findByText('No calendar feeds');

    fireEvent.click(screen.getByRole('button', { name: 'Subscribe to calendar feed' }));
    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    expect(writes(sent)[0]).toMatchObject({ path: FEEDS_PATH, body: {} });

    const address = await screen.findByText(ADDRESS);
    expect(address).toBeInTheDocument();
    expect(screen.getByText(/anyone holding it can read your roadmap/)).toBeInTheDocument();

    expect(JSON.stringify(Object.entries(window.localStorage))).not.toContain(ADDRESS);
    expect(JSON.stringify(Object.entries(window.sessionStorage))).not.toContain(ADDRESS);
    expect(window.location.href).not.toContain(ADDRESS);
    expect(JSON.stringify(sent.filter((s) => s.method === 'get'))).not.toContain(ADDRESS);
    expect(screen.queryByRole('button', { name: /show/i })).toBeNull();

    unmount();
    const again = renderIn(<CalendarFeedsScreen />);
    await waitFor(() => expect(again.container.textContent).not.toContain(ADDRESS));
    expect(container.textContent).toBe('');
  });

  it('says nothing changed when the passkey step-up is refused', async () => {
    server({ status: 200, data: [] }, (s) => (s.path === FEEDS_PATH && s.method === 'post' ? { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } } : undefined));
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('No calendar feeds');

    fireEvent.click(screen.getByRole('button', { name: 'Subscribe to calendar feed' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveAttribute('data-problem-code', 'step_up_required');
    expect(alert).toHaveTextContent('The action was not confirmed, so nothing changed.');
    expect(screen.queryByText(ADDRESS)).toBeNull();
  });

  it('tells the person to revoke one first once they hold the cap', async () => {
    server({ status: 200, data: [live] }, (s) =>
      s.path === FEEDS_PATH && s.method === 'post' ? { status: 409, data: { code: 'feed_limit_reached', detail: 'You already have 5 calendar subscriptions. Stop one you no longer use and then subscribe again.' } } : undefined,
    );
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('Active');

    fireEvent.click(screen.getByRole('button', { name: 'Subscribe to calendar feed' }));
    expect(await screen.findByText('You already have 5 calendar subscriptions. Stop one you no longer use and then subscribe again.')).toBeInTheDocument();
  });

  it('asks in a dialog before revoking, and revokes through the real route', async () => {
    const sent = server({ status: 200, data: [live] }, (s) => (s.method === 'delete' ? { status: 204 } : undefined));
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('Active');

    fireEvent.click(within(rowOf('f1')).getByRole('button', { name: 'Revoke' }));
    const dialog = await screen.findByRole('dialog', { name: 'Revoke this calendar feed?' });
    expect(dialog).toHaveTextContent('It stops working right away');
    expect(dialog).toHaveTextContent('which regulatory changes your bank has open work on');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke the feed' }));
    await waitFor(() => expect(writes(sent)).toHaveLength(1));
    expect(writes(sent)[0]?.path).toBe(`${FEEDS_PATH}/f1`);
  });

  it('closes the dialog without revoking on cancel', async () => {
    const sent = server({ status: 200, data: [live] });
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('Active');

    fireEvent.click(within(rowOf('f1')).getByRole('button', { name: 'Revoke' }));
    const dialog = await screen.findByRole('dialog', { name: 'Revoke this calendar feed?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toHaveLength(0);
  });

  it('says there are no feeds yet when the list is empty', async () => {
    server({ status: 200, data: [] });
    renderIn(<CalendarFeedsScreen />);
    expect(await screen.findByText('No calendar feeds')).toBeInTheDocument();
  });

  it('offers a retry when the list could not be read', async () => {
    server({ status: 502, data: { code: 'bad_gateway', detail: 'Try again shortly.' } });
    renderIn(<CalendarFeedsScreen />);
    expect(await screen.findByText('Could not load your calendar feeds')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('is loading before the list arrives', () => {
    server({ status: 200, data: [] });
    const { container } = renderIn(<CalendarFeedsScreen />);
    expect(container.querySelector('[data-loading-state]')).not.toBeNull();
  });

  it('shows the Restricted screen, naming the grant, to a reader without roadmap.read', async () => {
    server({ status: 200, data: [] });
    renderIn(
      <PermissionsProvider permissions={[]}>
        <CalendarFeedsPage />
      </PermissionsProvider>,
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Needs roadmap read');
    expect(screen.queryByRole('button', { name: 'Subscribe to calendar feed' })).toBeNull();
  });
});
