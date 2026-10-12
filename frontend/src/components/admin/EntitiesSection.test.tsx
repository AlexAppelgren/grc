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

const group = { id: 'group', kind: 'group', name: 'Example Group', parentId: null, orgNumber: '', lei: '', countryCode: '', entityTerm: null, head: null, active: true, version: 1, registerEntry: null };
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
    if (sent.method === 'get' && sent.path === UNITS) return { status: 200, data: { items: [{ ...bank, licences: [banking, withdrawn] }, { ...group, licences: [] }, { ...retail, licences: [] }], total: 3 } };
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

  it('reads the licences off the units list and never once per entity', async () => {
    const sent = server();
    await renderSection(['vocab.manage']);
    expect(await screen.findByText('FI 12-3456', { exact: false })).toBeInTheDocument();
    expect(sent.some((s) => s.method === 'get' && s.path === bankLicences)).toBe(false);
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

describe('filling in from the public registers (TEN-07, TEN-S13)', () => {
  const LOOKUPS = '/api/v1/tenant/register-lookups';
  const facts = (name: string, mainBusiness: string, licences: number) => ({
    name,
    registrationNumber: '',
    lei: '',
    mainBusiness,
    otherBusinesses: [],
    licences: Array.from({ length: licences }, (_, i) => ({ text: `Licence ${i + 1}`, grantedOn: null })),
    branches: [],
    listed: true,
  });
  const found = (lei: string, name: string, overrides: Record<string, unknown>) => ({
    lei,
    name,
    registrationNumber: '556000-0001',
    country: 'SE',
    parentLei: null,
    leiStatus: 'ISSUED',
    authority: 'fi',
    facts: null,
    existingOrgUnitId: null,
    preselected: false,
    unmapped: [],
    entityType: null,
    sourceUrl: null,
    ...overrides,
  });
  const job = (status: string, extra: Record<string, unknown> = {}) => ({ id: 'job-1', query: '556000-0001', status, error: null, createdAt: '2026-10-05T08:00:00Z', completedAt: null, entities: [], ...extra });
  const succeeded = job('succeeded', {
    completedAt: '2026-10-05T08:00:04Z',
    entities: [
      found('BANK', 'Example Bank AB', { existingOrgUnitId: 'bank', preselected: true, facts: facts('Example Bank AB', 'Bankaktiebolag', 5) }),
      found('FONDER', 'Example Fonder AB', { registrationNumber: '556000-0003', preselected: true, facts: facts('Example Fonder AB', 'Fondbolag', 3) }),
      found('HOLDING', 'Example Holding AB', { registrationNumber: '556000-0004' }),
      found('PANK', 'Example Pank AS', { registrationNumber: '10000005', country: 'EE', authority: null }),
    ],
  });

  /** The lookup's job reads queued once, then as `outcome`; applying adds one and links one. */
  function registers(outcome: unknown, units: unknown[] = [{ ...bank, licences: [banking] }]): Sent[] {
    let reads = 0;
    return installAdapter((sent) => {
      if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
      if (sent.method === 'get' && sent.path === UNITS) return { status: 200, data: { items: units, total: units.length } };
      if (sent.path === '/api/v1/authorities') return { status: 200, data: [{ id: 'a1', key: 'fi', name: 'Finansinspektionen', shortName: 'FI', url: '', jurisdiction: { key: 'se', label: 'Sweden' } }] };
      if (sent.method === 'post' && sent.path === LOOKUPS) return { status: 202, data: job('queued') };
      if (sent.path === `${LOOKUPS}/job-1`) return { status: 200, data: (reads += 1) === 1 ? job('running') : outcome };
      if (sent.path === `${LOOKUPS}/job-1/apply`) return { status: 200, data: { created: 1, linked: 1, orgUnits: [] } };
      return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
    });
  }

  async function lookUp(): Promise<HTMLElement> {
    fireEvent.click(screen.getByRole('button', { name: 'Fill in from public registers' }));
    const dialog = await screen.findByRole('dialog', { name: 'Fill in from public registers' });
    expect(within(dialog).getByText('The group comes from GLEIF, and each Swedish company\'s licences and branches from Finansinspektionen\'s register.')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Look up' })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText('Organisation number or LEI'), { target: { value: ' 556000-0001 ' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Look up' }));
    expect(await within(dialog).findByText('Reading the registers…')).toBeInTheDocument();
    return dialog;
  }

  it('lists the group with the licensed companies ticked, the bank\'s own linked, and says what it did', async () => {
    const sent = registers(succeeded);
    await renderSection(['vocab.manage', 'footprint.request', 'library.read']);
    await lookUp();
    const dialog = await screen.findByRole('dialog', { name: "Companies in Example Bank AB's group" }, { timeout: 4000 });
    const row = (name: string) => dialog.querySelector<HTMLElement>(`[data-lookup-company="${name}"]`)!;
    const box = (name: string) => within(row(name)).getByRole('checkbox');
    expect(box('Example Bank AB')).toBeChecked();
    expect(box('Example Bank AB')).toBeDisabled();
    expect(row('Example Bank AB')).toHaveTextContent('Bankaktiebolag5 licencesAlready in your organisation');
    expect(box('Example Fonder AB')).toBeChecked();
    expect(within(row('Example Fonder AB')).getByText('556000-0003')).toHaveClass('font-mono');
    expect(box('Example Holding AB')).not.toBeChecked();
    expect(await within(row('Example Holding AB')).findByText("Not in Finansinspektionen's register")).toBeInTheDocument();
    expect(within(row('Example Pank AS')).getByText('No register we read for this country')).toBeInTheDocument();
    expect(within(dialog).getByText(/^Read from GLEIF and Finansinspektionen's register on /)).toBeInTheDocument();

    fireEvent.click(box('Example Fonder AB'));
    expect(within(dialog).getByRole('button', { name: 'Link 1 company' })).toBeEnabled();
    fireEvent.click(box('Example Fonder AB'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add 1 company and link 1' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(sent.find((s) => s.path === `${LOOKUPS}/job-1/apply`)?.body).toEqual({ leis: ['BANK', 'FONDER'] });
    expect(sent.find((s) => s.method === 'post' && s.path === LOOKUPS)?.body).toEqual({ query: '556000-0001' });
    expect(screen.getByRole('status')).toHaveTextContent('Added 1 company from the public registers. Linked 1 company you already had.');
    expect(screen.getByRole('link', { name: 'See the regulatory scope they set' })).toHaveAttribute('href', '/admin/footprint');
  });

  it('says why a lookup failed, by its code, and offers the number again', async () => {
    registers(job('failed', { error: 'lookup_ambiguous', completedAt: '2026-10-05T08:00:04Z' }), []);
    const { wrapper: Query } = queryWrapper();
    render(
      <Query>
        <PermissionsProvider permissions={['vocab.manage']}>
          <EntitiesSection />
        </PermissionsProvider>
      </Query>,
    );
    const empty = await screen.findByText('No legal entities yet');
    expect(within(empty.closest('[data-empty-state]') as HTMLElement).getByRole('button', { name: 'Add a legal entity' })).toBeInTheDocument();
    const dialog = await lookUp();
    expect(await within(dialog).findByText('More than one company has that number. Type the LEI instead.', {}, { timeout: 4000 })).toHaveAttribute('role', 'alert');
    expect(within(dialog).getByRole('button', { name: 'Look up' })).toBeEnabled();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it("shows what the register says about an entity, its licences behind a disclosure, and what is outside its own scope", async () => {
    const entry = {
      authority: { key: 'fi', name: 'Finansinspektionen' },
      facts: {
        ...facts('Example Bank AB', 'Bankaktiebolag', 0),
        otherBusinesses: ['Värdepappersbolag'],
        licences: [{ text: 'Tillstånd att driva bankrörelse', grantedOn: '1995-03-01' }, { text: 'IM_MR_SA', grantedOn: null }],
        branches: [{ name: 'Example Bank AB, filial i Danmark', countryName: 'Danmark', jurisdiction: 'dk' }],
      },
      sourceUrl: 'https://www.fi.se/',
      readAt: '2026-10-05T03:17:00Z',
      changedAt: '2026-10-05T03:17:00Z',
      unmapped: ['IM_MR_SA'],
    };
    registers(null, [{ ...bank, licences: [banking], registerEntry: entry, scopeExclusions: [{ key: 'insurance', kind: null, label: 'Insurance' }, { key: 'advice', kind: null, label: 'Advice' }] }]);
    await renderSection([]);
    const block = document.querySelector<HTMLElement>('[data-register-facts]')!;
    expect(block).toHaveTextContent('BusinessBankaktiebolag · Värdepappersbolag');
    expect(block).toHaveTextContent('BranchesExample Bank AB, filial i Danmark (Danmark)');
    expect(block).toHaveTextContent('Not used for the scopeIM_MR_SA');
    expect(block).toHaveTextContent("Outside this company's scopeInsurance, Advice");
    expect(screen.getByText(/^Read from Finansinspektionen's register on /)).toBeInTheDocument();
    const show = within(block).getByRole('button', { name: 'Show 2 licences' });
    expect(within(block).getByText('Tillstånd att driva bankrörelse')).not.toBeVisible();
    fireEvent.click(show);
    expect(within(block).getByText('Tillstånd att driva bankrörelse')).toBeVisible();
    expect(within(block).getByRole('button', { name: 'Hide licences' })).toHaveAttribute('aria-expanded', 'true');
  });
});
