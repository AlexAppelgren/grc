import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { EntitiesSection } from '@/components/admin/EntitiesSection';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// Legal entities with their licences and certificates (TEN-02, TEN-S2,
// TEN-S10): the tree under the group, a certificate recorded with its owner,
// a withdrawn row kept behind Show withdrawn, Edit and Add only for
// vocab.manage, and a refused write placed by its code.

const UNITS = '/api/v1/tenant/org-units';
const bankLicences = `${UNITS}/bank/licences`;

const group = { id: 'group', kind: 'group', name: 'Example Group', parentId: null, orgNumber: '', lei: '', countryCode: '', entityTerm: null, head: null, active: true, version: 1 };
const bank = { ...group, id: 'bank', kind: 'legal_entity', name: 'Example Bank AB', parentId: 'group', orgNumber: '556000-0001', countryCode: 'SE', entityTerm: { key: 'bank', kind: null, label: 'Bank' } };
const retail = { ...group, id: 'retail', kind: 'business_area', name: 'Retail Banking', parentId: 'bank' };

const banking = {
  id: 'l1',
  orgUnitId: 'bank',
  licenceType: { key: 'bank', kind: null, label: 'Bank' },
  reference: 'FI 12-3456',
  grantedOn: null,
  withdrawnOn: null,
  scopeNote: 'Banking business',
  issuer: '',
  number: '',
  scopeStatement: '',
  issuedOn: null,
  validUntil: null,
  nextAuditOn: null,
  owner: null,
  serviceTerms: [{ key: 'custody', kind: null, label: 'Custody' }],
  version: 2,
};
const withdrawn = { ...banking, id: 'l2', licenceType: { key: 'consumer_credit', kind: null, label: 'Consumer credit' }, withdrawnOn: '2025-03-31', serviceTerms: [] };

const dimensions = { items: [{ key: 'standard', kind: 'opt_in', label: 'Standards', extra: {} }, { key: 'legal_entity', kind: 'scope', label: 'Legal entity', extra: {} }], total: 2 };
const terms = {
  items: [
    { dimension: { key: 'standard', label: 'Standards' }, key: 'iso_iec_27001', label: 'ISO/IEC 27001', active: true, mirrored: false },
    { dimension: { key: 'legal_entity', label: 'Legal entity' }, key: 'bank', label: 'Bank', active: true, mirrored: false },
  ],
  total: 2,
};
const people = [{ id: 'u-sara', name: 'Sara Lindqvist' }];

function server(write?: (sent: Sent) => { status: number; data?: unknown }): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.method === 'get' && sent.path === UNITS) return { status: 200, data: { items: [bank, group, retail], total: 3 } };
    if (sent.method === 'get' && sent.path === bankLicences) return { status: 200, data: { items: [banking, withdrawn], total: 2 } };
    if (sent.path === '/api/v1/taxonomy/dimensions') return { status: 200, data: dimensions };
    if (sent.path === '/api/v1/taxonomy/terms') return { status: 200, data: terms };
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
        <EntitiesSection />
      </PermissionsProvider>
    </Query>,
  );
  await screen.findByText('FI 12-3456');
}

beforeEach(() => {
  resetApiForTests();
});

describe('legal entities', () => {
  it('draws the group with its entity under it, the entity term as a brand pill, and no department', async () => {
    server();
    await renderSection(['vocab.manage']);
    const row = screen.getByText('Example Bank AB', { selector: '[data-org-unit] h3' }).closest('[data-org-unit]') as HTMLElement;
    expect(within(row).getByText('556000-0001')).toBeInTheDocument();
    expect(within(row).getByText('No LEI')).toBeInTheDocument();
    expect(within(row).getByText('Bank', { selector: '[data-pill]' })).toHaveAttribute('data-pill', 'brand');
    expect(screen.queryByText('Retail Banking')).not.toBeInTheDocument();
  });

  it('shows no Edit or Add without vocab.manage', async () => {
    server();
    await renderSection([]);
    expect(screen.queryByRole('button', { name: /^Edit/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a legal entity' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a licence or certificate to Example Bank AB' })).not.toBeInTheDocument();
  });

  it('keeps a withdrawn licence behind Show withdrawn, dimmed and without Edit', async () => {
    server();
    await renderSection(['vocab.manage']);
    expect(screen.queryByText('Consumer credit')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show 1 withdrawn' }));
    const row = screen.getByText('Consumer credit').closest('[data-licence]') as HTMLElement;
    expect(row).toHaveAttribute('data-withdrawn');
    expect(within(row).getByText(/^Withdrawn /)).toBeInTheDocument();
    expect(within(row).queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('recording a certificate', () => {
  it('sends the certificate fields with its owner and no licence field', async () => {
    const sent = server((s) => ({ status: 201, data: { ...banking, id: 'l3', ...(s.body as object) } }));
    await renderSection(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Add a licence or certificate to Example Bank AB' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Kind'), { target: { value: 'certificate' } });
    await within(dialog).findByRole('option', { name: 'ISO/IEC 27001' });
    fireEvent.change(within(dialog).getByLabelText('Type'), { target: { value: 'iso_iec_27001' } });
    fireEvent.change(within(dialog).getByLabelText('Issuer'), { target: { value: 'Example Certification AB' } });
    fireEvent.change(within(dialog).getByLabelText('Certificate number'), { target: { value: 'EC-27001-0421' } });
    fireEvent.change(within(dialog).getByLabelText('Valid until'), { target: { value: '2028-03-11' } });
    await within(dialog).findByRole('option', { name: 'Sara Lindqvist' });
    fireEvent.change(within(dialog).getByLabelText('Owner'), { target: { value: 'u-sara' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const post = sent.find((s) => s.method === 'post' && s.path === bankLicences);
    expect(post?.body).toEqual({
      licenceType: 'iso_iec_27001',
      reference: '',
      grantedOn: null,
      withdrawnOn: null,
      scopeNote: '',
      issuer: 'Example Certification AB',
      number: 'EC-27001-0421',
      scopeStatement: '',
      issuedOn: null,
      validUntil: '2028-03-11',
      nextAuditOn: null,
      ownerUserId: 'u-sara',
      serviceTerms: [],
    });
  });

  it('puts unknown_member on the owner and keeps the dialog open', async () => {
    server(() => ({ status: 422, data: { code: 'unknown_member', detail: 'That person is not an active member of your organisation.' } }));
    await renderSection(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Add a licence or certificate to Example Bank AB' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Kind'), { target: { value: 'certificate' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    const owner = await within(dialog).findByText('That person is not an active member of your organisation.');
    expect(owner).toHaveAttribute('id', 'licence-ownerUserId-error');
  });
});

describe('changing a licence', () => {
  it('withdraws with If-Match by sending only the withdrawal date, and says so when someone changed it first', async () => {
    const sent = server(() => ({ status: 409, data: { code: 'stale_write', detail: 'The record changed.' } }));
    await renderSection(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Edit Bank' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Withdrawn'), { target: { value: '2026-09-30' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await within(dialog).findByText('Someone changed this while you were editing. Close it and open it again to see their change.');
    expect(sent.find((s) => s.method === 'patch')).toMatchObject({ path: '/api/v1/tenant/licences/l1', body: { withdrawnOn: '2026-09-30' } });
  });
});
