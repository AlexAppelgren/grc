import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LicencesScreen } from '@/components/admin/LicencesScreen';
import { installAdapter, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { renderWith } from '@/shared/testing/render';

// Licences (TEN-02, TEN-07, TEN-S16, TEN-S2, TEN-S10): every legal entity in the
// Organisation page's order with its register lines and what each brings into scope, the
// licences and certificates the bank recorded (a certificate with its owner, a withdrawn row
// behind Show withdrawn, Edit and Add only for vocab.manage, a refused write placed by its
// code), the terms outside its own scope, and its offered obligations for register.read.

const UNITS = '/api/v1/tenant/org-units';
const COMPANIES = '/api/v1/applicability/companies';
const bankLicences = `${UNITS}/bank/licences`;

const group = { id: 'group', kind: 'group', name: 'Example Group', parentId: null, orgNumber: '', lei: '', countryCode: '', entityTerm: null, head: null, active: true, version: 1, registerEntry: null, licences: [] };
const bank = { ...group, id: 'bank', kind: 'legal_entity', name: 'Example Bank AB', parentId: 'group', orgNumber: '556000-0001', countryCode: 'SE', entityTerm: { key: 'bank', kind: null, label: 'Bank' } };
const fonder = { ...bank, id: 'fonder', name: 'Example Fonder AB', orgNumber: '556000-0003', entityTerm: { key: 'fund_company', kind: null, label: 'Fund company' } };
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

const term = (key: string, label: string, dimension = 'regime') => ({ key, label, kind: null, dimension });
const licenceLine = (text: string, grantedOn: string | null = null) => ({ text, grantedOn });
const entry = {
  authority: { key: 'fi', name: 'Finansinspektionen' },
  facts: {
    name: 'Example Bank AB',
    registrationNumber: '556000-0001',
    lei: '',
    mainBusiness: 'Bankaktiebolag',
    otherBusinesses: ['Medelstort institut'],
    licences: [licenceLine('Tillstånd att driva bankrörelse', '1995-03-01'), licenceLine('Tillstånd att ge ut elektroniska pengar'), licenceLine('IM_MR_SA')],
    branches: [],
    branchesRead: true,
    listed: true,
  },
  sourceUrl: 'https://www.fi.se/sv/vara-register/',
  readAt: '2026-11-11T03:17:00Z',
  changedAt: '2026-11-11T03:17:00Z',
  mapped: [
    { line: 'Bankaktiebolag', terms: [term('banking', 'Banking'), term('bank', 'Bank', 'legal_entity')] },
    { line: 'Tillstånd att driva bankrörelse', terms: [term('banking', 'Banking'), term('payments', 'Payments')] },
  ],
  unmapped: ['Tillstånd att ge ut elektroniska pengar'],
};

const dimensions = { items: [{ key: 'standard', kind: 'opt_in', label: 'Standards', extra: {} }, { key: 'legal_entity', kind: 'scope', label: 'Legal entity', extra: {} }], total: 2 };
const terms = {
  items: [
    { dimension: { key: 'standard', label: 'Standards' }, key: 'iso_iec_27001', label: 'ISO/IEC 27001', active: true, mirrored: false },
    { dimension: { key: 'legal_entity', label: 'Legal entity' }, key: 'bank', label: 'Bank', active: true, mirrored: false },
  ],
  total: 2,
};
const people = [{ id: 'u-sara', name: 'Sara Lindqvist' }];
const companies = [{ orgUnit: { id: 'bank', name: 'Example Bank AB' }, offered: 142, applies: 100, notApplicable: 11, underAssessment: 31 }];

const defaultUnits = [{ ...bank, licences: [banking, withdrawn] }, group, retail];

function server({ units = defaultUnits, write }: { units?: unknown[]; write?: (sent: Sent) => { status: number; data?: unknown } } = {}): Sent[] {
  return installAdapter((sent) => {
    if (sent.method === 'get' && sent.path === UNITS) return { status: 200, data: { items: units, total: units.length } };
    if (sent.path === COMPANIES) return { status: 200, data: companies };
    if (sent.path === '/api/v1/vocab/term_dimension') return { status: 200, data: dimensions };
    if (sent.path === '/api/v1/taxonomy/terms') return { status: 200, data: terms };
    if (sent.path === '/api/v1/reference/people') return { status: 200, data: people };
    if (sent.method !== 'get' && write !== undefined) return write(sent);
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

const panel = (name: string) => document.querySelector<HTMLElement>(`[data-company="${name}"]`)!;

async function renderScreen(permissions: string[]): Promise<void> {
  renderWith(<LicencesScreen />, { permissions });
  await screen.findByRole('heading', { level: 2, name: 'Example Bank AB' });
}

beforeEach(() => {
  resetApiForTests();
});

describe('the companies', () => {
  it('draws one card per legal entity in the Organisation page order, with its type, number, country and What applies', async () => {
    server({ units: [{ ...fonder, licences: [] }, group, retail, { ...bank, licences: [banking] }] });
    await renderScreen(['register.read']);
    expect(screen.getByText("What each company is licensed or certified for. A certificate's expiry and next audit show on the roadmap as your own deadlines.")).toBeInTheDocument();
    expect([...document.querySelectorAll('[data-company]')].map((card) => card.getAttribute('data-company'))).toEqual(['Example Fonder AB', 'Example Bank AB']);
    const card = within(panel('Example Bank AB'));
    expect(card.getByText('Bank', { selector: '[data-pill]' })).toHaveAttribute('data-pill', 'brand');
    expect(card.getByText('556000-0001')).toHaveClass('font-mono');
    expect(card.getByText('Sweden')).toBeInTheDocument();
    expect(card.getByRole('link', { name: 'What applies to Example Bank AB' })).toHaveAttribute('href', '/applies?company=bank');
    expect(screen.queryByText('Example Group')).not.toBeInTheDocument();
    expect(screen.queryByText('Retail Banking')).not.toBeInTheDocument();
  });

  it('draws no What applies for someone without register.read, who cannot open it', async () => {
    server();
    await renderScreen(['vocab.manage']);
    expect(within(panel('Example Bank AB')).queryByRole('link', { name: 'What applies to Example Bank AB' })).not.toBeInTheDocument();
  });

  it('marks an inactive company and draws no What applies, which lists active companies only', async () => {
    server({ units: [{ ...bank, active: false, licences: [] }] });
    await renderScreen(['register.read']);
    const card = panel('Example Bank AB');
    expect(card).toHaveClass('opacity-60');
    expect(within(card).getByText('Inactive')).toBeInTheDocument();
    expect(within(card).queryByRole('link', { name: 'What applies to Example Bank AB' })).not.toBeInTheDocument();
  });

  it('names the next step when the bank has no legal entity yet', async () => {
    server({ units: [group] });
    renderWith(<LicencesScreen />, { permissions: ['vocab.manage'] });
    const empty = (await screen.findByText('No legal entities yet')).closest('[data-empty-state]') as HTMLElement;
    expect(within(empty).getByRole('link', { name: 'Go to Organisation' })).toHaveAttribute('href', '/admin/organisation');
  });

  it('says when the units could not be read', async () => {
    installAdapter(() => ({ status: 500, data: { code: 'server_error', detail: 'Down.' } }));
    renderWith(<LicencesScreen />, { permissions: [] });
    expect(await screen.findByText('The licences could not be loaded')).toBeInTheDocument();
  });

  it('says in one line when a company has neither register facts nor recorded licences, with Add for vocab.manage', async () => {
    server({ units: [{ ...bank, licences: [] }] });
    await renderScreen(['vocab.manage']);
    const recorded = within(panel('Example Bank AB').querySelector<HTMLElement>('[data-licences-of]')!);
    expect(recorded.getByText('No licences from the register and none recorded by us.')).toBeInTheDocument();
    expect(recorded.queryByRole('heading', { name: 'Recorded by us' })).not.toBeInTheDocument();
    expect(recorded.getByRole('button', { name: 'Add a licence or certificate to Example Bank AB' })).toBeInTheDocument();
  });
});

describe('from the register', () => {
  it('lists the businesses then the licence lines, each with the terms it brings or that it is not used for scope', async () => {
    server({ units: [{ ...bank, licences: [], registerEntry: entry }] });
    await renderScreen([]);
    const register = panel('Example Bank AB').querySelector<HTMLElement>('[data-register-lines]')!;
    expect(within(register).getByText(/^Finansinspektionen · read /)).toBeInTheDocument();
    expect(within(register).getByRole('link', { name: 'Source' })).toHaveAttribute('href', 'https://www.fi.se/sv/vara-register/');
    expect(register.querySelector('a[href=""]')).toBeNull();
    const lines = [...register.querySelectorAll<HTMLElement>('[data-register-line]')];
    expect(lines.map((line) => line.firstElementChild?.textContent)).toEqual(['Bankaktiebolag', 'Medelstort institut', 'Tillstånd att driva bankrörelse', 'Tillstånd att ge ut elektroniska pengar', 'IM_MR_SA']);
    const [business, size, bankLine, money, code] = lines as [HTMLElement, HTMLElement, HTMLElement, HTMLElement, HTMLElement];
    expect(within(business).getAllByText(/./, { selector: '[data-pill]' }).map((pill) => pill.textContent)).toEqual(['Banking', 'Bank']);
    expect(bankLine).toHaveTextContent('granted 1 Mar 1995');
    expect(bankLine.querySelector('[data-brings]')).toHaveTextContent('Brings into scope');
    for (const pill of within(bankLine).getAllByText(/./, { selector: '[data-pill]' })) expect(pill).toHaveAttribute('data-pill', 'brand');
    expect(within(bankLine).getAllByText(/./, { selector: '[data-pill]' }).map((pill) => pill.textContent)).toEqual(['Banking', 'Payments']);
    expect(money.querySelector('[data-unmapped]')).toHaveTextContent('Not used for scope yet');
    expect(money.querySelector('[data-pill]')).toBeNull();
    for (const bare of [size, code]) {
      expect(bare.querySelector('[data-brings]')).toBeNull();
      expect(bare.querySelector('[data-unmapped]')).toBeNull();
    }
    // The register's facts sit above what the bank recorded itself.
    expect(within(panel('Example Bank AB')).getByRole('heading', { name: 'Recorded by us' })).toBeInTheDocument();
    expect(within(panel('Example Bank AB')).getByText('None')).toBeInTheDocument();
  });

  it('draws no Source link when the register address is not an absolute http(s) address', async () => {
    for (const sourceUrl of ['', 'javascript:alert(1)', '/relative']) {
      resetApiForTests();
      server({ units: [{ ...bank, licences: [], registerEntry: { ...entry, sourceUrl } }] });
      const { unmount } = renderWith(<LicencesScreen />, { permissions: [] });
      await screen.findByRole('heading', { level: 2, name: 'Example Bank AB' });
      const register = panel('Example Bank AB').querySelector<HTMLElement>('[data-register-lines]')!;
      expect(within(register).getByText(/^Finansinspektionen · read /)).toBeInTheDocument();
      expect(within(register).queryByRole('link', { name: 'Source' })).not.toBeInTheDocument();
      unmount();
    }
  });

  it('folds the licence lines after the fifth away', async () => {
    const licences = Array.from({ length: 7 }, (_, i) => licenceLine(`Licence line ${i + 1}`));
    server({ units: [{ ...bank, licences: [], registerEntry: { ...entry, facts: { ...entry.facts, otherBusinesses: [], licences }, mapped: [], unmapped: [] } }] });
    await renderScreen([]);
    const card = within(panel('Example Bank AB'));
    expect(card.getByText('Licence line 5')).toBeVisible();
    expect(card.queryByText('Licence line 6')).not.toBeInTheDocument();
    fireEvent.click(card.getByRole('button', { name: 'Show 2 more' }));
    expect(card.getByText('Licence line 6')).toBeVisible();
    expect(card.getByText('Licence line 7')).toBeVisible();
  });
});

describe("outside the company's scope", () => {
  const excluded = [{ ...fonder, licences: [], scopeExclusions: [{ key: 'insurance', kind: null, label: 'Insurance' }, { key: 'banking', kind: null, label: 'Banking' }] }];

  it('shows each excluded term as a brand pill, and the way to Regulatory scope to someone who may open it', async () => {
    server({ units: excluded });
    renderWith(<LicencesScreen />, { permissions: ['footprint.request'] });
    const outside = (await screen.findByRole('heading', { name: "Outside this company's scope" })).closest('[data-outside-scope]') as HTMLElement;
    expect(within(outside).getAllByText(/./, { selector: '[data-pill="brand"]' }).map((pill) => pill.textContent)).toEqual(['Insurance', 'Banking']);
    expect(within(outside).getByRole('link', { name: 'Regulatory scope' })).toHaveAttribute('href', '/admin/footprint');
  });

  it('draws no link to Regulatory scope for someone who may not open it, and no section without exclusions', async () => {
    server({ units: [...excluded, { ...bank, licences: [] }] });
    renderWith(<LicencesScreen />, { permissions: [] });
    const outside = (await screen.findByRole('heading', { name: "Outside this company's scope" })).closest('[data-outside-scope]') as HTMLElement;
    expect(within(outside).queryByRole('link')).not.toBeInTheDocument();
    expect(panel('Example Bank AB').querySelector('[data-outside-scope]')).toBeNull();
  });
});

describe('the obligations within its licences', () => {
  it('counts them for someone holding register.read, and links to What applies', async () => {
    server();
    await renderScreen(['register.read']);
    const line = await within(panel('Example Bank AB')).findByRole('link', { name: '142 obligations within its licences' });
    expect(line).toHaveAttribute('href', '/applies?company=bank');
  });

  it('never asks without register.read, and the page reads the same without the line', async () => {
    const sent = server();
    await renderScreen([]);
    expect(sent.some((s) => s.path === COMPANIES)).toBe(false);
    expect(panel('Example Bank AB').querySelector('[data-offered]')).toBeNull();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('recorded by us', () => {
  it('puts Add beside its heading, names the licences under it, and adds no second region named after the company', async () => {
    server();
    await renderScreen(['vocab.manage']);
    const recorded = panel('Example Bank AB').querySelector<HTMLElement>('[data-licences-of]')!;
    expect(recorded).not.toHaveAttribute('aria-label');
    const heading = within(recorded).getByRole('heading', { level: 3, name: 'Recorded by us' });
    expect(within(heading.parentElement!).getByRole('button', { name: 'Add a licence or certificate to Example Bank AB' })).toBeInTheDocument();
    expect(within(recorded).getByRole('heading', { level: 4, name: 'Bank' })).toBeInTheDocument();
    expect(screen.getAllByRole('region', { name: 'Example Bank AB' })).toHaveLength(1);
  });

  it('shows no Edit or Add without vocab.manage', async () => {
    server();
    await renderScreen([]);
    expect(screen.getByText('FI 12-3456')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Edit/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a licence or certificate to Example Bank AB' })).not.toBeInTheDocument();
  });

  it('keeps a withdrawn licence behind Show withdrawn, dimmed and without Edit', async () => {
    server();
    await renderScreen(['vocab.manage']);
    expect(screen.queryByText('Consumer credit')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show 1 withdrawn' }));
    const row = screen.getByText('Consumer credit').closest('[data-licence]') as HTMLElement;
    expect(row).toHaveAttribute('data-withdrawn');
    expect(within(row).getByText(/^Withdrawn /)).toBeInTheDocument();
    expect(within(row).queryByRole('button')).not.toBeInTheDocument();
  });

  it('reads the licences off the units list and never once per entity', async () => {
    const sent = server();
    await renderScreen(['vocab.manage']);
    expect(await screen.findByText('FI 12-3456')).toBeInTheDocument();
    expect(sent.some((s) => s.method === 'get' && s.path === bankLicences)).toBe(false);
  });

  it('sends the certificate fields with its owner and no licence field', async () => {
    const sent = server({ write: (s) => ({ status: 201, data: { ...banking, id: 'l3', ...(s.body as object) } }) });
    await renderScreen(['vocab.manage']);
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
    server({ write: () => ({ status: 422, data: { code: 'unknown_member', detail: 'That person is not an active member of your organisation.' } }) });
    await renderScreen(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Add a licence or certificate to Example Bank AB' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Kind'), { target: { value: 'certificate' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    const owner = await within(dialog).findByText('That person is not an active member of your organisation.');
    expect(owner).toHaveAttribute('id', 'licence-ownerUserId-error');
  });

  it('withdraws with If-Match by sending only the withdrawal date, and says so when someone changed it first', async () => {
    const sent = server({ write: () => ({ status: 409, data: { code: 'stale_write', detail: 'The record changed.' } }) });
    await renderScreen(['vocab.manage']);
    fireEvent.click(screen.getByRole('button', { name: 'Edit Bank' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Withdrawn'), { target: { value: '2026-09-30' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await within(dialog).findByText('Someone changed this while you were editing. Close it and open it again to see their change.');
    expect(sent.find((s) => s.method === 'patch')).toMatchObject({ path: '/api/v1/tenant/licences/l1', body: { withdrawnOn: '2026-09-30' } });
  });
});
