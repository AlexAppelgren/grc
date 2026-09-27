import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { CaseWorkflow } from '@/features/cases/types';
import type { ChangeDetail } from '@/features/watch/api';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { CaseParticipantsPanel } from './CaseParticipantsPanel';

// "Participants" on the case (COL-04): the owner read-only above the list,
// who added each row, Leave on your own row whatever your role, Remove and
// Add only with cases.contribute (never register.edit), one picker over the
// people who can open cases and the teams, refusals in place by their code.

const CONTRIBUTOR = ['cases.read', 'cases.contribute'];
const READER = ['cases.read', 'register.read', 'register.edit'];
const SARA = { id: 'u-sara', name: 'Sara Lindqvist' };
const ERIK = { id: 'u-erik', name: 'Erik Holm' };
const ANNA = { id: 'u-anna', name: 'Anna Nilsson' };

const CHANGE = { id: 'c-1' } as unknown as ChangeDetail;
const erik = { id: 'p-erik', person: ERIK, team: null, addedBy: SARA, addedAt: '2026-09-18T08:00:00Z' };
const legal = { id: 'p-legal', person: null, team: { key: 'legal', kind: null, label: 'Legal' }, addedBy: SARA, addedAt: '2026-09-17T08:00:00Z' };

function workflowOf(overrides: Partial<CaseWorkflow> = {}): CaseWorkflow {
  return { id: 'case-1', category: 'assessing', owner: SARA, version: 3, ...overrides } as CaseWorkflow;
}

function serve({ meId, items = [erik, legal], write = () => ({ status: 204 }) }: { meId: string; items?: unknown[]; write?: (sent: Sent) => Answer }) {
  return installAdapter((s) => {
    if (s.path === '/api/v1/me') return { status: 200, data: { user: { id: meId, name: 'Me', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false } };
    if (s.path === '/api/v1/reference/people') return { status: 200, data: [ERIK, ANNA] };
    if (s.path === '/api/v1/tenant/teams') return { status: 200, data: { items: [{ key: 'legal', label: 'Legal', active: true, email: '', memberCount: 2, orgUnitId: null }], total: 1 } };
    if (s.method === 'get') return { status: 200, data: { items, total: items.length } };
    return write(s);
  });
}

function renderPanel(permissions: string[], workflow = workflowOf()) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <CaseParticipantsPanel change={CHANGE} workflow={workflow} />
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

describe('CaseParticipantsPanel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('shows the owner read-only, who added each row, and to a reader only Leave on their own row', async () => {
    const sent = serve({ meId: 'u-erik' });
    renderPanel(READER);
    expect(screen.getByText('Owner')).toBeTruthy();
    expect(screen.getByText('Sara Lindqvist')).toBeTruthy();
    await screen.findByText('Erik Holm');
    expect(within(row('p-erik')).getByText('You')).toBeTruthy();
    expect(within(row('p-erik')).getByText(/Added .* by Sara Lindqvist/)).toBeTruthy();
    expect(within(row('p-legal')).getByText('Team')).toBeTruthy();
    // register.edit reaches nothing on a case.
    expect(within(row('p-legal')).queryByRole('button')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a participant' })).toBeNull();
    fireEvent.click(within(row('p-erik')).getByRole('button', { name: 'Leave' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'delete')?.path).toBe('/api/v1/changes/c-1/participants/p-erik'));
  });

  it('names no owner before triage, and says when nobody takes part', async () => {
    serve({ meId: 'u-anna', items: [] });
    renderPanel(CONTRIBUTOR, workflowOf({ category: 'new', owner: null }));
    expect(await screen.findByText('Nobody takes part yet.')).toBeTruthy();
    expect(document.querySelector('[data-participant-owners]')).toBeNull();
  });

  it('lets a contributor remove another row and add a person who can open cases', async () => {
    const sent = serve({ meId: 'u-anna', write: (s) => (s.method === 'post' ? { status: 201, data: erik } : { status: 204 }) });
    renderPanel(CONTRIBUTOR);
    fireEvent.click(await within(await waitFor(() => row('p-legal'))).findByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'delete')?.path).toBe('/api/v1/changes/c-1/participants/p-legal'));
    fireEvent.click(screen.getByRole('button', { name: 'Add a participant' }));
    fireEvent.click(await screen.findByRole('radio', { name: /Anna Nilsson/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'post')?.body).toEqual({ userId: 'u-anna' }));
    expect(sent.find((s) => s.method === 'post')?.path).toBe('/api/v1/changes/c-1/participants');
    expect(sent.find((s) => s.path === '/api/v1/reference/people')?.params).toEqual({ permission: 'cases.read' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('shows a closed case’s refusal in place, and keeps the dialog open', async () => {
    serve({ meId: 'u-anna', write: () => ({ status: 409, data: { code: 'invalid_transition', detail: 'server words' } }) });
    renderPanel(CONTRIBUTOR, workflowOf({ category: 'closed' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Add a participant' }));
    fireEvent.click(await screen.findByRole('radio', { name: /Erik Holm/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    const dialog = screen.getByRole('dialog', { name: 'Add a participant' });
    expect(await within(dialog).findByText('This case is closed, so its participants no longer change.')).toBeTruthy();
  });

  it('names the person a duplicate add refers to', async () => {
    serve({ meId: 'u-anna', write: () => ({ status: 409, data: { code: 'already_participant', detail: 'server words' } }) });
    renderPanel(CONTRIBUTOR);
    fireEvent.click(await screen.findByRole('button', { name: 'Add a participant' }));
    fireEvent.click(await screen.findByRole('radio', { name: /Erik Holm/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(await screen.findByText('Erik Holm already takes part in this case.')).toBeTruthy();
  });
});
