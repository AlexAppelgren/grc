import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { TeamsSection } from '@/components/admin/TeamsSection';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// Teams (TEN-03, TEN-S8): each team with its department and member count, a
// retired one dimmed; Add and Rename write the bank's `team` list, a rename
// with the version the row was read at.

const TEAM_LIST = '/api/v1/vocab/team';

const retail = { id: 'retail', kind: 'business_area', name: 'Retail Banking', parentId: null, orgNumber: '', lei: '', countryCode: '', entityTerm: null, head: null, active: true, version: 1 };
const team = { key: 'retail_compliance', label: 'Retail compliance', email: '', active: true, memberCount: 4, orgUnitId: 'retail' };
const old = { key: 'old_desk', label: 'Old desk', email: '', active: false, memberCount: 0, orgUnitId: null };
const row = { key: 'retail_compliance', kind: null, label: 'Retail compliance', labels: { en: 'Retail compliance', sv: 'Compliance privatmarknad' }, usageNote: '', sortOrder: 1, active: true, isSystem: false, isDefault: false, usageCount: 0, extra: {}, version: 7 };

function server(write?: (sent: Sent) => { status: number; data?: unknown }): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === '/api/v1/tenant/teams') return { status: 200, data: { items: [team, old], total: 2 } };
    if (sent.path === '/api/v1/tenant/org-units') return { status: 200, data: { items: [retail], total: 1 } };
    if (sent.method === 'get' && sent.path === TEAM_LIST) return { status: 200, data: { items: [row], total: 1 } };
    if (sent.method !== 'get' && write !== undefined) return write(sent);
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

async function renderSection(permissions: string[]): Promise<void> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <TeamsSection />
      </PermissionsProvider>
    </Query>,
  );
  await screen.findByText('Retail compliance');
}

beforeEach(() => {
  resetApiForTests();
});

describe('teams', () => {
  it('lists each team with its department and members, and dims a retired one', async () => {
    server();
    await renderSection(['vocab.manage']);
    const line = screen.getByText('Retail compliance').closest('[data-team]') as HTMLElement;
    await within(line).findByText('Retail Banking');
    expect(within(line).getByText('4 members')).toBeInTheDocument();
    const retired = screen.getByText('Old desk').closest('[data-team]') as HTMLElement;
    expect(retired).toHaveClass('opacity-60');
    expect(within(retired).getByText('Retired')).toBeInTheDocument();
  });

  it('shows no Rename or Add without vocab.manage', async () => {
    server();
    await renderSection([]);
    expect(screen.queryByRole('button', { name: /^Rename/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a team' })).not.toBeInTheDocument();
  });

  it('adds a team to the bank team list, and asks for a name first', async () => {
    const sent = server(() => ({ status: 201, data: row }));
    await renderSection(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Add a team' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add a team' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText('Give the team a name.')).toBeInTheDocument();
    expect(sent.some((s) => s.method === 'post' && s.path === TEAM_LIST)).toBe(false);
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: ' Savings compliance ' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'post' && s.path === TEAM_LIST)).toMatchObject({ path: TEAM_LIST, body: { labels: { en: 'Savings compliance' } } }));
  });

  it('renames a team with both its labels and the version it was read at', async () => {
    const sent = server(() => ({ status: 200, data: row }));
    await renderSection(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Rename Retail compliance' }));
    const dialog = await screen.findByRole('dialog', { name: 'Rename Retail compliance' });
    await waitFor(() => expect(within(dialog).getByLabelText('Name in Swedish')).toHaveValue('Compliance privatmarknad'));
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Retail and savings compliance' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(sent.some((s) => s.method === 'patch')).toBe(true));
    expect(sent.find((s) => s.method === 'patch')).toMatchObject({
      path: `${TEAM_LIST}/retail_compliance`,
      body: { labels: { en: 'Retail and savings compliance', sv: 'Compliance privatmarknad' } },
    });
  });
});
