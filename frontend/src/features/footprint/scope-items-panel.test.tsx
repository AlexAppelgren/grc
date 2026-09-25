import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { FootprintScreen } from '@/components/admin/FootprintScreen';
import type { Me } from '@/features/identity/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

// The scope-item panel of /admin/footprint (design/screens/admin-footprint.html, states
// 21 to 27; OWN-01, FP-02, D-89): regulations we research ourselves, each with its research
// status, added and removed through the same request and second person as a term.

const ME = '/api/v1/me';
const FOOTPRINT = '/api/v1/tenant/footprint';
const REQUESTS = `${FOOTPRINT}/requests`;
const TERMS = '/api/v1/taxonomy/terms';
const JURISDICTIONS = '/api/v1/reference/jurisdictions';

const SARA = { id: 'u1', name: 'Sara Lindqvist' };
const MARIA = { id: 'u2', name: 'Maria Ek' };
const OFFICER = ['footprint.request', 'footprint.approve'];

function meOf(user: { id: string; name: string }, permissions: readonly string[]): Me {
  return {
    user: { id: user.id, email: `${user.id}@example.test`, name: user.name, locale: 'en' },
    tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm' },
    roles: [],
    permissions: [...permissions],
    platformRoles: [],
    enrolmentPending: false,
    passkeyCount: 1,
    stepUpValidUntil: null,
    counts: { triage: 0, proposals: 0, assignedToMe: 0 },
    lastVisitAt: null,
  } as Me;
}

const DIMENSIONS = [{ dimension: { key: 'service_type', kind: null, label: 'Service' }, restrictsFootprint: true, allSelected: false, terms: [{ key: 'advice', kind: null, label: 'Advice' }] }];
const term = (dimension: string, key: string, label: string) => ({ id: `${dimension}:${key}`, dimension: { key: dimension, kind: null, label: dimension }, key, kind: null, label, usageNote: '', sortOrder: 0, active: true, mirrored: false });
const TAXONOMY = { items: [term('service_type', 'advice', 'Advice'), term('regime', 'payments', 'Payments'), term('regime', 'banking', 'Banking')], total: 3 };
const REFERENCE = [
  { key: 'se', kind: 'country', label: 'Sweden', parentKey: 'eu' },
  { key: 'dk', kind: 'country', label: 'Denmark', parentKey: 'eu' },
];

function scopeItem(key: string, name: string, overrides: Record<string, unknown> = {}) {
  return {
    id: `id-${key}`,
    key,
    name,
    description: '',
    jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
    regimeTerm: { key: 'payments', kind: null, label: 'Payments', dimension: 'regime' },
    officialReference: '',
    sourceUrl: `https://example.se/${key}`,
    status: 'in_scope',
    research: 'waiting_for_agent',
    ...overrides,
  };
}

const BETAL = scopeItem('betaltjanstlagen', 'Betaltjänstlagen', { officialReference: 'SFS 2010:751', research: 'researched' });
const KONTANT = scopeItem('kontanthantering', 'Kontanthantering');

function waiting(changes: Record<string, unknown>, requestedBy = SARA) {
  return {
    id: 'r1',
    status: 'pending',
    requestedAt: '2026-09-18T12:00:00Z',
    requestedBy,
    adds: [],
    removes: [],
    scopeItemAdds: [],
    scopeItemRemoves: [],
    preview: { obligations: { hidden: 0, revealed: 0, available: true }, cases: { hidden: 0, revealed: 0, available: true } },
    decidedBy: null,
    decidedAt: null,
    decisionNote: '',
    version: 1,
    ...changes,
  };
}

type Server = { pending: unknown; items: unknown[] };

function serve(me: Me, items: unknown[], pending: unknown = null, write: (sent: Sent, server: Server) => Answer = () => ({ status: 500 })): Sent[] {
  const server: Server = { pending, items };
  return installAdapter((s) => {
    if (s.path === ME) return { status: 200, data: me };
    if (s.path === FOOTPRINT) return { status: 200, data: { dimensions: DIMENSIONS, pendingRequest: server.pending, markets: [], scopeItems: server.items } };
    if (s.path === TERMS) return { status: 200, data: TAXONOMY };
    if (s.path === JURISDICTIONS) return { status: 200, data: REFERENCE };
    if (s.method === 'get' && s.path === REQUESTS) return { status: 200, data: { items: [], total: 0 } };
    return write(s, server);
  });
}

function open(me: Me): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <PermissionsProvider permissions={me.permissions}>
        <LocaleProvider locale="en">
          <FootprintScreen />
        </LocaleProvider>
      </PermissionsProvider>
    </Query>,
  );
}

const panel = () => document.querySelector<HTMLElement>('[data-scope-items]')!;
const row = (key: string) => panel().querySelector<HTMLElement>(`[data-scope-item="${key}"]`)!;
const statusLine = () => document.querySelector<HTMLElement>('[data-status-line]')!;
const sends = (sent: Sent[]) => sent.filter((s) => s.method === 'post' && s.path === REQUESTS && s.params === null);

function findBanner(): Promise<HTMLElement> {
  return waitFor(() => {
    const banner = document.querySelector<HTMLElement>('[data-pending-request]');
    if (banner === null) throw new Error('no banner yet');
    return banner;
  });
}

async function findPanel(): Promise<HTMLElement> {
  await screen.findByRole('heading', { name: 'Regulations we research ourselves' });
  return panel();
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
});

describe('scope items: reading', () => {
  it('lists each item by name with its facts, its address as an outside link and its research status', async () => {
    serve(meOf(SARA, OFFICER), [KONTANT, BETAL]);
    open(meOf(SARA, OFFICER));
    await findPanel();

    const keys = [...panel().querySelectorAll('[data-scope-item]')].map((li) => li.getAttribute('data-scope-item'));
    expect(keys).toEqual(['betaltjanstlagen', 'kontanthantering']);
    expect(within(row('betaltjanstlagen')).getByRole('heading', { name: 'Betaltjänstlagen' })).toBeVisible();
    expect(row('betaltjanstlagen')).toHaveTextContent('SwedenPaymentsSFS 2010:751');
    expect(row('kontanthantering')).toHaveTextContent('No official reference');
    const link = within(row('betaltjanstlagen')).getByRole('link', { name: 'https://example.se/betaltjanstlagen' });
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAttribute('target', '_blank');
    expect(within(row('betaltjanstlagen')).getByText('Researched').closest('[data-pill]')).toHaveAttribute('data-pill', 'positive');
    expect(within(row('kontanthantering')).getByText('Waiting for your agent').closest('[data-pill]')).toHaveAttribute('data-pill', 'warning');
    expect(within(panel()).getByRole('button', { name: 'Add a regulation' })).toBeVisible();
    expect(within(panel()).queryByRole('button', { name: /^Remove/ })).toBeNull();
  });

  it('renders an address that is not http or https as plain text, never a link', async () => {
    serve(meOf(SARA, OFFICER), [scopeItem('odd', 'Odd', { sourceUrl: 'javascript:alert(1)' })]);
    open(meOf(SARA, OFFICER));
    await findPanel();
    expect(row('odd')).toHaveTextContent('javascript:alert(1)');
    expect(within(row('odd')).queryByRole('link')).toBeNull();
  });

  it('reads the same for someone who can only approve, without Add or Remove', async () => {
    serve(meOf(MARIA, ['footprint.approve']), [BETAL]);
    open(meOf(MARIA, ['footprint.approve']));
    await findPanel();
    expect(within(row('betaltjanstlagen')).getByText('Researched')).toBeVisible();
    expect(within(panel()).queryByRole('button')).toBeNull();
  });

  it('says there are none yet and offers to add one', async () => {
    serve(meOf(SARA, OFFICER), []);
    open(meOf(SARA, OFFICER));
    await findPanel();
    expect(within(panel()).getByRole('heading', { name: 'No regulations of our own yet' })).toBeVisible();
    expect(within(panel()).getByRole('button', { name: 'Add a regulation' })).toBeVisible();
  });
});

describe('scope items: proposing', () => {
  it('adds a regulation through the request: the form, a preview that moves nothing, and the item in the body', async () => {
    const me = meOf(SARA, OFFICER);
    const sent = serve(me, [], null, (s, server) => {
      if (s.method === 'post' && s.path === REQUESTS) {
        server.pending = waiting({ scopeItemAdds: [scopeItem('betaltjanstlagen', 'Betaltjänstlagen', { id: 'n1', status: 'requested', research: null })] });
        return { status: 201, data: server.pending };
      }
      return { status: 500 };
    });
    open(me);
    await findPanel();
    fireEvent.click(within(panel()).getByRole('button', { name: 'Add a regulation' }));

    const name = await screen.findByLabelText('Name');
    await waitFor(() => expect(document.activeElement).toBe(name));
    expect(screen.queryByRole('button', { name: 'Propose a change' })).toBeNull();
    expect(within(panel()).queryByRole('button', { name: 'Add a regulation' })).toBeNull();
    fireEvent.change(name, { target: { value: 'Betaltjänstlagen' } });
    fireEvent.change(screen.getByLabelText('Regime'), { target: { value: 'banking' } });
    fireEvent.change(screen.getByLabelText('Official reference (optional)'), { target: { value: 'SFS 2010:751' } });
    fireEvent.change(screen.getByLabelText('Public address to research'), { target: { value: 'https://www.riksdagen.se/sfs-2010-751' } });

    const change = document.querySelector<HTMLElement>('[data-draft-preview]')!;
    expect(within(change).getByRole('heading', { name: 'Your change: Add the regulation Betaltjänstlagen' })).toBeVisible();
    expect(within(change).getAllByText('Nothing.')).toHaveLength(2);
    expect(within(change).getByText('Our agent starts researching it once someone else approves.')).toBeVisible();
    fireEvent.click(within(change).getByRole('button', { name: 'Request approval' }));

    await waitFor(() => expect(statusLine()).toHaveTextContent('Sent for approval.'));
    // Only the send reached the server: an item moves no count, so it is never dry-run.
    expect(sent.filter((s) => s.method === 'post')).toHaveLength(1);
    expect(sends(sent)[0]?.body).toEqual({
      adds: [],
      removes: [],
      scopeItemAdds: [{ name: 'Betaltjänstlagen', description: '', jurisdiction: 'se', regimeTerm: 'banking', officialReference: 'SFS 2010:751', sourceUrl: 'https://www.riksdagen.se/sfs-2010-751' }],
    });
    await waitFor(() => expect(row('betaltjanstlagen')).toHaveTextContent('Added when approved'));
    expect(within(row('betaltjanstlagen')).queryByText('Waiting for your agent')).toBeNull();
  });

  it("renders the server's refusal of an address under its input, from the problem's code", async () => {
    const me = meOf(SARA, OFFICER);
    serve(me, [], null, () => ({ status: 422, data: { code: 'source_not_public', detail: 'The address is not public.' } }));
    open(me);
    await findPanel();
    fireEvent.click(within(panel()).getByRole('button', { name: 'Add a regulation' }));
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Intranet rules' } });
    const address = screen.getByLabelText('Public address to research');
    fireEvent.change(address, { target: { value: 'https://intranet.bank.local/rules' } });
    fireEvent.click(screen.getByRole('button', { name: 'Request approval' }));

    expect(await screen.findByText('Use a public https address.')).toBeVisible();
    expect(address).toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByText('The address is not public.')).toBeNull();
    expect(statusLine()).toBeEmptyDOMElement();

    fireEvent.change(address, { target: { value: 'https://www.fi.se/rules' } });
    expect(screen.queryByText('Use a public https address.')).toBeNull();
    expect(address).toHaveAttribute('aria-invalid', 'false');
  });

  it('removes an item through the same draft, and Keep takes the removal back', async () => {
    const me = meOf(SARA, OFFICER);
    const sent = serve(me, [BETAL, KONTANT], null, (s, server) => {
      if (s.method === 'post' && s.path === REQUESTS) {
        server.pending = waiting({ scopeItemRemoves: [KONTANT] });
        return { status: 201, data: server.pending };
      }
      return { status: 500 };
    });
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Propose a change' }));

    fireEvent.click(within(row('betaltjanstlagen')).getByRole('button', { name: 'Remove Betaltjänstlagen' }));
    expect(row('betaltjanstlagen')).toHaveTextContent('Removed when approved');
    fireEvent.click(within(row('betaltjanstlagen')).getByRole('button', { name: 'Keep Betaltjänstlagen' }));
    expect(row('betaltjanstlagen')).not.toHaveTextContent('Removed when approved');
    fireEvent.click(within(row('kontanthantering')).getByRole('button', { name: 'Remove Kontanthantering' }));

    const change = document.querySelector<HTMLElement>('[data-draft-preview]')!;
    expect(within(change).getByRole('heading', { name: 'Your change: Remove the regulation Kontanthantering' })).toBeVisible();
    fireEvent.click(within(change).getByRole('button', { name: 'Request approval' }));
    await waitFor(() => expect(statusLine()).toHaveTextContent('Sent for approval.'));
    expect(sends(sent)[0]?.body).toEqual({ adds: [], removes: [], scopeItemRemoves: ['kontanthantering'] });
    await waitFor(() => expect(row('kontanthantering')).toHaveTextContent('Removed when approved'));
  });
});

describe('scope items: deciding', () => {
  it('approves an added item behind the passkey step-up and names it in the status line', async () => {
    const me = meOf(MARIA, ['footprint.approve']);
    const added = scopeItem('betaltjanstlagen', 'Betaltjänstlagen', { status: 'requested', research: null, description: 'Information duties.' });
    const sent = serve(me, [], waiting({ scopeItemAdds: [added] }), (s, server) => {
      if (s.path === `${REQUESTS}/r1/approve`) {
        server.pending = null;
        server.items = [{ ...added, status: 'in_scope', research: 'waiting_for_agent' }];
        return { status: 200, data: waiting({ status: 'approved', scopeItemAdds: [added], decidedBy: MARIA }) };
      }
      return { status: 500 };
    });
    open(me);

    const banner = await findBanner();
    expect(within(banner).getByText('Add the regulation Betaltjänstlagen')).toBeVisible();
    expect(row('betaltjanstlagen')).toHaveTextContent('Added when approved');
    expect(row('betaltjanstlagen')).toHaveTextContent('Information duties.');
    fireEvent.click(within(banner).getByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog', { name: 'Approve "Add the regulation Betaltjänstlagen"?' });
    expect(dialog).toHaveAccessibleDescription('Hides nothing and reveals nothing. Our agent starts researching it, and what it finds waits in our own records.');
    expect(dialog.querySelector('[data-notice="warn"]')).toBeNull();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve with passkey' }));
    await waitFor(() => expect(statusLine()).toHaveTextContent('Approved. Our agent will research Betaltjänstlagen.'));
    expect(sent.filter((s) => s.path === `${REQUESTS}/r1/approve`)).toHaveLength(1);
    await waitFor(() => expect(within(row('betaltjanstlagen')).getByText('Waiting for your agent')).toBeVisible());
  });

  it('says in the banner that a removal stops the research', async () => {
    serve(meOf(MARIA, ['footprint.approve']), [KONTANT], waiting({ scopeItemRemoves: [KONTANT] }));
    open(meOf(MARIA, ['footprint.approve']));
    const banner = await findBanner();
    expect(within(banner).getByText('Remove the regulation Kontanthantering')).toBeVisible();
    expect(banner).toHaveTextContent('Our agent stops researching it. What we already approved stays in our inventory.');
  });

  it("shows the four-eyes refusal from the server's code in the approve dialog", async () => {
    const me = meOf(MARIA, ['footprint.approve']);
    serve(me, [], waiting({ scopeItemAdds: [scopeItem('x', 'X', { status: 'requested', research: null })] }), () => ({ status: 409, data: { code: 'four_eyes_violation', detail: 'The requester cannot approve.' } }));
    open(me);
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve with passkey' }));
    expect(await within(dialog).findByText('You requested this change, so someone else has to approve it.')).toBeVisible();
    expect(within(dialog).getByRole('button', { name: 'Approve with passkey' })).toBeDisabled();
  });
});
