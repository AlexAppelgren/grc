import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MemberDetailScreen } from '@/components/admin/MemberDetailScreen';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH, setStepUpHandler } from '@/shared/utils/api-client';

// A member's teams and removal (TEN-03, TEN-05, TEN-S8, TEN-S5, TEN-S9): the
// teams are saved as one set with no step-up; Deactivate opens the removal,
// which shows what the member holds by kind, asks for an owner per kind, says
// what simply ends, sends nothing until the admin confirms, and renders the
// server's refusals from their codes.

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

const MEMBER = '/api/v1/tenant/members/u-gustav';
const gustav = {
  userId: 'u-gustav',
  name: 'Gustav Sjöberg',
  email: 'leaver@example-bank.test',
  title: 'Obligation owner, savings',
  roles: [{ key: 'owner', kind: null, label: 'Obligation owner' }],
  status: 'active',
  teams: ['cards'],
  lastSeenAt: null,
  passkeyCount: 1,
  activeSessions: 0,
};
const teams = [
  { key: 'retail_compliance', label: 'Retail compliance', email: '', active: true, memberCount: 4, orgUnitId: 'retail' },
  { key: 'cards', label: 'Cards', email: '', active: true, memberCount: 3, orgUnitId: null },
  { key: 'old_desk', label: 'Old desk', email: '', active: false, memberCount: 0, orgUnitId: null },
];
const retail = { id: 'retail', kind: 'business_area', name: 'Retail Banking', parentId: null, orgNumber: '', lei: '', countryCode: '', entityTerm: null, head: null, active: true, version: 1 };
const people = [
  { id: 'u-gustav', name: 'Gustav Sjöberg' },
  { id: 'u-sara', name: 'Sara Lindqvist' },
];
const openWork = {
  member: { id: 'u-gustav', name: 'Gustav Sjöberg' },
  items: [
    { kind: 'gap', count: 1 },
    { kind: 'register_entry', count: 3 },
    { kind: 'participation', count: 2 },
    { kind: 'team_membership', count: 1 },
  ],
  teams: ['cards'],
};
const stillOwns = {
  code: 'reassignment_required',
  detail: 'This member still holds work.',
  errors: [{ field: 'gap', count: 1, message: 'Needs a new owner or ends with the removal.' }],
};

function server(write: (sent: Sent) => { status: number; data?: unknown } = () => ({ status: 204 })): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === '/api/v1/tenant/members') return { status: 200, data: { items: [gustav], total: 1 } };
    if (sent.path === `${MEMBER}/sessions`) return { status: 200, data: [] };
    if (sent.path === `${MEMBER}/open-work`) return { status: 200, data: openWork };
    if (sent.path === '/api/v1/tenant/roles') return { status: 200, data: [] };
    if (sent.path === '/api/v1/tenant/teams') return { status: 200, data: { items: teams, total: teams.length } };
    if (sent.path === '/api/v1/tenant/org-units') return { status: 200, data: { items: [retail], total: 1 } };
    if (sent.path === '/api/v1/reference/people') return { status: 200, data: people };
    if (sent.method !== 'get') return write(sent);
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

async function renderScreen(): Promise<void> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <MemberDetailScreen userId="u-gustav" />
    </Query>,
  );
  await screen.findByRole('heading', { level: 1, name: 'Gustav Sjöberg' });
}

async function openRemoval(): Promise<HTMLElement> {
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }));
  const dialog = await screen.findByRole('dialog', { name: 'Deactivate Gustav Sjöberg' });
  await within(dialog).findByText('3 obligations');
  return dialog;
}

const writes = (sent: Sent[]) => sent.filter((s) => s.method !== 'get' && s.path !== REFRESH_PATH);

beforeEach(() => {
  resetApiForTests();
  push.mockReset();
  setStepUpHandler(() => Promise.resolve(true));
});

describe("a member's teams", () => {
  it('offers the active teams with their department, keeps no retired one, and saves the whole set', async () => {
    const sent = server((s) => ({ status: 200, data: { ...gustav, teams: (s.body as { teams: string[] }).teams } }));
    await renderScreen();
    const retailBox = await screen.findByLabelText(/Retail compliance/);
    expect(screen.getByText('Retail Banking')).toBeInTheDocument();
    expect(screen.getByLabelText(/Cards/)).toBeChecked();
    expect(screen.queryByLabelText(/Old desk/)).not.toBeInTheDocument();
    fireEvent.click(retailBox);
    fireEvent.click(screen.getByLabelText(/Cards/));
    fireEvent.click(screen.getByRole('button', { name: 'Save teams' }));
    expect(await screen.findByText('Teams saved.')).toBeInTheDocument();
    expect(writes(sent)).toEqual([expect.objectContaining({ method: 'put', path: `${MEMBER}/teams`, body: { teams: ['retail_compliance'] } })]);
  });
});

describe("a member's removal", () => {
  it('shows what the member holds by kind, what ends, and changes nothing until confirmed', async () => {
    const sent = server();
    await renderScreen();
    const dialog = await openRemoval();
    const kinds = within(dialog)
      .getAllByText(/obligations|gap/)
      .map((node) => node.textContent);
    expect(kinds).toEqual(['3 obligations', '1 gap']);
    expect(within(dialog).getByText('Takes part in 2 items. That ends; the items keep their other participants.')).toBeInTheDocument();
    expect(within(dialog).getByText('Teams: Cards. Gustav Sjöberg leaves it; what the team owns stays with the team.')).toBeInTheDocument();
    // The person being removed is never offered as their own successor.
    const owner = within(dialog).getByRole('combobox', { name: 'New owner of 3 obligations' });
    await within(owner).findByRole('option', { name: 'Sara Lindqvist' });
    expect(within(owner).queryByRole('option', { name: 'Gustav Sjöberg' })).not.toBeInTheDocument();
    expect(within(owner).queryByRole('option', { name: 'Old desk' })).not.toBeInTheDocument();
    fireEvent.change(owner, { target: { value: 'team:retail_compliance' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(writes(sent)).toEqual([]);
  });

  it('sends a person or a team per kind on confirm, then leaves for the member list', async () => {
    const sent = server();
    await renderScreen();
    const dialog = await openRemoval();
    await within(dialog).findAllByRole('option', { name: 'Sara Lindqvist' });
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'New owner of 3 obligations' }), { target: { value: 'user:u-sara' } });
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'New owner of 1 gap' }), { target: { value: 'team:cards' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/admin/members'));
    expect(writes(sent)).toEqual([
      expect.objectContaining({
        method: 'post',
        path: `${MEMBER}/remove`,
        body: { owners: [{ kind: 'register_entry', userId: 'u-sara' }, { kind: 'gap', teamKey: 'cards' }] },
      }),
    ]);
  });

  it('renders reassignment_required from its code and counts, and marks the kind still owned', async () => {
    server(() => ({ status: 422, data: stillOwns }));
    await renderScreen();
    const dialog = await openRemoval();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }));
    expect(await within(dialog).findByText('Gustav Sjöberg still owns open work: 1 gap. Choose a new owner for each kind.')).toBeInTheDocument();
    expect(within(dialog).getByRole('combobox', { name: 'New owner of 1 gap' })).toHaveAttribute('aria-invalid', 'true');
    expect(within(dialog).getByRole('combobox', { name: 'New owner of 3 obligations' })).toHaveAttribute('aria-invalid', 'false');
    expect(push).not.toHaveBeenCalled();
  });

  it('says nothing changed when the passkey prompt is cancelled', async () => {
    const sent = server(() => ({ status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } }));
    setStepUpHandler(() => Promise.resolve(false));
    await renderScreen();
    const dialog = await openRemoval();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }));
    expect(await within(dialog).findByText('Nothing changed. Deactivating needs your passkey.')).toBeInTheDocument();
    expect(writes(sent)).toHaveLength(1);
  });
});
