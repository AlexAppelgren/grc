import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CalendarFeedsPage from '@/app/(tenant)/me/calendar-feeds/page';
import { StepUpProvider } from '@/components/auth/StepUpProvider';
import { CalendarFeedsScreen } from '@/components/account/CalendarFeedsScreen';
import type { Me } from '@/features/identity/types';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, setStepUpHandler } from '@/shared/utils/api-client';
import { logger } from '@/shared/utils/logger';

// Calendar feeds (design/screens/tenant-calendar-feeds.html, HOM-04, D-52,
// ADR 0045): a person's own feeds with when each was made and last fetched,
// "New feed" with nothing to fill in, the two refusals the contract makes
// plain, and the rule that decides this screen: the address is shown once
// and reaches nothing that outlives the dialog.

const ME_PATH = '/api/v1/me';
const FEEDS_PATH = '/api/v1/calendar-feeds';
const ADDRESS = 'http://localhost:8000/api/v1/calendar/feed.ics?token=a1b2c3d4e5f6a1b2.shown-once-secret';

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
  notificationPrefs: null,
};

const live = { id: 'f1', createdAt: '2026-09-10T08:00:00Z', lastUsedAt: '2026-09-22T06:02:00Z', revokedAt: null };
const revoked = { id: 'f2', createdAt: '2026-08-01T08:00:00Z', lastUsedAt: null, revokedAt: '2026-09-12T09:00:00Z' };
const STEP_UP: Answer = { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } };

function server(feeds: Answer, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: me };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === FEEDS_PATH && sent.method === 'get') return feeds;
    return { status: 404, data: { code: 'not_found', detail: 'Not in this test.' } };
  });
}

const creates = (answer: Answer | ((index: number) => Answer)) => {
  let calls = 0;
  return (sent: Sent) => (sent.path === FEEDS_PATH && sent.method === 'post' ? (typeof answer === 'function' ? answer(calls++) : answer) : undefined);
};

function renderIn(node: ReactNode) {
  const { wrapper: Query, queryClient } = queryWrapper();
  return { ...render(<Query>{node}</Query>), queryClient };
}

// Feeds have no names (D-52): the created date tells one from another.
const REVOKE_F1 = /^Revoke the feed created 10 Sept? 2026, 10:00$/;
const REVOKE_F1_DIALOG = /^Revoke the feed created 10 Sept? 2026, 10:00\?$/;
const rowOf = (id: string) => document.querySelector(`[data-feed-id="${id}"]`) as HTMLElement;
const writes = (sent: Sent[]) => sent.filter((s) => (s.method === 'post' || s.method === 'delete') && s.path !== REFRESH_PATH);

describe('calendar feeds', () => {
  beforeEach(() => {
    resetApiForTests();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists each feed with its status, when it was created and when it was last fetched', async () => {
    server({ status: 200, data: [live, revoked] });
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('Active');

    const first = rowOf('f1');
    expect(within(first).getByText(/^Created 10 Sept? 2026, 10:00$/)).toBeInTheDocument();
    expect(within(first).getByText(/^Last fetched 22 Sept? 2026, 08:02$/)).toBeInTheDocument();
    // The button says which feed it revokes.
    expect(within(first).getByRole('button', { name: REVOKE_F1 })).toBeInTheDocument();

    // A revoked feed stays listed and dated, and offers nothing to press.
    const second = rowOf('f2');
    expect(within(second).getByText('Revoked')).toBeInTheDocument();
    expect(within(second).getByText('Never fetched')).toBeInTheDocument();
    expect(within(second).getByText(/^Revoked 12 Sept? 2026, 11:00$/)).toBeInTheDocument();
    expect(within(second).queryByRole('button')).toBeNull();
    // Rows carry no address: the list never had one.
    expect(document.body.textContent).not.toContain('feed.ics');
  });

  it('creates a feed with nothing to fill in, and shows the address once in a dialog with a copy control and the warning', async () => {
    const sent = server({ status: 200, data: [] }, creates({ status: 201, data: { feed: live, url: ADDRESS } }));
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const logged = [vi.spyOn(logger, 'debug'), vi.spyOn(logger, 'info'), vi.spyOn(logger, 'warn'), vi.spyOn(logger, 'error')];
    const { queryClient } = renderIn(<CalendarFeedsScreen />);
    await screen.findByText('No calendar feeds');

    fireEvent.click(screen.getByRole('button', { name: 'New feed' }));
    const dialog = await screen.findByRole('dialog', { name: 'Copy this address into your calendar' });
    expect(writes(sent)).toEqual([expect.objectContaining({ method: 'post', path: FEEDS_PATH, body: {} })]);
    expect(within(dialog).getByText(ADDRESS)).toBeInTheDocument();
    expect(dialog).toHaveTextContent('It is shown once and never again.');
    expect(dialog).toHaveTextContent('which regulatory changes your bank has open work on');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Copy address' }));
    expect(await within(dialog).findByText('Copied.')).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(ADDRESS);

    // Nothing that outlives the dialog holds it: no storage, no address bar,
    // no log line, and no later request carries it.
    expect(JSON.stringify({ ...window.localStorage })).not.toContain('shown-once-secret');
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain('shown-once-secret');
    expect(window.location.href).not.toContain('shown-once-secret');
    for (const spy of logged) expect(JSON.stringify(spy.mock.calls)).not.toContain('shown-once-secret');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.body.textContent).not.toContain('shown-once-secret');
    expect(JSON.stringify(sent)).not.toContain('shown-once-secret');
    // Nor does the query client keep the answer once the dialog has closed.
    await waitFor(() => expect(JSON.stringify(queryClient.getMutationCache().getAll().map((m) => m.state.data))).not.toContain('shown-once-secret'));
  });

  it('keeps the address on screen through Escape and a click outside, so only Done can drop it', async () => {
    server({ status: 200, data: [] }, creates({ status: 201, data: { feed: live, url: ADDRESS } }));
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('No calendar feeds');

    fireEvent.click(screen.getByRole('button', { name: 'New feed' }));
    const dialog = await screen.findByRole('dialog', { name: 'Copy this address into your calendar' });
    fireEvent.keyDown(dialog, { key: 'Escape' });
    // Radix portals the overlay just before the dialog: a mouse press there
    // is a click outside it.
    const overlay = dialog.previousElementSibling as HTMLElement;
    fireEvent.pointerDown(overlay, { button: 0, pointerType: 'mouse' });
    fireEvent.pointerUp(overlay, { button: 0, pointerType: 'mouse' });
    fireEvent.click(overlay);
    // The query client announces a reset on its next tick; let that land.
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
    expect(screen.getByRole('dialog', { name: 'Copy this address into your calendar' })).toHaveTextContent(ADDRESS);

    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('asks for the passkey when the sign-in is not recent, and says nothing changed when the person cancels', async () => {
    server({ status: 200, data: [] }, creates(STEP_UP));
    renderIn(
      <StepUpProvider>
        <CalendarFeedsScreen />
      </StepUpProvider>,
    );
    await screen.findByText('No calendar feeds');

    fireEvent.click(screen.getByRole('button', { name: 'New feed' }));
    const prompt = await screen.findByRole('dialog', { name: 'Confirm with your passkey' });
    fireEvent.click(within(prompt).getByRole('button', { name: 'Cancel' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveAttribute('data-problem-code', 'step_up_required');
    expect(alert).toHaveTextContent('The action was not confirmed, so nothing changed.');
    expect(screen.queryByText(ADDRESS)).toBeNull();
  });

  it('retries once the passkey is confirmed, and then shows the address', async () => {
    const sent = server({ status: 200, data: [] }, creates((index) => (index === 0 ? STEP_UP : { status: 201, data: { feed: live, url: ADDRESS } })));
    setStepUpHandler(() => Promise.resolve(true));
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('No calendar feeds');

    fireEvent.click(screen.getByRole('button', { name: 'New feed' }));
    expect(await screen.findByText(ADDRESS)).toBeInTheDocument();
    expect(writes(sent).map((s) => s.method)).toEqual(['post', 'post']);
  });

  it('tells the person to revoke one first once they hold as many feeds as allowed', async () => {
    server({ status: 200, data: [live] }, creates({ status: 409, data: { code: 'feed_limit_reached', detail: 'You already have 5 calendar subscriptions.' } }));
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('Active');

    fireEvent.click(screen.getByRole('button', { name: 'New feed' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveAttribute('data-problem-code', 'feed_limit_reached');
    expect(alert).toHaveTextContent('You already have as many feeds as one person can hold. Revoke one you no longer use first.');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('asks in a dialog before revoking, and revokes through the real route', async () => {
    const sent = server({ status: 200, data: [live] }, (s) => (s.method === 'delete' ? { status: 204 } : undefined));
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('Active');

    fireEvent.click(within(rowOf('f1')).getByRole('button', { name: REVOKE_F1 }));
    const dialog = await screen.findByRole('dialog', { name: REVOKE_F1_DIALOG });
    expect(dialog).toHaveTextContent('The address stops working at once');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([expect.objectContaining({ method: 'delete', path: `${FEEDS_PATH}/f1` })]);
  });

  it('closes the revoke dialog without revoking on cancel', async () => {
    const sent = server({ status: 200, data: [live] });
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('Active');

    fireEvent.click(within(rowOf('f1')).getByRole('button', { name: REVOKE_F1 }));
    const dialog = await screen.findByRole('dialog', { name: REVOKE_F1_DIALOG });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(writes(sent)).toEqual([]);
  });

  it('keeps the dialog open and says why when a revoke fails', async () => {
    server({ status: 200, data: [live] }, (s) => (s.method === 'delete' ? { status: 404, data: { code: 'not_found', detail: 'No such calendar feed.' } } : undefined));
    renderIn(<CalendarFeedsScreen />);
    await screen.findByText('Active');

    fireEvent.click(within(rowOf('f1')).getByRole('button', { name: REVOKE_F1 }));
    const dialog = await screen.findByRole('dialog', { name: REVOKE_F1_DIALOG });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('No such calendar feed.');
  });

  it('says there are no feeds yet and names the next step', async () => {
    server({ status: 200, data: [] });
    renderIn(<CalendarFeedsScreen />);
    expect(await screen.findByText('No calendar feeds')).toBeInTheDocument();
    expect(screen.getByText('Create one to see the roadmap in your calendar.')).toBeInTheDocument();
  });

  it('is loading before the list arrives, and offers a retry when it cannot be read', async () => {
    server({ status: 502, data: { code: 'bad_gateway', detail: 'Try again shortly.' } });
    const { container } = renderIn(<CalendarFeedsScreen />);
    expect(container.querySelector('[data-loading-state]')).not.toBeNull();
    expect(await screen.findByText('Could not load your feeds')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('shows the Restricted screen, naming the grant, when the server refuses the list', async () => {
    server({ status: 403, data: { code: 'permission_denied', detail: '', requiredPermission: 'roadmap.read' } });
    renderIn(<CalendarFeedsScreen />);
    expect(await screen.findByText('Needs roadmap read')).toBeInTheDocument();
    expect(screen.queryByText('Could not load your feeds')).toBeNull();
  });

  it('links back to the roadmap it belongs to', async () => {
    server({ status: 200, data: [] });
    renderIn(<CalendarFeedsScreen />);
    expect(await screen.findByRole('link', { name: '← Roadmap' })).toHaveAttribute('href', '/roadmap');
  });

  it('gates the page on roadmap.read, the grant the roadmap itself needs', async () => {
    server({ status: 200, data: [] });
    renderIn(
      <PermissionsProvider permissions={[]}>
        <CalendarFeedsPage />
      </PermissionsProvider>,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Needs roadmap read');
    expect(screen.queryByRole('button', { name: 'New feed' })).toBeNull();
  });
});
