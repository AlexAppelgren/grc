import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { ObligationParticipantsPanel } from './ObligationParticipantsPanel';

// "Participants" (COL-04): the owners read-only above the list, who added each
// row, Leave on your own row whatever your role, Remove and Add only with
// register.edit, one picker over people and teams, refusals by their code.

const EDITOR = ['register.read', 'register.edit'];
const READER = ['register.read'];
const ANNA = { id: 'u-anna', name: 'Anna Nilsson' };
const ERIK = { id: 'u-erik', name: 'Erik Holm' };

const erik = { id: 'p-erik', person: ERIK, team: null, addedBy: ANNA, addedAt: '2026-09-19T08:00:00Z' };
const legal = { id: 'p-legal', person: null, team: { key: 'legal', kind: null, label: 'Legal' }, addedBy: ANNA, addedAt: '2026-09-18T08:00:00Z' };

interface Server {
  meId: string;
  items?: unknown[];
  entry?: Answer;
  write?: (sent: Sent) => Answer;
}

function serve({ meId, items = [erik, legal], entry, write = () => ({ status: 204 }) }: Server) {
  return installAdapter((s) => {
    if (s.path === '/api/v1/me') return { status: 200, data: { user: { id: meId, name: 'Me', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false } };
    if (s.path.endsWith('/register')) return entry ?? { status: 200, data: { firstLineOwner: ANNA, complianceContact: { id: 'u-sara', name: 'Sara Lindqvist' } } };
    if (s.path === '/api/v1/reference/people') return { status: 200, data: [ERIK, ANNA] };
    if (s.path === '/api/v1/tenant/teams') return { status: 200, data: { items: [{ key: 'legal', label: 'Legal', active: true, email: '', memberCount: 2, orgUnitId: null }], total: 1 } };
    if (s.method === 'get') return { status: 200, data: { items, total: items.length } };
    return write(s);
  });
}

function renderPanel(permissions: string[]) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <ObligationParticipantsPanel obligationId="ob-1" />
        </PermissionsProvider>
      </LocaleProvider>
    </Wrapper>,
  );
}

function row(id: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-participant-id="${id}"]`);
  if (found === null) throw new Error(`no row ${id}`);
  return found;
}

describe('ObligationParticipantsPanel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('shows the owners read-only, who added each row, and Leave on the reader’s own row only', async () => {
    const sent = serve({ meId: 'u-erik' });
    renderPanel(READER);
    expect(await screen.findByText('Sara Lindqvist')).toBeTruthy();
    expect(screen.getByText('First-line owner')).toBeTruthy();
    await screen.findByText('Erik Holm');
    expect(within(row('p-erik')).getByText('You')).toBeTruthy();
    expect(within(row('p-erik')).getByText(/Added .* by Anna Nilsson/)).toBeTruthy();
    expect(within(row('p-legal')).getByText('Team')).toBeTruthy();
    expect(within(row('p-legal')).queryByRole('button')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a participant' })).toBeNull();
    fireEvent.click(within(row('p-erik')).getByRole('button', { name: 'Leave' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'delete')?.path).toBe('/api/v1/obligations/ob-1/participants/p-erik'));
  });

  it('stands on its own when the register entry cannot be read, and says when nobody takes part', async () => {
    serve({ meId: 'u-anna', items: [], entry: { status: 501, data: { code: 'not_built' } } });
    renderPanel(EDITOR);
    expect(await screen.findByText('Nobody takes part yet.')).toBeTruthy();
    expect(document.querySelector('[data-participant-owners]')).toBeNull();
  });

  it('lets an editor remove another row and add a team from the one picker', async () => {
    const sent = serve({ meId: 'u-anna', write: (s) => (s.method === 'post' ? { status: 201, data: legal } : { status: 204 }) });
    renderPanel(EDITOR);
    fireEvent.click(await within(await waitFor(() => row('p-legal'))).findByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'delete')?.path).toBe('/api/v1/obligations/ob-1/participants/p-legal'));
    fireEvent.click(screen.getByRole('button', { name: 'Add a participant' }));
    fireEvent.change(screen.getByRole('searchbox', { name: 'Person or team' }), { target: { value: 'leg' } });
    fireEvent.click(await screen.findByRole('radio', { name: /Legal/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'post')?.body).toEqual({ teamKey: 'legal' }));
    expect(sent.find((s) => s.path === '/api/v1/reference/people')?.params).toEqual({ permission: 'register.read' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('renders a refused add from its code, naming the person', async () => {
    const sent = serve({ meId: 'u-anna', write: () => ({ status: 409, data: { code: 'already_participant', detail: 'server words' } }) });
    renderPanel(EDITOR);
    fireEvent.click(await screen.findByRole('button', { name: 'Add a participant' }));
    fireEvent.click(await screen.findByRole('radio', { name: /Erik Holm/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(await screen.findByText('Erik Holm already takes part in this obligation.')).toBeTruthy();
    expect(sent.find((s) => s.method === 'post')?.body).toEqual({ userId: 'u-erik' });
  });
});
