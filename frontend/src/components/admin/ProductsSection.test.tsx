import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { ProductsSection } from '@/components/admin/ProductsSection';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// Products scoped with the terms obligations use (TEN-02, TEN-S2): the entity
// and the terms as brand pills, status as meta text, a retired product dimmed,
// a new product sent with its scope, and an unknown term placed on the scope.

const PRODUCTS = '/api/v1/tenant/products';
const bank = { id: 'bank', kind: 'legal_entity', name: 'Example Bank AB', parentId: null, orgNumber: '', lei: '', countryCode: '', entityTerm: null, head: null, active: true, version: 1 };
const custody = { id: 'p1', name: 'Custody', description: 'Safekeeping of listed securities.', status: 'live', launchDate: null, orgUnitId: 'bank', owner: { id: 'u1', name: 'Johan Berg' }, terms: [{ key: 'custody', kind: null, label: 'Custody' }], version: 1 };
const cardCredit = { ...custody, id: 'p2', name: 'Card credit', description: '', status: 'retired', owner: null, orgUnitId: null, terms: [] };
const dimensions = { items: [{ key: 'service_type', kind: 'scope', label: 'Services', extra: {} }], total: 1 };
const terms = { items: [{ dimension: { key: 'service_type', label: 'Services' }, key: 'custody', label: 'Custody', active: true, mirrored: false }, { dimension: { key: 'service_type', label: 'Services' }, key: 'advice', label: 'Advice', active: true, mirrored: false }], total: 2 };

function server(write?: (sent: Sent) => { status: number; data?: unknown }): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.method === 'get' && sent.path === PRODUCTS) return { status: 200, data: { items: [cardCredit, custody], total: 2 } };
    if (sent.path === '/api/v1/tenant/org-units') return { status: 200, data: { items: [bank], total: 1 } };
    if (sent.path === '/api/v1/taxonomy/dimensions') return { status: 200, data: dimensions };
    if (sent.path === '/api/v1/taxonomy/terms') return { status: 200, data: terms };
    if (sent.path === '/api/v1/reference/people') return { status: 200, data: [{ id: 'u1', name: 'Johan Berg' }] };
    if (sent.method !== 'get' && write !== undefined) return write(sent);
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

async function renderSection(permissions: string[]): Promise<void> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <ProductsSection />
      </PermissionsProvider>
    </Query>,
  );
  await screen.findByText('Safekeeping of listed securities.');
}

beforeEach(() => {
  resetApiForTests();
});

describe('products', () => {
  it('shows the entity and the terms as brand pills and dims a retired product', async () => {
    server();
    await renderSection(['vocab.manage']);
    const row = screen.getByText('Safekeeping of listed securities.').closest('[data-product]') as HTMLElement;
    await within(row).findByText('Example Bank AB');
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['Example Bank AB', 'brand'],
      ['Custody', 'brand'],
    ]);
    expect(within(row).getByText('Live')).toBeInTheDocument();
    expect(within(row).getByText('Owner: Johan Berg')).toBeInTheDocument();
    expect(screen.getByText('Card credit').closest('[data-product]')).toHaveClass('opacity-60');
  });

  it('shows no Edit or Add without vocab.manage', async () => {
    server();
    await renderSection([]);
    expect(screen.queryByRole('button', { name: /^Edit/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a product' })).not.toBeInTheDocument();
  });

  it('sends a new product with its scope and places an unknown term on the scope', async () => {
    const sent = server(() => ({ status: 422, data: { code: 'unknown_key', detail: 'Not a term obligations are scoped with: advice.' } }));
    await renderSection(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Add a product' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: ' Guided investing ' } });
    fireEvent.change(within(dialog).getByLabelText('Status'), { target: { value: 'planned' } });
    fireEvent.change(within(dialog).getByLabelText('Legal entity'), { target: { value: 'bank' } });
    await within(dialog).findByRole('option', { name: 'Advice' });
    fireEvent.change(within(dialog).getByLabelText('Scope'), { target: { value: 'advice' } });
    expect(within(dialog).getByRole('button', { name: 'Remove Advice' })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    const error = await within(dialog).findByText('Not a term obligations are scoped with: advice.');
    expect(error).toHaveAttribute('id', 'product-terms-error');
    expect(sent.find((s) => s.method === 'post' && s.path === PRODUCTS)?.body).toEqual({ name: 'Guided investing', description: '', status: 'planned', launchDate: null, orgUnitId: 'bank', ownerUserId: null, terms: ['advice'] });
  });

  it('changes only what moved, with the version it read', async () => {
    const sent = server((s) => ({ status: 200, data: { ...custody, ...(s.body as object), version: 2 } }));
    await renderSection(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Edit Custody' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Status'), { target: { value: 'retired' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(sent.find((s) => s.method === 'patch')).toMatchObject({ path: '/api/v1/tenant/products/p1', body: { status: 'retired' } });
  });
});
