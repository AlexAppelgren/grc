import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { SupportAccessScreen } from '@/components/admin/SupportAccessScreen';
import type { SupportAccessGrant } from '@/features/support-access/types';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, setStepUpHandler } from '@/shared/utils/api-client';

// The bank's support access panel (TEN-06, D-49): pending, live and past
// grants in their own sections; Approve goes through the passkey step-up,
// Decline and Revoke do not; a request decided elsewhere reloads the list.

const LIST = '/api/v1/tenant/support-access';
const kari = { id: 'p1', name: 'Kari Nygaard' };
const lars = { id: 'p2', name: 'Lars Mikkelsen' };
const erik = { id: 'u1', name: 'Erik Holm' };

const pending: SupportAccessGrant = {
  id: 'g-pending',
  state: 'pending',
  purpose: 'Your weekly briefing stopped arriving.',
  ticketRef: 'SUP-2291',
  hours: 2,
  platformPerson: kari,
  requestedAt: '2026-09-25T07:12:00Z',
  decidedBy: null,
  decidedAt: null,
  endsAt: null,
};
const active: SupportAccessGrant = {
  ...pending,
  id: 'g-active',
  state: 'active',
  purpose: 'Two changes show twice on Watch.',
  ticketRef: 'SUP-2287',
  platformPerson: lars,
  decidedBy: erik,
  decidedAt: '2026-09-25T06:30:00Z',
  endsAt: '2026-09-25T08:30:00Z',
};
const declined: SupportAccessGrant = { ...pending, id: 'g-declined', state: 'declined', purpose: 'Routine check of the search index.', ticketRef: '', decidedBy: erik, decidedAt: '2026-09-03T14:40:00Z' };

const stepUpRequired: Answer = { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.', status: 403 } };
const stale: Answer = { status: 422, data: { code: 'invalid_transition', detail: 'This request is no longer pending.', status: 422 } };

function server(grants: SupportAccessGrant[], decide: (sent: Sent) => Answer = () => ({ status: 500 })): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === LIST && sent.method === 'get') return { status: 200, data: { items: grants, total: grants.length } };
    if (sent.path.startsWith(`${LIST}/`) && sent.method === 'post') return decide(sent);
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderScreen(permissions: string[] = ['security.manage', 'audit.read']): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <SupportAccessScreen />
      </PermissionsProvider>
    </Query>,
  );
}

const section = (name: string) => document.querySelector(`[data-support-section="${name}"]`) as HTMLElement;
const posts = (sent: Sent[]) => sent.filter((s) => s.method === 'post' && s.path !== REFRESH_PATH).map((s) => s.path);

beforeEach(() => {
  resetApiForTests();
});

describe('the support access panel', () => {
  it('puts each grant in its section with its state pill and facts', async () => {
    server([pending, active, declined]);
    renderScreen();
    await screen.findByText('Waiting for your decision');

    const waiting = section('pending');
    expect(within(waiting).getByText('Waiting for approval')).toHaveAttribute('data-pill', 'warning');
    expect(within(waiting).getByText('Kari Nygaard, bleqq support')).toBeInTheDocument();
    expect(within(waiting).getByText('SUP-2291')).toBeInTheDocument();
    expect(within(waiting).getByText('2 hours, starting when you approve')).toBeInTheDocument();
    expect(within(waiting).getByRole('button', { name: 'Approve' })).toBeEnabled();
    expect(within(waiting).getByRole('button', { name: 'Decline' })).toBeEnabled();

    const live = section('active');
    expect(within(live).getByText('Active')).toHaveAttribute('data-pill', 'notice');
    expect(within(live).getByText(/by Erik Holm$/)).toBeInTheDocument();
    expect(within(live).getByRole('button', { name: 'Revoke' })).toBeEnabled();
    expect(within(live).queryByRole('button', { name: 'Approve' })).toBeNull();

    const history = section('history');
    expect(within(history).getByText('Declined')).toHaveAttribute('data-pill', 'information');
    expect(within(history).queryByRole('button')).toBeNull();
    expect(within(history).queryByText('Ticket')).toBeNull();
  });

  it('says so when support never asked', async () => {
    server([]);
    renderScreen();
    expect(await screen.findByText('Nobody from bleqq has asked for access')).toBeInTheDocument();
  });

  it('shows the grants but no decision to a member without security.manage', async () => {
    server([pending, active]);
    renderScreen(['audit.read']);
    await screen.findByText('Waiting for your decision');
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Revoke' })).toBeNull();
    expect(screen.getAllByText('Only a member who manages security can approve, decline or revoke.')).toHaveLength(2);
  });

  it('approves behind the passkey step-up and says until when', async () => {
    let calls = 0;
    const sent = server([pending], () => {
      calls += 1;
      return calls === 1 ? stepUpRequired : { status: 200, data: { ...pending, state: 'active', decidedBy: erik, decidedAt: '2026-09-25T09:14:00Z', endsAt: '2026-09-25T11:14:00Z' } };
    });
    const prompts: number[] = [];
    setStepUpHandler(() => {
      prompts.push(1);
      return Promise.resolve(true);
    });
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    expect(await screen.findByText(/^Approved\. Kari Nygaard can read until /)).toBeInTheDocument();
    expect(prompts).toHaveLength(1);
    expect(posts(sent)).toEqual([`${LIST}/g-pending/approve`, `${LIST}/g-pending/approve`]);
  });

  it('shows it is approving, and takes no second click, while the passkey prompt is open', async () => {
    let confirm: (given: boolean) => void = () => undefined;
    const sent = server([pending], () => stepUpRequired);
    setStepUpHandler(
      () =>
        new Promise<boolean>((resolve) => {
          confirm = resolve;
        }),
    );
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    const busy = await screen.findByRole('button', { name: 'Approving…' });
    expect(busy).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Decline' })).toBeDisabled();
    fireEvent.click(busy);
    expect(posts(sent)).toHaveLength(1);
    confirm(false);
    expect(await screen.findByRole('alert')).toHaveTextContent('Nothing changed. Approving needs your passkey.');
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled();
  });

  it('declines and revokes without a passkey', async () => {
    const prompts: number[] = [];
    setStepUpHandler(() => {
      prompts.push(1);
      return Promise.resolve(true);
    });
    const sent = server([pending, active], (s) =>
      s.path.endsWith('/decline')
        ? { status: 200, data: { ...pending, state: 'declined', decidedBy: erik, decidedAt: '2026-09-25T09:00:00Z' } }
        : { status: 200, data: { ...active, state: 'revoked', decidedAt: '2026-09-25T07:47:00Z' } },
    );
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: 'Decline' }));
    expect(await screen.findByText('Declined. Nothing was opened.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    expect(await screen.findByText(/^Revoked\. Lars Mikkelsen's access ended at /)).toBeInTheDocument();
    expect(prompts).toHaveLength(0);
    expect(posts(sent)).toEqual([`${LIST}/g-pending/decline`, `${LIST}/g-active/revoke`]);
  });

  it('reloads the list when the request was already decided or lapsed', async () => {
    const sent = server([pending], () => stale);
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: 'Decline' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This request was already decided or has lapsed. The list now shows where it stands.');
    await waitFor(() => expect(sent.filter((s) => s.method === 'get' && s.path === LIST)).toHaveLength(2));
  });
});
