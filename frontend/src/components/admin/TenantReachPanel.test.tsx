import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { TenantReachPanel } from '@/components/admin/TenantReachPanel';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// Tenant reach on Security (ACC-08): asked by one holder of security.manage
// with a passkey, decided by another; the requester is offered no decision and
// a four-eyes refusal is a state; switching off needs one person and confirms.

const REACH = '/api/v1/tenant/reach';
const SECURITY = ['security.manage'];

const me = (id: string) => ({
  user: { id, email: `${id}@bank.example`, name: id, locale: 'en' },
  tenant: null,
  roles: [],
  permissions: SECURITY,
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
});

const pending = { id: 'r1', status: 'pending', requestedBy: { id: 'u-sara', name: 'Sara Lindqvist' }, requestedAt: '2026-09-25T07:12:00Z', decidedAt: null, decidedBy: null, version: 1 };
const off = { enabled: false, changedAt: null, changedBy: null, pending: null };

function server(reach: unknown, viewer = 'u-erik', extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === '/api/v1/me') return { status: 200, data: me(viewer) };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === REACH && sent.method === 'get') return { status: 200, data: reach };
    return { status: 500 };
  });
}

function open(permissions: readonly string[] = SECURITY) {
  const { wrapper: Query } = queryWrapper();
  return render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <LocaleProvider locale="en">
          <TenantReachPanel />
        </LocaleProvider>
      </PermissionsProvider>
    </Query>,
  );
}

const writes = (sent: Sent[]) => sent.filter((s) => s.method === 'post' && s.path.startsWith(REACH)).map((s) => s.path);

describe('tenant reach panel', () => {
  beforeEach(() => resetApiForTests());

  it('asks to switch it on, and says a second person decides', async () => {
    const sent = server(off, 'u-erik', (s) => (s.method === 'post' && s.path === `${REACH}/requests` ? { status: 201, data: pending } : undefined));
    open();
    expect(await screen.findByText(/^Off\. The agents we register/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ask to switch it on' }));
    expect(await screen.findByText('Asked. Another member holding security manage can approve it here.')).toBeInTheDocument();
    expect(writes(sent)).toEqual([`${REACH}/requests`]);
  });

  it('shows the requester the waiting banner and no decision', async () => {
    server({ ...off, pending }, 'u-sara');
    open();
    expect(await screen.findByText(/^You asked to switch this on/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve with passkey' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });

  it('lets a second person approve, naming who asked', async () => {
    const sent = server({ ...off, pending }, 'u-erik', (s) => (s.method === 'post' && s.path.endsWith('/approve') ? { status: 200, data: { ...pending, status: 'approved' } } : undefined));
    open();
    await waitFor(() => expect(document.querySelector('[data-reach-pending]')).not.toBeNull());
    expect(await screen.findByText(/^Sara Lindqvist asked to switch this on/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve with passkey' }));
    expect(await screen.findByText(/^Approved\./)).toBeInTheDocument();
    expect(writes(sent)).toEqual([`${REACH}/requests/r1/approve`]);
  });

  it('draws a four-eyes refusal as its own state, not an error banner', async () => {
    server({ ...off, pending }, 'u-erik', (s) => (s.method === 'post' ? { status: 409, data: { code: 'four_eyes_violation', detail: 'Server words.' } } : undefined));
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Approve with passkey' }));
    const state = await screen.findByRole('alert');
    expect(within(state).getByRole('heading', { name: 'Someone else must approve this' })).toBeInTheDocument();
    expect(screen.queryByText('Server words.')).toBeNull();
    fireEvent.click(within(state).getByRole('button', { name: 'Back to Security' }));
    expect(await screen.findByRole('button', { name: 'Reject' })).toBeInTheDocument();
  });

  it('rejects as the second person', async () => {
    const sent = server({ ...off, pending }, 'u-erik', (s) => (s.method === 'post' && s.path.endsWith('/reject') ? { status: 200, data: { ...pending, status: 'rejected' } } : undefined));
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    expect(await screen.findByText(/^Rejected\./)).toBeInTheDocument();
    expect(writes(sent)).toEqual([`${REACH}/requests/r1/reject`]);
  });

  it('names who switched it on, and switches it off after a confirmation', async () => {
    const on = { enabled: true, changedAt: '2026-09-25T07:40:00Z', changedBy: { id: 'u-erik', name: 'Erik Holm' }, pending: null };
    const sent = server(on, 'u-erik', (s) => (s.method === 'post' && s.path === `${REACH}/off` ? { status: 200, data: off } : undefined));
    open();
    expect(await screen.findByText(/switched on by Erik Holm/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Switch off' }));
    const dialog = await screen.findByRole('dialog', { name: 'Switch off reading our register?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Switch off' }));
    expect(await screen.findByText('Switched off. Every entry now reads the shared library only.')).toBeInTheDocument();
    expect(writes(sent)).toEqual([`${REACH}/off`]);
  });

  it('is read-only without security.manage and reads nothing', async () => {
    const sent = server(off);
    open([]);
    expect(await screen.findByText('Whether our own agents may read our register is changed by a member holding security manage.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
    expect(sent.some((s) => s.path === REACH)).toBe(false);
  });

  it('says so when the state cannot load', async () => {
    server(off, 'u-erik', (s) => (s.path === REACH ? { status: 500 } : undefined));
    open();
    expect(await screen.findByText('Could not load whether our register can be read')).toBeInTheDocument();
  });
});
