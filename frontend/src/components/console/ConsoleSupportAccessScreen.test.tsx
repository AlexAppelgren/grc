import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ConsoleSupportAccessPage from '@/app/(console)/console/support-access/page';
import { ConsoleSupportAccessScreen } from '@/components/console/ConsoleSupportAccessScreen';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, tokenStore } from '@/shared/utils/api-client';

// Support access in the console (TEN-06, TEN-S6): the caller's own requests
// with their state, asking a bank, and entering an approved grant. Nobody at
// the bank is named, and entering swaps the console session for the support
// session and reads nothing more.

const nav = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
}));

const ME_PATH = '/api/v1/me';
const MINE_PATH = '/api/v1/console/support-access';
const TENANTS_PATH = '/api/v1/console/tenants';

const platformAdmin = {
  user: { id: 'u11', email: 'platform@bleqq.test', name: 'Per Ström', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['tenants.manage', 'support_access.grant'],
  platformRoles: [{ key: 'platform_admin', kind: null, label: 'Platform administrator' }],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

function grant(id: string, state: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    tenantId: 't1',
    tenantName: 'Example Bank AB',
    state,
    purpose: 'Two changes show twice on Watch.',
    ticketRef: '',
    hours: 2,
    requestedAt: '2026-09-25T07:00:00Z',
    decidedAt: null,
    endsAt: null,
    ...extra,
  };
}

const active = grant('g-active', 'active', { ticketRef: 'SUP-2287', decidedAt: '2026-09-25T08:30:00Z', endsAt: '2026-09-25T10:30:00Z' });
const pending = grant('g-pending', 'pending', { tenantId: 't2', tenantName: 'Nordkyst Sparebank' });

function server(mine: Answer, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'console-token' } };
    if (sent.path === ME_PATH) return { status: 200, data: platformAdmin };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === MINE_PATH && sent.method === 'get') return mine;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

beforeEach(() => {
  resetApiForTests();
  nav.replace.mockReset();
});

describe('the console support access screen', () => {
  it("lists the caller's own grants by bank and state, with Enter only on a live one", async () => {
    server({ status: 200, data: { items: [pending, active], total: 2 } });
    renderIn(<ConsoleSupportAccessScreen />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Support access' })).toBeInTheDocument();
    const rows = await waitFor(() => {
      const found = [...document.querySelectorAll<HTMLElement>('[data-grant-id]')];
      expect(found).toHaveLength(2);
      return found;
    });
    expect(rows.map((row) => row.getAttribute('data-grant-state'))).toEqual(['pending', 'active']);
    const [waiting, live] = rows as [HTMLElement, HTMLElement];
    expect(within(waiting).getByText('Waiting for approval')).toHaveAttribute('data-pill', 'warning');
    expect(within(waiting).getByText('Nordkyst Sparebank')).toBeInTheDocument();
    expect(within(waiting).getByText('2 hours, starting when they approve')).toBeInTheDocument();
    expect(within(waiting).queryByRole('button', { name: 'Enter' })).toBeNull();
    expect(within(live).getByText('Active')).toHaveAttribute('data-pill', 'notice');
    expect(within(live).getByText('SUP-2287')).toBeInTheDocument();
    expect(within(live).getByRole('button', { name: 'Enter' })).toBeEnabled();
  });

  it('asks a bank with the purpose, the ticket and the window, and says who was told', async () => {
    const sent = server({ status: 200, data: { items: [], total: 0 } }, (s) => {
      if (s.path === TENANTS_PATH) {
        const bank = { id: 't2', name: 'Nordkyst Sparebank', slug: 'nordkyst', status: 'active', defaultLanguage: null, createdAt: '2026-09-17T08:00:00Z' };
        return { status: 200, data: { items: [bank], total: 1 } };
      }
      if (s.path === `${TENANTS_PATH}/t2/support-access`) return { status: 201, data: pending };
      return undefined;
    });
    renderIn(<ConsoleSupportAccessScreen />);
    expect(await screen.findByText('You have not asked for access')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ask for access' }));
    const form = await screen.findByRole('dialog', { name: 'Ask for access' });

    fireEvent.click(within(form).getByRole('button', { name: 'Ask for access' }));
    expect(await within(form).findByText('Choose the bank you need to read.')).toBeInTheDocument();
    await within(form).findByRole('option', { name: 'Nordkyst Sparebank' });
    fireEvent.change(within(form).getByLabelText('Bank'), { target: { value: 't2' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Ask for access' }));
    expect(await within(form).findByText('Say why you need access.')).toBeInTheDocument();
    expect(sent.some((s) => s.method === 'post' && s.path.endsWith('/support-access'))).toBe(false);

    fireEvent.change(within(form).getByLabelText('Purpose'), { target: { value: '  Their weekly briefing stopped arriving.  ' } });
    fireEvent.change(within(form).getByLabelText('Ticket'), { target: { value: 'SUP-2291' } });
    fireEvent.change(within(form).getByLabelText('How long, in hours'), { target: { value: '3' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Ask for access' }));
    expect(await screen.findByText("Asked. Nordkyst Sparebank's administrators have been emailed.")).toBeInTheDocument();
    const posted = sent.find((s) => s.method === 'post' && s.path === `${TENANTS_PATH}/t2/support-access`);
    expect(posted?.body).toEqual({ purpose: 'Their weekly briefing stopped arriving.', ticketRef: 'SUP-2291', hours: 3 });
  });

  it("renders the server's refusal of a window that is too long", async () => {
    server({ status: 200, data: { items: [], total: 0 } }, (s) => {
      if (s.path === TENANTS_PATH) return { status: 200, data: { items: [{ id: 't1', name: 'Example Bank AB', slug: 'x', status: 'active', defaultLanguage: null, createdAt: '2026-09-17T08:00:00Z' }], total: 1 } };
      if (s.path.endsWith('/support-access') && s.method === 'post') return { status: 422, data: { code: 'validation_error', detail: 'Ask for at most 4 hours.', status: 422 } };
      return undefined;
    });
    renderIn(<ConsoleSupportAccessScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ask for access' }));
    const form = await screen.findByRole('dialog', { name: 'Ask for access' });
    await within(form).findByRole('option', { name: 'Example Bank AB' });
    fireEvent.change(within(form).getByLabelText('Bank'), { target: { value: 't1' } });
    fireEvent.change(within(form).getByLabelText('Purpose'), { target: { value: 'A roadmap item shows the wrong deadline.' } });
    fireEvent.change(within(form).getByLabelText('How long, in hours'), { target: { value: '6' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Ask for access' }));
    expect(await within(form).findByRole('alert')).toHaveTextContent('Ask for at most 4 hours.');
  });

  it('enters a live grant, holds the support session, and reads nothing more; Leave signs out', async () => {
    const sent = server({ status: 200, data: { items: [active], total: 1 } }, (s) => {
      if (s.path === `${MINE_PATH}/g-active/enter`) return { status: 200, data: { accessToken: 'support-token', sessionKind: 'support', expiresIn: 600 } };
      if (s.path === '/api/v1/auth/sign-out') return { status: 204, data: null };
      return undefined;
    });
    renderIn(<ConsoleSupportAccessScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Enter' }));
    const banner = await screen.findByText('Support access to Example Bank AB.');
    expect(banner.closest('[data-support-banner]')).not.toBeNull();
    expect(tokenStore.get()).toBe('support-token');
    const reads = sent.filter((s) => s.method === 'get' && s.path === MINE_PATH).length;

    fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
    await waitFor(() => expect(nav.replace).toHaveBeenCalled());
    expect(sent.some((s) => s.method === 'post' && s.path === '/api/v1/auth/sign-out')).toBe(true);
    expect(sent.filter((s) => s.method === 'get' && s.path === MINE_PATH)).toHaveLength(reads);
  });

  it('says nothing opened when the passkey prompt is cancelled', async () => {
    server({ status: 200, data: { items: [active], total: 1 } }, (s) =>
      s.path === `${MINE_PATH}/g-active/enter` ? { status: 403, data: { code: 'step_up_required', detail: 'A passkey is needed.', status: 403 } } : undefined,
    );
    renderIn(<ConsoleSupportAccessScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Enter' }));
    expect(await screen.findByText('Nothing opened. Entering needs your passkey.')).toBeInTheDocument();
    expect(tokenStore.get()).toBe('console-token');
  });

  it('shows the loading, empty and error states', async () => {
    server({ status: 500, data: { code: 'server_error', detail: 'x', status: 500 } });
    renderIn(<ConsoleSupportAccessScreen />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(await screen.findByText('Could not load your support access')).toBeInTheDocument();
  });

  it('is gated on support_access.grant', async () => {
    server({ status: 200, data: { items: [], total: 0 } });
    renderIn(
      <PermissionsProvider permissions={['tenants.manage']}>
        <ConsoleSupportAccessPage />
      </PermissionsProvider>,
    );
    expect(await screen.findByText('This page is not available to you')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 1, name: 'Support access' })).toBeNull();
  });
});
