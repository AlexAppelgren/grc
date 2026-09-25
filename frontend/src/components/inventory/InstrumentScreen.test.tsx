import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { InstrumentScreen } from './InstrumentScreen';
import type { InstrumentDetail, Obligation } from '@/features/library/types';

// The instrument card (design/screens/tenant-instrument.html; INV-01, INV-06,
// FP-03): the header pills, the Identity panel, the source link, lineage
// grouped by relation and direction, the obligations from this instrument
// inside our scope unless asked otherwise, and every state the card names.
// Nothing here writes but "This looks wrong".

const fffs: InstrumentDetail = {
  id: 'in-1',
  stableKey: 'fffs-2017-2',
  shortName: 'FFFS 2017:2',
  name: { text: 'FFFS 2017:2 om värdepappersrörelse', language: 'sv', isOriginal: true, isMachine: false },
  level: { key: 'authority_regulation', kind: null, label: 'Supervisory regulation' },
  binding: true,
  jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
  authority: { key: 'fi', name: 'Finansinspektionen', shortName: 'FI', url: 'https://www.fi.se/' },
  regime: { key: 'securities', kind: null, label: 'Securities' },
  officialRef: 'FFFS 2017:2',
  eliUri: '',
  inForceFrom: { date: '2018-01-03', precision: 'day' },
  inForceTo: null,
  implementsNote: 'MiFID II delegated directive (EU) 2017/593',
  sourceUrl: 'https://www.fi.se/en/published/regulations/2017/fffs-20172/',
  lastVerifiedAt: '2026-06-30T07:12:44Z',
  verifiedBy: null,
  privateToUs: false,
  lineage: [
    {
      relation: { key: 'amends', kind: null, label: 'Amends' },
      direction: 'incoming',
      instrument: { key: 'fffs-2026-11', shortName: 'FFFS 2026:11' },
      note: 'Amends FFFS 2017:2, in force 1 October 2026.',
      toRef: '',
    },
    {
      relation: { key: 'implements', kind: null, label: 'Implements' },
      direction: 'outgoing',
      instrument: { key: 'celex-32017l0593', shortName: 'Delegated directive (EU) 2017/593' },
      note: '',
      toRef: '',
    },
  ],
};

const researchObligation: Obligation = {
  id: 'ob-1',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: true, isMachine: false },
  instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
  bindingLevel: { key: 'authority_regulation', kind: null, label: 'Supervisory regulation' },
  binding: true,
  dutyType: { key: 'governance', kind: null, label: 'Governance' },
  tags: [],
  scope: [],
  version: { versionNumber: 1, effectiveFrom: null, approvedAt: null, verifiedOrigin: '', confirmedByAgent: null, proposedByAgent: null },
  upcomingVersion: null,
  jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
  inFootprint: true,
  outsideReason: [],
  lastVerifiedAt: null,
  verifiedBy: null,
  openChangeCount: 0,
  tenantTags: [],
  privateToUs: false,
  complianceStatus: null,
};

const ME = {
  user: { id: 'u1', name: 'Sara', locale: 'en' },
  tenant: { timezone: 'Europe/Stockholm' },
  permissions: ['library.read', 'problems.report'],
  enrolmentPending: false,
};

function renderIn(node: ReactNode, permissions: string[] = ['library.read', 'problems.report']) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      {
        <LocaleProvider locale="en">
          <PermissionsProvider permissions={permissions}>{node}</PermissionsProvider>
        </LocaleProvider>
      }
    </Wrapper>,
  );
}

/** The server: /me, the card, its obligations (`total` beyond the page when given) and the report. */
function serve(answer: InstrumentDetail | number, obligations: Obligation[] = [researchObligation], total = obligations.length) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: ME };
    if (sent.path === '/api/v1/obligations') return { status: 200, data: { items: obligations, total } };
    if (sent.path.endsWith('/provisions')) return { status: 200, data: [] };
    // The record's "Reported problems" (AUD-03): the bank has filed none on it.
    if (sent.path === '/api/v1/problem-reports') return { status: 200, data: { items: [], total: 0 } };
    if (sent.path.endsWith('/problem-reports')) return { status: 201, data: { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' } };
    if (typeof answer === 'number') return { status: answer, data: { detail: 'no', code: answer === 404 ? 'not_found' : 'server_error' } };
    return { status: 200, data: answer };
  });
}

describe('InstrumentScreen', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('a standard reads "Standard" in its binding slots and says its text is licensed, with the catalogue link', async () => {
    const iso: InstrumentDetail = {
      ...fffs,
      stableKey: 'iso-27001-2022',
      shortName: 'ISO/IEC 27001:2022',
      name: { text: 'Information security management systems', language: 'en', isOriginal: true, isMachine: false },
      level: { key: 'standard', kind: 'standard', label: 'Standard edition' },
      binding: false,
      jurisdiction: { key: 'int', kind: 'international', label: 'International' },
      authority: null,
      regime: { key: 'ai_ict', kind: null, label: 'AI and ICT' },
      sourceUrl: 'https://www.iso.org/standard/27001',
      lineage: [],
    };
    const control: Obligation = {
      ...researchObligation,
      instrument: { key: iso.stableKey, shortName: iso.shortName },
      bindingLevel: iso.level,
      binding: false,
    };
    const sent = serve(iso, [control]);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1, name: 'Information security management systems' });

    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['ISO/IEC 27001:2022', 'brand'],
      ['Standard edition', 'information'],
      ['Standard', 'information'],
      ['International', 'brand'],
      ['AI and ICT', 'information'],
    ]);
    expect(screen.queryByText('Guidance, comply or explain')).toBeNull();
    const identity = document.querySelector('[data-identity-panel]') as HTMLElement;
    expect(within(identity).getByText('Standard')).toBeInTheDocument();

    const licensed = document.querySelector('[data-provision-tree] [data-provisions-licensed]') as HTMLElement;
    expect(within(licensed).getByRole('link', { name: "See it in the publisher's catalogue" })).toHaveAttribute('href', iso.sourceUrl);
    expect(sent.some((request) => request.path.endsWith('/provisions'))).toBe(false);

    // The row of an obligation under it reads "Standard" in its guidance slot, never "Guidance".
    await waitFor(() => expect(document.querySelector('[data-obligations-panel] [data-obligation]')).not.toBeNull());
    const row = document.querySelector('[data-obligations-panel] [data-obligation]') as HTMLElement;
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['ISO/IEC 27001:2022', 'brand'],
      ['Standard', 'information'],
    ]);
  });

  it('leads the head of the bank\'s own instrument with "Private to us", its short name outlined (OWN-04)', async () => {
    serve({ ...fffs, privateToUs: true });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1, name: 'FFFS 2017:2 om värdepappersrörelse' });
    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].slice(0, 3).map((pill) => [pill.textContent, pill.getAttribute('data-pill'), pill.hasAttribute('data-outlined')])).toEqual([
      ['Private to us', 'information', true],
      ['FFFS 2017:2', 'information', true],
      ['Supervisory regulation', 'information', false],
    ]);
  });

  it('shows the header pills, the identity panel, the source link and the obligations from this instrument', async () => {
    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1, name: 'FFFS 2017:2 om värdepappersrörelse' });

    // Short name and jurisdiction are brand, level and binding are information (INV-S1).
    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['FFFS 2017:2', 'brand'],
      ['Supervisory regulation', 'information'],
      ['Binding', 'information'],
      ['Sweden', 'brand'],
      ['Securities', 'information'],
    ]);

    const identity = document.querySelector('[data-identity-panel]') as HTMLElement;
    expect(within(identity).getByText('FFFS 2017:2')).toBeInTheDocument();
    expect(within(identity).getByText('Not available')).toBeInTheDocument();
    expect(within(identity).getByText('Finansinspektionen')).toBeInTheDocument();
    expect(document.querySelector('[data-last-verified]')?.textContent).toBe('30 Jun 2026');

    const source = screen.getByRole('link', { name: 'Source' });
    expect(source).toHaveAttribute('href', fffs.sourceUrl);
    expect(source).toHaveAttribute('rel', 'noopener noreferrer');

    // An instrument with no provision tree yet shows the empty state, not an error.
    expect(await screen.findByText('No provisions yet')).toBeVisible();

    expect(await screen.findByText('Pay for third-party research only under the permitted models')).toBeInTheDocument();
  });

  it('groups the lineage by relation and direction, each under its own heading', async () => {
    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    const groups = [...document.querySelectorAll('[data-lineage-group]')];
    expect(groups.map((group) => [group.getAttribute('data-lineage-group'), group.querySelector('h3')?.textContent])).toEqual([
      ['amends:incoming', 'Amends this instrument'],
      ['implements:outgoing', 'Implements'],
    ]);
    const amendedBy = document.querySelector('[data-lineage-group="amends:incoming"]') as HTMLElement;
    expect(within(amendedBy).getByText('FFFS 2026:11')).toBeInTheDocument();
    expect(within(amendedBy).getByText('Amends FFFS 2017:2, in force 1 October 2026.')).toBeInTheDocument();
    expect(within(document.querySelector('[data-lineage-group="implements:outgoing"]') as HTMLElement).getByText('Delegated directive (EU) 2017/593')).toBeInTheDocument();
  });

  it('shows what implements this instrument and what it amends, pairs no fixed list names', async () => {
    // The directive's card sees FFFS 2017:2 implementing it (incoming implements);
    // the amending instrument's card sees its own amendment going out.
    const lineage: InstrumentDetail['lineage'] = [
      { relation: { key: 'implements', kind: null, label: 'Implements' }, direction: 'incoming', instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2' }, note: '', toRef: '' },
      { relation: { key: 'amends', kind: null, label: 'Amends' }, direction: 'outgoing', instrument: { key: 'fffs-2017-1', shortName: 'FFFS 2017:1' }, note: '', toRef: '9 kap. 6 §' },
    ];
    serve({ ...fffs, lineage });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    const implementedBy = document.querySelector('[data-lineage-group="implements:incoming"]') as HTMLElement;
    expect(within(implementedBy).getByRole('heading', { level: 3 })).toHaveTextContent('Implements this instrument');
    expect(within(implementedBy).getByText('FFFS 2017:2')).toBeInTheDocument();
    const amends = document.querySelector('[data-lineage-group="amends:outgoing"]') as HTMLElement;
    expect(within(amends).getByRole('heading', { level: 3 })).toHaveTextContent('Amends');
    expect(within(amends).getByText('FFFS 2017:1')).toBeInTheDocument();
    expect(screen.queryByText('The library files no other instrument beside this one.')).toBeNull();
  });

  it('shows the lineage empty state when the instrument has none', async () => {
    serve({ ...fffs, lineage: [] });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByText('The library files no other instrument beside this one.')).toBeVisible();
    expect(document.querySelector('[data-lineage-group]')).toBeNull();
  });

  it('reads the obligations inside our scope first, with the total and a link to the same list in the inventory', async () => {
    const sent = serve(fffs, [researchObligation], 34);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    const read = sent.filter((s) => s.path === '/api/v1/obligations');
    expect(read[0]?.params).toMatchObject({ instrument: 'fffs-2017-2' });
    expect(read[0]?.params).not.toHaveProperty('footprint');
    const panel = document.querySelector('[data-obligations-panel]') as HTMLElement;
    expect(within(panel).getByRole('button', { name: 'In our scope' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(panel).getByRole('button', { name: 'Show outside our scope' })).toHaveAttribute('aria-pressed', 'false');
    expect(panel.querySelector('[data-obligations-total]')).toHaveTextContent('34 obligations');
    expect(within(panel).getByRole('link', { name: 'Open in the inventory' })).toHaveAttribute('href', '/inventory?instrument=fffs-2017-2');
  });

  it('asks for the obligations outside our scope on request, and the link follows', async () => {
    const sent = serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    const panel = document.querySelector('[data-obligations-panel]') as HTMLElement;
    fireEvent.click(within(panel).getByRole('button', { name: 'Show outside our scope' }));
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/obligations').at(-1)?.params).toMatchObject({ instrument: 'fffs-2017-2', footprint: 'all' }));
    expect(within(panel).getByRole('button', { name: 'Show outside our scope' })).toHaveAttribute('aria-pressed', 'true');
    expect(await within(panel).findByRole('link', { name: 'Open in the inventory' })).toHaveAttribute('href', '/inventory?instrument=fffs-2017-2&scope=all');
  });

  it('asks for what the watched markets add, names each row\'s market, and the link follows', async () => {
    const sent = serve(fffs, [{ ...researchObligation, inFootprint: false, jurisdiction: { key: 'dk', kind: 'country', label: 'Denmark' } }]);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    const panel = document.querySelector('[data-obligations-panel]') as HTMLElement;
    fireEvent.click(within(panel).getByRole('button', { name: 'Markets we watch' }));
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/obligations').at(-1)?.params).toMatchObject({ instrument: 'fffs-2017-2', footprint: 'watched' }));
    expect(await within(panel).findByText('Market we watch: Denmark')).toBeVisible();
    expect(panel.querySelector('[data-outside-footprint]')).toBeNull();
    expect(within(panel).getByRole('link', { name: 'Open in the inventory' })).toHaveAttribute('href', '/inventory?instrument=fffs-2017-2&scope=watched');
  });

  it('shows the ELI when the instrument carries one, and "by <name>" when someone verified it', async () => {
    serve({ ...fffs, eliUri: 'http://data.europa.eu/eli/reg/2017/565', verifiedBy: { id: 'u-2', name: 'Johan Ek' } });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('http://data.europa.eu/eli/reg/2017/565')).toBeInTheDocument();
    expect(document.querySelector('[data-last-verified]')?.textContent).toBe('30 Jun 2026 by Johan Ek');
  });

  it('says none is in our scope, and none at all once the reader looks outside it', async () => {
    serve(fffs, []);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByText('No obligation from this instrument is in our scope.')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Open in the inventory' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show outside our scope' }));
    expect(await screen.findByText('This instrument has no obligation yet.')).toBeVisible();
  });

  it('offers a retry when the read fails, and Not found on a 404', async () => {
    const sent = serve(500);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/instruments/in-1').length).toBeGreaterThan(1));
    expect(screen.getByText('Could not load this instrument')).toBeVisible();

    serve(404);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByRole('heading', { name: 'Not found' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Inventory' })).toHaveAttribute('href', '/inventory');
  });

  it('files a report through "This looks wrong", and hides the button without the permission', async () => {
    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    fireEvent.click(screen.getByRole('button', { name: 'This looks wrong' }));
    fireEvent.change(screen.getByLabelText('What you see'), { target: { value: 'The in-force date looks wrong.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }));
    expect(await screen.findByText('Report sent. Thank you.')).toBeVisible();

    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />, ['library.read']);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('button', { name: 'This looks wrong' })).toBeNull();
  });

  it("shows the instrument's reported problems, and none of it without the permission", async () => {
    const sent = serve(fffs);
    const withReport = renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByText('No problems reported on this record.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Reported problems' })).toBeInTheDocument();
    expect(sent.filter((call) => call.path === '/api/v1/problem-reports').map((call) => call.params)).toEqual([
      { subjectType: 'instrument', subjectId: fffs.id, limit: 20, offset: 0 },
    ]);
    withReport.unmount();

    renderIn(<InstrumentScreen instrumentId="in-1" />, ['library.read']);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('heading', { name: 'Reported problems' })).toBeNull();
  });
});
