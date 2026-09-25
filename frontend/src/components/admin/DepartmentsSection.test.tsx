import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { DepartmentsSection } from '@/components/admin/DepartmentsSection';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// Departments (TEN-02, TEN-S8): the business areas, units and functions with
// their head, the unit they sit in and their teams; legal entities are not
// departments. Add and Edit only for vocab.manage, and a head from another
// bank is placed on the head field by its code.

const UNITS = '/api/v1/tenant/org-units';

const unit = { parentId: null, orgNumber: '', lei: '', countryCode: '', entityTerm: null, head: null, active: true, version: 3 };
const bank = { ...unit, id: 'bank', kind: 'legal_entity', name: 'Example Bank AB' };
const retail = { ...unit, id: 'retail', kind: 'business_area', name: 'Retail Banking', parentId: 'bank', head: { id: 'u-karin', name: 'Karin Ek' } };
const risk = { ...unit, id: 'risk', kind: 'function', name: 'Risk control' };
const team = { key: 'retail_compliance', label: 'Retail compliance', email: '', active: true, memberCount: 4, orgUnitId: 'retail' };
const cards = { ...team, key: 'cards', label: 'Cards' };
const people = [
  { id: 'u-karin', name: 'Karin Ek' },
  { id: 'u-sara', name: 'Sara Lindqvist' },
];

function server(write?: (sent: Sent) => { status: number; data?: unknown }): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.method === 'get' && sent.path === UNITS) return { status: 200, data: { items: [bank, retail, risk], total: 3 } };
    if (sent.path === '/api/v1/tenant/teams') return { status: 200, data: { items: [team, cards], total: 2 } };
    if (sent.path === '/api/v1/reference/people') return { status: 200, data: people };
    if (sent.method !== 'get' && write !== undefined) return write(sent);
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

async function renderSection(permissions: string[]): Promise<void> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <DepartmentsSection />
      </PermissionsProvider>
    </Query>,
  );
  await screen.findByText('Retail Banking');
}

beforeEach(() => {
  resetApiForTests();
});

describe('departments', () => {
  it('lists each department with its kind, parent, head and teams, and no legal entity', async () => {
    server();
    await renderSection(['vocab.manage']);
    const row = screen.getByText('Retail Banking').closest('[data-department]') as HTMLElement;
    expect(within(row).getByText('Business area')).toBeInTheDocument();
    expect(within(row).getByText('In Example Bank AB')).toBeInTheDocument();
    expect(within(row).getByText('Head: Karin Ek')).toBeInTheDocument();
    await within(row).findByText('2 teams');
    const other = screen.getByText('Risk control').closest('[data-department]') as HTMLElement;
    expect(within(other).getByText('No head yet')).toBeInTheDocument();
    expect(within(other).getByText('0 teams')).toBeInTheDocument();
    expect(screen.queryByText('Example Bank AB', { selector: 'h3' })).not.toBeInTheDocument();
  });

  it('shows no Edit or Add without vocab.manage', async () => {
    server();
    await renderSection([]);
    expect(screen.queryByRole('button', { name: /^Edit/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a department' })).not.toBeInTheDocument();
  });

  it('adds a department with its kind, parent and head', async () => {
    const sent = server((s) => ({ status: 201, data: { ...unit, id: 'new', ...(s.body as object) } }));
    await renderSection(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Add a department' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add a department' });
    fireEvent.change(within(dialog).getByLabelText('Kind'), { target: { value: 'business_unit' } });
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Savings' } });
    fireEvent.change(within(dialog).getByLabelText('Sits under'), { target: { value: 'retail' } });
    await within(dialog).findByRole('option', { name: 'Sara Lindqvist' });
    fireEvent.change(within(dialog).getByLabelText('Head'), { target: { value: 'u-sara' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(sent.some((s) => s.method === 'post' && s.path === UNITS)).toBe(true));
    expect(sent.find((s) => s.method === 'post' && s.path === UNITS)?.body).toEqual({
      kind: 'business_unit',
      name: 'Savings',
      parentId: 'retail',
      headUserId: 'u-sara',
      orgNumber: '',
      lei: '',
      countryCode: '',
      entityTerm: null,
    });
  });

  it('sends only what changed, and places a head from another bank on the head field', async () => {
    const sent = server(() => ({ status: 422, data: { code: 'unknown_member', detail: 'Choose an active member of this bank.' } }));
    await renderSection(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Edit Retail Banking' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Retail Banking' });
    await within(dialog).findByRole('option', { name: 'Sara Lindqvist' });
    fireEvent.change(within(dialog).getByLabelText('Head'), { target: { value: 'u-sara' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await within(dialog).findByText('Choose an active member of this bank.');
    expect(sent.find((s) => s.method === 'patch')?.body).toEqual({ headUserId: 'u-sara' });
  });
});
