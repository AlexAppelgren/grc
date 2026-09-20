import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import ConsoleTenantsPage from '@/app/(console)/console/tenants/page';
import { TenantsScreen } from '@/components/console/TenantsScreen';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// Tenants in the platform console (ADM-02, ADM-S6): the list of banks, the
// four states, and creating one with its first administrator invited. The
// screen reads the tenant rows and the language reference and nothing else,
// so platform staff gain no way into a bank's own data.

const ME_PATH = '/api/v1/me';
const TENANTS_PATH = '/api/v1/console/tenants';
const LANGUAGES_PATH = '/api/v1/reference/languages';

const LANGUAGES = [
  { key: 'en', kind: null, label: 'English' },
  { key: 'sv', kind: null, label: 'Swedish' },
];

const tenantA = { id: 't1', name: 'Example Bank AB', slug: 'example-bank', status: 'active', defaultLanguage: LANGUAGES[1], createdAt: '2026-09-17T08:00:00Z' };
const tenantB = { id: 't2', name: 'Second Bank A/S', slug: 'second-bank', status: 'deactivated', defaultLanguage: null, createdAt: '2026-09-18T08:00:00Z' };

const platformAdmin = {
  user: { id: 'u11', email: 'platform@bleqq.test', name: 'Per Ström', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['tenants.manage', 'agent_definitions.manage', 'support_access.grant', 'system.health'],
  platformRoles: [{ key: 'platform_admin', kind: null, label: 'Platform administrator' }],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

/** The server: the session, the two reads the screen makes, and whatever the test adds. */
function server(tenants: Answer, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: platformAdmin };
    if (sent.path === LANGUAGES_PATH) return { status: 200, data: LANGUAGES };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === TENANTS_PATH && sent.method === 'get') return tenants;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

async function openForm(): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole('button', { name: 'Create a tenant' }));
  const form = await screen.findByRole('dialog', { name: 'Create a tenant' });
  await within(form).findByLabelText('English');
  return form;
}

function fill(form: HTMLElement, values: { name?: string; slug?: string; email?: string }): void {
  if (values.name !== undefined) fireEvent.change(within(form).getByLabelText('Name'), { target: { value: values.name } });
  if (values.slug !== undefined) fireEvent.change(within(form).getByLabelText('Short name'), { target: { value: values.slug } });
  if (values.email !== undefined) fireEvent.change(within(form).getByLabelText("First administrator's email"), { target: { value: values.email } });
}

beforeEach(() => {
  resetApiForTests();
});

describe('the console tenants screen', () => {
  it('lists every bank with its status and created date, and asks for nothing inside one', async () => {
    const sent = server({ status: 200, data: { items: [tenantA, tenantB], total: 2 } });
    renderIn(<TenantsScreen />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Tenants' })).toBeInTheDocument();
    await screen.findByText('Example Bank AB');

    const rows = [...document.querySelectorAll('[data-tenant-id]')];
    expect(rows.map((row) => row.getAttribute('data-tenant-slug'))).toEqual(['example-bank', 'second-bank']);
    expect(within(rows[0] as HTMLElement).getByText('Active')).toHaveAttribute('data-pill', 'positive');
    expect(within(rows[1] as HTMLElement).getByText('Deactivated')).toHaveAttribute('data-pill', 'information');
    expect(rows[0]).toHaveTextContent('Swedish');
    expect(rows[0]).toHaveTextContent('Created 17 Sept 2026');

    // The session, the language reference and the tenant rows: no read of
    // anything a bank holds.
    expect(new Set(sent.map((s) => `${s.method} ${s.path}`))).toEqual(new Set([`post ${REFRESH_PATH}`, `get ${ME_PATH}`, `get ${LANGUAGES_PATH}`, `get ${TENANTS_PATH}`]));
  });

  it('shows the loading state, then the empty one when no bank exists yet', async () => {
    server({ status: 200, data: { items: [], total: 0 } });
    renderIn(<TenantsScreen />);
    expect(document.querySelector('[data-loading-state]')).not.toBeNull();
    expect(await screen.findByRole('heading', { name: 'No tenants yet' })).toBeInTheDocument();
    expect(screen.getByText('Create the first tenant and invite its administrator.')).toBeInTheDocument();
  });

  it('offers a retry when the read fails', async () => {
    let answered = 0;
    server({ status: 500 }, (sent) => {
      if (sent.path !== TENANTS_PATH || sent.method !== 'get') return undefined;
      answered += 1;
      return answered === 1 ? { status: 500 } : { status: 200, data: { items: [tenantA], total: 1 } };
    });
    renderIn(<TenantsScreen />);
    expect(await screen.findByRole('heading', { name: 'Could not load the tenants' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Example Bank AB')).toBeInTheDocument();
  });

  it('shows the Restricted screen, naming the grant, to a person without tenants.manage', async () => {
    server({ status: 200, data: { items: [], total: 0 } });
    renderIn(
      <PermissionsProvider permissions={['proposals.review', 'library_vocab.manage']}>
        <ConsoleTenantsPage />
      </PermissionsProvider>,
    );
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByRole('heading', { name: 'This page is not available to you' })).toBeInTheDocument();
    expect(alert).toHaveTextContent('Needs tenants manage');
    expect(screen.queryByRole('button', { name: 'Create a tenant' })).toBeNull();
  });

  it('creates a bank with its first administrator, and says who was invited', async () => {
    const created = { id: 't3', name: 'Third Bank AB', slug: 'third-bank', status: 'active', defaultLanguage: LANGUAGES[0], createdAt: '2026-09-20T08:00:00Z' };
    let tenants = [tenantA];
    const sent = server({ status: 200, data: { items: [tenantA], total: 1 } }, (s) => {
      if (s.path === TENANTS_PATH && s.method === 'post') {
        tenants = [tenantA, created];
        return { status: 201, data: created };
      }
      if (s.path === TENANTS_PATH) return { status: 200, data: { items: tenants, total: tenants.length } };
      return undefined;
    });
    renderIn(<TenantsScreen />);
    const form = await openForm();
    fill(form, { name: 'Third Bank AB', slug: 'third-bank', email: 'administrator@third-bank.test' });
    fireEvent.click(within(form).getByLabelText('Swedish'));
    fireEvent.click(within(form).getByRole('button', { name: 'Create tenant' }));

    expect(await screen.findByText('Third Bank AB is ready. Its first administrator has been invited.')).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector('[data-tenant-slug="third-bank"]')).not.toBeNull());
    const posted = sent.find((s) => s.method === 'post' && s.path === TENANTS_PATH);
    expect(posted?.body).toEqual({
      name: 'Third Bank AB',
      slug: 'third-bank',
      timezone: 'Europe/Stockholm',
      defaultLanguage: 'en',
      contentLanguages: ['en', 'sv'],
      firstAdminEmail: 'administrator@third-bank.test',
      firstAdminTitle: '',
    });
  });

  it('shows a short name another bank already uses in the form, and keeps what was typed', async () => {
    server({ status: 200, data: { items: [tenantA], total: 1 } }, (s) =>
      s.method === 'post' ? { status: 409, data: { code: 'duplicate_key', detail: 'An organisation already uses that short name.', status: 409 } } : undefined,
    );
    renderIn(<TenantsScreen />);
    const form = await openForm();
    fill(form, { name: 'Another Bank AB', slug: 'example-bank', email: 'administrator@another-bank.test' });
    fireEvent.click(within(form).getByRole('button', { name: 'Create tenant' }));

    expect(await within(form).findByText('Another tenant already uses that short name.')).toBeInTheDocument();
    expect(within(form).getByLabelText('Short name')).toHaveValue('example-bank');
  });

  it('asks for what the server would refuse, before sending anything', async () => {
    const sent = server({ status: 200, data: { items: [tenantA], total: 1 } });
    renderIn(<TenantsScreen />);
    const form = await openForm();
    const create = within(form).getByRole('button', { name: 'Create tenant' });

    fireEvent.click(create);
    expect(await within(form).findByText('Give the tenant a name.')).toBeInTheDocument();
    fill(form, { name: 'Third Bank AB' });
    fireEvent.click(create);
    expect(await within(form).findByText('Give the tenant a short name.')).toBeInTheDocument();
    fill(form, { slug: 'third-bank' });
    fireEvent.click(create);
    expect(await within(form).findByText("Give the first administrator's address.")).toBeInTheDocument();
    fill(form, { email: 'administrator@third-bank.test' });
    fireEvent.click(within(form).getByLabelText('English'));
    fireEvent.click(create);
    expect(await within(form).findByText('Choose at least one content language.')).toBeInTheDocument();

    expect(sent.filter((s) => s.method === 'post' && s.path === TENANTS_PATH)).toHaveLength(0);
  });
});
