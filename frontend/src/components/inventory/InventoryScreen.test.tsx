import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { InstrumentRow } from './InstrumentRow';
import { InventoryScreen, filtersFrom, isNarrowed, queryOf, searchOf, selectedInView } from './InventoryScreen';
import { ObligationRow, factsOf, metaOf, pillsOf } from './ObligationRow';
import type { Instrument, Obligation } from '@/features/library/types';
import { createT } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

// /inventory (design/screens/tenant-inventory.html): the URL carries keys,
// the row carries the pill contract, a row outside the footprint is dashed
// and says why, and every state the card names renders.

const nav = { search: '', replace: vi.fn() };

vi.mock('next/navigation', () => ({
  usePathname: () => '/inventory',
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const t = createT('en');

const research: Obligation = {
  id: 'ob-1',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: true, isMachine: false },
  instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
  bindingLevel: { key: 'regulation', kind: null, label: 'FI regulation' },
  binding: true,
  dutyType: { key: 'conduct', kind: null, label: 'Conduct' },
  tags: [{ key: 'research', kind: null, label: 'Research' }],
  scope: [
    { dimension: { key: 'service_type', kind: null, label: 'Service' }, terms: [{ key: 'advice', kind: null, label: 'Advice' }, { key: 'portfolio_management', kind: null, label: 'Portfolio management' }], allSelected: false },
    { dimension: { key: 'channel', kind: null, label: 'Channel' }, terms: [], allSelected: false },
  ],
  version: { versionNumber: 1, effectiveFrom: { date: '2018-01-03', precision: 'day' }, approvedAt: null, verifiedOrigin: '', confirmedByAgent: null, proposedByAgent: null },
  upcomingVersion: { versionNumber: 2, effectiveFrom: { date: '2026-10-01', precision: 'day' }, approvedAt: null, verifiedOrigin: '', confirmedByAgent: null, proposedByAgent: null },
  jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
  inFootprint: true,
  outsideReason: [],
  lastVerifiedAt: '2026-06-30',
  verifiedBy: null,
  openChangeCount: 1,
  tenantTags: [{ key: 'custody', kind: null, label: 'Custody' }],
  privateToUs: false,
  complianceStatus: null,
  applicability: 'under_assessment',
  firstLineOwner: null,
  ownerTeam: null,
};

const adviceOnly: Obligation = {
  ...research,
  id: 'ob-2',
  stableKey: 'obl-suitability-statement',
  refLabel: '9 kap.',
  title: { text: 'Give the retail client a suitability statement before an advised trade', language: 'en', isOriginal: false, isMachine: true },
  instrument: { key: 'sfs-2007-528', shortName: 'LVM' },
  binding: false,
  tags: [],
  version: null,
  upcomingVersion: null,
  inFootprint: false,
  outsideReason: [{ dimension: { key: 'service_type', kind: null, label: 'Service' }, terms: [{ key: 'advice', kind: null, label: 'Advice' }] }],
  lastVerifiedAt: null,
  openChangeCount: 0,
  tenantTags: [],
  complianceStatus: { key: 'gap', kind: 'gap', label: 'Gap' },
};

function renderIn(node: ReactNode, permissions: readonly string[] = ['library.read']) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <PermissionsProvider permissions={permissions}>
        <LocaleProvider locale="en">{node}</LocaleProvider>
      </PermissionsProvider>
    </Wrapper>,
  );
}

const fffs: Instrument = {
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
  inForceFrom: { date: '2018-01-03', precision: 'day' },
  inForceTo: null,
  implementsNote: 'MiFID II delegated directive (EU) 2017/593',
  obligationCount: 2,
  inFootprint: true,
  privateToUs: false,
  lastVerifiedAt: '2026-06-30',
  sourceUrl: 'https://www.fi.se/en/published/regulations/2017/fffs-20172/',
};

/**
 * The server: /me for the format context, the taxonomy and vocabulary reads for the filters, and the page.
 * `outsidePage` answers the instrument reads that lift the footprint filter; by default the same page.
 */
function serve(
  page: { items: Obligation[]; total: number } | 'error',
  instrumentPage: { items: Instrument[]; total: number } = { items: [fffs], total: 1 },
  outsidePage: { items: Instrument[]; total: number } = instrumentPage,
) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/obligations') return page === 'error' ? { status: 500 } : { status: 200, data: page };
    if (sent.path === '/api/v1/instruments') {
      const outside = (sent.params as { footprint?: string } | null)?.footprint === 'all';
      return { status: 200, data: outside ? outsidePage : instrumentPage };
    }
    if (sent.path === '/api/v1/me') return { status: 200, data: { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false } };
    if (sent.path === '/api/v1/taxonomy/terms') return { status: 200, data: { items: [{ dimension: { key: 'regime' }, key: 'securities', kind: null, label: 'Securities' }], total: 1 } };
    return { status: 200, data: [{ key: 'conduct', kind: null, label: 'Conduct', labels: { en: 'Conduct' }, usageNote: '', sortOrder: 1, active: true, isSystem: true, isDefault: true, usageCount: 2, extra: {} }] };
  });
}

describe('inventory filters in the URL', () => {
  it('reads keys and a plain date, and writes them back without the ones that are not set', () => {
    expect(filtersFrom(new URLSearchParams('instrument=fffs-2017-2&regime=securities&service=advice&dutyType=conduct&asOf=2026-09-16&scope=all'))).toEqual({
      instrument: 'fffs-2017-2',
      regime: 'securities',
      service: 'advice',
      dutyType: 'conduct',
      asOf: '2026-09-16',
      scope: 'all',
      tenantTag: '',
      applicability: '',
      complianceStatus: '',
      owner: '',
      ownerTeam: '',
    });
    expect(filtersFrom(new URLSearchParams(''))).toEqual({
      instrument: '',
      regime: '',
      service: '',
      dutyType: '',
      asOf: '',
      scope: 'in',
      tenantTag: '',
      applicability: '',
      complianceStatus: '',
      owner: '',
      ownerTeam: '',
    });
    // Anything but one of the three values leaves the footprint filter on.
    expect(filtersFrom(new URLSearchParams('scope=outside')).scope).toBe('in');
    expect(filtersFrom(new URLSearchParams('scope=watched')).scope).toBe('watched');
    expect(
      searchOf('obligations', { instrument: 'fffs-2017-2', regime: 'securities', service: 'advice', dutyType: 'conduct', asOf: '2026-09-16', scope: 'all' }),
    ).toBe('instrument=fffs-2017-2&regime=securities&service=advice&dutyType=conduct&asOf=2026-09-16&scope=all');
    expect(searchOf('obligations', { instrument: '', regime: '', service: '', dutyType: '', asOf: '', scope: 'in' })).toBe('');
    // The Instruments tab rides in the same URL, as its own key.
    expect(searchOf('instruments', { instrument: '', regime: '', service: '', dutyType: '', asOf: '', scope: 'in' })).toBe('tab=instruments');
  });

  it('turns a scope filter into a dimension:key term and leaves the rest of the query out', () => {
    expect(queryOf({ instrument: '', regime: 'securities', service: 'advice', dutyType: 'conduct', asOf: '2026-09-16', scope: 'all' })).toEqual({
      term: ['regime:securities', 'service_type:advice'],
      dutyType: 'conduct',
      asOf: '2026-09-16',
      footprint: 'all',
    });
    expect(queryOf({ instrument: 'fffs-2017-2', regime: '', service: '', dutyType: '', asOf: '', scope: 'in' })).toEqual({ instrument: 'fffs-2017-2' });
    expect(queryOf({ instrument: '', regime: '', service: 'advice', dutyType: '', asOf: '', scope: 'in' })).toEqual({ term: ['service_type:advice'] });
    expect(queryOf({ instrument: '', regime: '', service: '', dutyType: '', asOf: '', scope: 'in' })).toEqual({});
    expect(isNarrowed({ instrument: '', regime: '', service: '', dutyType: '', asOf: '', scope: 'all' })).toBe(false);
    expect(isNarrowed({ instrument: '', regime: '', service: '', dutyType: '', asOf: '2026-09-16', scope: 'in' })).toBe(true);
    expect(isNarrowed({ instrument: '', regime: '', service: '', dutyType: 'conduct', asOf: '', scope: 'in' })).toBe(true);
    expect(isNarrowed({ instrument: '', regime: 'securities', service: '', dutyType: '', asOf: '', scope: 'in' })).toBe(true);
    expect(isNarrowed({ instrument: '', regime: '', service: 'advice', dutyType: '', asOf: '', scope: 'in' })).toBe(true);
    expect(isNarrowed({ instrument: 'fffs-2017-2', regime: '', service: '', dutyType: '', asOf: '', scope: 'in' })).toBe(true);
  });
});

describe('ObligationRow', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
    nav.search = '';
    nav.replace.mockReset();
  });

  it('reads the row into the pill contract: the instrument, the level kind, the tags, and the counted open changes', () => {
    expect(factsOf(research)).toEqual({
      instrument: { key: 'fffs-2017-2', label: 'FFFS 2017:2' },
      binding: true,
      levelKind: null,
      openChangeCount: 1,
      libraryTags: [{ key: 'research', kind: null, label: 'Research' }],
      tenantTags: [{ key: 'custody', kind: null, label: 'Custody' }],
      privateToUs: false,
    });
    expect(factsOf(adviceOnly)).toMatchObject({ binding: false, tenantTags: [] });
    expect(factsOf(adviceOnly)).not.toHaveProperty('changeWaitingForApproval');
  });

  it('puts the scope terms, the version coming next and the verified date in the meta line', () => {
    expect(metaOf(research, t, defaultFormatContext)).toEqual(['Advice, Portfolio management', 'Version 2, from 1 Oct 2026', 'Verified 30 Jun 2026']);
  });

  it('labels a row whose wording in force agents confirmed, where the verified date would read, until a named person re-verifies it later', () => {
    const byAgents: Obligation = {
      ...research,
      upcomingVersion: null,
      version: {
        versionNumber: 2,
        effectiveFrom: null,
        approvedAt: '2026-08-17T14:02:11Z',
        verifiedOrigin: 'agent',
        confirmedByAgent: { id: 'a2', key: 'library-confirmer' },
        proposedByAgent: { id: 'a1', key: 'watch-sweeper' },
      },
    };
    const machine = 'Machine-confirmed 17 Aug 2026: proposed by watch-sweeper, confirmed by library-confirmer';
    expect(metaOf(byAgents, t, defaultFormatContext)).toEqual(['Advice, Portfolio management', machine]);
    // A later stamp nobody signed never vouches for wording no person has seen.
    expect(metaOf({ ...byAgents, lastVerifiedAt: '2026-08-20T09:00:00Z', verifiedBy: null }, t, defaultFormatContext)).toEqual(['Advice, Portfolio management', machine]);
    expect(metaOf({ ...byAgents, lastVerifiedAt: '2026-08-20T09:00:00Z', verifiedBy: { id: 'u1', name: 'Ida Holm' } }, t, defaultFormatContext)).toEqual([
      'Advice, Portfolio management',
      'Verified 20 Aug 2026',
    ]);
  });

  it('names the terms that put a row outside the footprint, and leaves out what the row does not carry', () => {
    expect(metaOf(adviceOnly, t, defaultFormatContext)).toEqual(['Advice, Portfolio management', 'Outside our scope: Advice']);
  });

  it('names the market a row comes from under "Markets we watch", in place of the outside reason', () => {
    const danish: Obligation = { ...adviceOnly, jurisdiction: { key: 'dk', kind: 'country', label: 'Denmark' } };
    expect(metaOf(danish, t, defaultFormatContext, true)).toEqual(['Advice, Portfolio management', 'Market we watch: Denmark']);
  });

  it('renders a watched-market row undashed, with its market as meta text and no new pill', async () => {
    serve({ items: [], total: 0 });
    const danish: Obligation = { ...adviceOnly, jurisdiction: { key: 'dk', kind: 'country', label: 'Denmark' } };
    renderIn(<ObligationRow obligation={danish} watched />);
    const row = await screen.findByRole('link');
    expect(row).not.toHaveAttribute('data-outside-footprint');
    expect(row).toHaveAttribute('data-watched-market', 'dk');
    expect(row.className).not.toContain('border-dashed');
    expect(within(row).getByText('Market we watch: Denmark')).toBeVisible();
    expect(within(row).queryByText(/Outside our scope/)).toBeNull();
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => pill.getAttribute('data-pill'))).toEqual(['brand', 'information', 'negative']);
  });

  it('renders the pills of the row slot order and links to the obligation', async () => {
    serve({ items: [], total: 0 });
    renderIn(<ObligationRow obligation={research} />);
    const row = await screen.findByRole('link');
    expect(row).toHaveAttribute('href', '/inventory/obligations/ob-1');
    expect(row).toHaveAttribute('data-obligation', 'obl-research-payments');
    expect(row).not.toHaveAttribute('data-outside-footprint');
    expect(row.className).toContain('border-line');
    expect(row.className).not.toContain('border-dashed');
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => [pill.getAttribute('data-pill'), pill.textContent])).toEqual([
      ['brand', 'FFFS 2017:2'],
      ['notice', '1 open change'],
      ['brand', 'Research'],
      ['information', 'Custody'],
    ]);
  });

  it('renders a row outside the footprint dashed, with its reason, and falls back to the ref label with no title', async () => {
    serve({ items: [], total: 0 });
    renderIn(<ObligationRow obligation={{ ...adviceOnly, title: null }} />);
    const row = await screen.findByRole('link');
    expect(row).toHaveAttribute('data-outside-footprint', '');
    expect(row.className).toContain('border-dashed');
    expect(within(row).getByRole('heading', { level: 3 })).toHaveTextContent('9 kap.');
    expect(within(row).getByText('Outside our scope: Advice')).toBeVisible();
    // Not binding and a gap, each pill from its slot or kind; no change waits for approval (D-75).
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => pill.getAttribute('data-pill'))).toEqual(['brand', 'information', 'negative']);
  });
});

describe('InventoryScreen', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
    nav.search = '';
    nav.replace.mockReset();
  });

  it('shows the loading state, then the rows and the total', async () => {
    serve({ items: [research, adviceOnly], total: 2 });
    renderIn(<InventoryScreen />);
    expect(screen.getByRole('status')).toHaveAttribute('data-loading-state');
    await waitFor(() => expect(screen.getByText('2 obligations')).toBeVisible());
    // Scoped to the obligation rows: the screen's own "Library updates" link
    // (chunk4-T19) sits in the head, beside the rows, not among them.
    expect(within(document.querySelector('[data-obligation-rows]') as HTMLElement).getAllByRole('link')).toHaveLength(2);
    expect(screen.queryByText(/Showing the first/)).toBeNull();
  });

  it('says so when the page holds fewer rows than the library', async () => {
    serve({ items: [research], total: 42 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('Showing the first 1 of 42.')).toBeVisible();
  });

  it('offers a retry when the read fails', async () => {
    const sent = serve('error');
    renderIn(<InventoryScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/obligations').length).toBeGreaterThan(1));
    expect(screen.getByText('Could not load the inventory')).toBeVisible();
  });

  it('offers to look outside the footprint when a filter matched nothing', async () => {
    nav.search = 'service=advice';
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('No obligations match')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Show outside our scope' })).toHaveAttribute('href', '/inventory?service=advice&scope=all');
  });

  it('drops the offer once the reader is already looking outside the footprint', async () => {
    nav.search = 'service=advice&scope=all';
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('No obligations match')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Show outside our scope' })).toBeNull();
  });

  it.each([['footprint.request'], ['footprint.approve']])('points a holder of %s at the regulatory scope when nothing is in it yet', async (permission) => {
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />, ['library.read', permission]);
    expect(await screen.findByText('The library has nothing in our scope yet')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Check the regulatory scope under Admin' })).toHaveAttribute('href', '/admin/footprint');
  });

  it('shows the empty state without the link to a reader who cannot open the regulatory scope', async () => {
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />, ['library.read']);
    expect(await screen.findByText('The library has nothing in our scope yet')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Check the regulatory scope under Admin' })).toBeNull();
  });

  it('reads as of a date, banners it and goes back to today', async () => {
    nav.search = 'asOf=2026-06-01';
    const sent = serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('Showing the versions in force on 1 Jun 2026.')).toBeVisible();
    expect(sent.find((s) => s.path === '/api/v1/obligations')?.params).toMatchObject({ asOf: '2026-06-01' });
    fireEvent.click(screen.getByRole('button', { name: 'Back to today' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory');
  });

  it('stores a filter as a key in the URL, never a label', async () => {
    serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    const regime = await screen.findByLabelText('Regime');
    await waitFor(() => expect(within(regime).getByRole('option', { name: 'Securities' })).toBeDefined());
    fireEvent.change(regime, { target: { value: 'securities' } });
    expect(nav.replace).toHaveBeenCalledWith('/inventory?regime=securities');

    fireEvent.change(screen.getByLabelText('Duty type'), { target: { value: 'conduct' } });
    expect(nav.replace).toHaveBeenCalledWith('/inventory?dutyType=conduct');
    fireEvent.change(screen.getByLabelText('As of'), { target: { value: '2026-09-16' } });
    expect(nav.replace).toHaveBeenCalledWith('/inventory?asOf=2026-09-16');
    fireEvent.click(screen.getByRole('button', { name: 'Show outside our scope' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?scope=all');
  });

  it('offers the scope as one filter of three values, exactly one pressed', async () => {
    serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    const scope = await screen.findByRole('group', { name: 'Scope' });
    expect(within(scope).getAllByRole('button').map((chip) => [chip.textContent, chip.getAttribute('aria-pressed')])).toEqual([
      ['In our scope', 'true'],
      ['Markets we watch', 'false'],
      ['Show outside our scope', 'false'],
    ]);
    fireEvent.click(within(scope).getByRole('button', { name: 'Markets we watch' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?scope=watched');
  });

  it('asks for what the watched markets add and names each row\'s market under "Markets we watch"', async () => {
    nav.search = 'scope=watched';
    const danish: Obligation = { ...research, id: 'ob-dk', inFootprint: false, jurisdiction: { key: 'dk', kind: 'country', label: 'Denmark' } };
    const sent = serve({ items: [danish], total: 1 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('Market we watch: Denmark')).toBeVisible();
    expect(sent.find((s) => s.path === '/api/v1/obligations')?.params).toMatchObject({ footprint: 'watched' });
    expect(screen.getByRole('button', { name: 'Markets we watch' })).toHaveAttribute('aria-pressed', 'true');
    expect(document.querySelector('[data-obligation-rows] [data-outside-footprint]')).toBeNull();
  });

  it('says the watched markets add nothing, with no offer to look outside, when that view is empty', async () => {
    nav.search = 'service=advice&scope=watched';
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('The markets we watch add nothing here')).toBeVisible();
    expect(screen.queryByText('No obligations match')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Show outside our scope' })).toBeNull();
  });

  it('asks for everything with the reason once "Show outside our scope" is on', async () => {
    nav.search = 'scope=all';
    const sent = serve({ items: [adviceOnly], total: 1 });
    renderIn(<InventoryScreen />);
    await screen.findByRole('link');
    expect(sent.find((s) => s.path === '/api/v1/obligations')?.params).toMatchObject({ footprint: 'all' });
    expect(screen.getByRole('button', { name: 'Show outside our scope' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('lists an instrument filter whose options carry the obligation count, read at the route maximum of 100', async () => {
    const sent = serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    const instrument = await screen.findByLabelText('Instrument');
    await waitFor(() => expect(within(instrument).getByRole('option', { name: 'FFFS 2017:2 (2)' })).toBeDefined());
    // The picker's own read, and not the Instruments tab's page of 20, which only that tab shows.
    expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toEqual([expect.objectContaining({ limit: 100 })]);
    fireEvent.change(instrument, { target: { value: 'fffs-2017-2' } });
    expect(nav.replace).toHaveBeenCalledWith('/inventory?instrument=fffs-2017-2');
  });

  it('keeps an instrument outside our scope as the picked one, by its name, never "All instruments", while it filters', async () => {
    // An instrument outside our scope, reached from its own card: the list is
    // filtered by it, so the picker says so rather than claiming no filter, and
    // names it from the instruments outside our scope, read only for this.
    nav.search = 'instrument=lfd-2005-405';
    const lfd: Instrument = { ...fffs, id: 'in-2', stableKey: 'lfd-2005-405', shortName: 'LFD', inFootprint: false };
    const sent = serve({ items: [], total: 0 }, { items: [fffs], total: 1 }, { items: [fffs, lfd], total: 2 });
    renderIn(<InventoryScreen />);
    const instrument = (await screen.findByLabelText('Instrument')) as HTMLSelectElement;
    await waitFor(() => expect(within(instrument).getByRole('option', { name: 'LFD' })).toHaveProperty('selected', true));
    expect(instrument.value).toBe('lfd-2005-405');
    expect(within(instrument).getByRole('option', { name: 'FFFS 2017:2 (2)' })).toBeDefined();
    expect(within(instrument).queryByRole('option', { name: 'lfd-2005-405' })).toBeNull();
    expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toContainEqual(expect.objectContaining({ footprint: 'all', limit: 100 }));
    expect(sent.find((s) => s.path === '/api/v1/obligations')?.params).toMatchObject({ instrument: 'lfd-2005-405' });
    // Choosing "All instruments" clears it like any other filter.
    fireEvent.change(instrument, { target: { value: '' } });
    expect(nav.replace).toHaveBeenCalledWith('/inventory');
  });

  it('falls back to the key only for an instrument no read names', async () => {
    nav.search = 'instrument=sfs-1999-999';
    const sent = serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    const instrument = (await screen.findByLabelText('Instrument')) as HTMLSelectElement;
    // Neither the options in our scope nor the ones outside it name this key.
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toContainEqual(expect.objectContaining({ footprint: 'all' })));
    await waitFor(() => expect(within(instrument).getByRole('option', { name: 'FFFS 2017:2 (2)' })).toBeDefined());
    expect(instrument.value).toBe('sfs-1999-999');
    expect(within(instrument).getByRole('option', { name: 'sfs-1999-999' })).toHaveProperty('selected', true);
  });

  it('asks for the instruments outside our scope only when the picked one is not an option', async () => {
    nav.search = 'instrument=fffs-2017-2';
    const sent = serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    const instrument = (await screen.findByLabelText('Instrument')) as HTMLSelectElement;
    await waitFor(() => expect(within(instrument).getByRole('option', { name: 'FFFS 2017:2 (2)' })).toHaveProperty('selected', true));
    await screen.findByText('1 obligation');
    expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).not.toContainEqual(expect.objectContaining({ footprint: 'all' }));
  });

  it('switches to the Instruments tab, carrying the tab and the filters in the URL', async () => {
    nav.search = 'regime=securities&scope=all';
    serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    await screen.findByText('1 obligation');
    fireEvent.click(screen.getByRole('tab', { name: 'Instruments' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?tab=instruments&regime=securities&scope=all');
  });

  it('reads the Instruments tab from the URL directly and shows its own rows and count', async () => {
    nav.search = 'tab=instruments';
    serve({ items: [], total: 0 }, { items: [fffs], total: 1 });
    renderIn(<InventoryScreen />);
    await waitFor(() => expect(screen.getByText('1 instrument')).toBeVisible());
    expect(screen.getByRole('tab', { name: 'Instruments' })).toHaveAttribute('aria-selected', 'true');
    const row = within(document.querySelector('[data-instrument-rows]') as HTMLElement).getByRole('link');
    expect(row).toHaveAttribute('href', '/inventory/instruments/in-1');
  });

  it('narrows the Instruments tab by regime, and shows outside the footprint on request', async () => {
    nav.search = 'tab=instruments';
    const sent = serve({ items: [], total: 0 }, { items: [], total: 0 });
    renderIn(<InventoryScreen />);
    await screen.findByText('No instruments match');
    expect(sent.find((s) => s.path === '/api/v1/instruments')?.params).not.toHaveProperty('footprint');
    fireEvent.change(screen.getByLabelText('Regime'), { target: { value: 'securities' } });
    expect(nav.replace).toHaveBeenCalledWith('/inventory?tab=instruments&regime=securities');
    fireEvent.click(screen.getByRole('button', { name: 'Show outside our scope' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?tab=instruments&scope=all');
  });

  it('asks the Instruments tab for what the watched markets add, and says so when they add nothing', async () => {
    nav.search = 'tab=instruments&scope=watched';
    const sent = serve({ items: [], total: 0 }, { items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('The markets we watch add nothing here')).toBeVisible();
    expect(sent.find((s) => s.path === '/api/v1/instruments')?.params).toMatchObject({ footprint: 'watched' });
    expect(screen.queryByRole('link', { name: 'Show outside our scope' })).toBeNull();
  });

  it('asks the Instruments tab for everything once "Show outside our scope" is on', async () => {
    nav.search = 'tab=instruments&scope=all';
    const sent = serve({ items: [], total: 0 }, { items: [{ ...fffs, inFootprint: false }], total: 1 });
    renderIn(<InventoryScreen />);
    await waitFor(() => expect(document.querySelector('[data-instrument-rows]')).not.toBeNull());
    expect(sent.find((s) => s.path === '/api/v1/instruments')?.params).toMatchObject({ footprint: 'all' });
    expect(screen.getByRole('button', { name: 'Show outside our scope' })).toHaveAttribute('aria-pressed', 'true');
    expect(document.querySelector('[data-instrument-rows] [data-outside-footprint]')).not.toBeNull();
  });
});

describe('InstrumentRow', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
    nav.search = '';
    nav.replace.mockReset();
  });

  it('renders the header pills, the name and the meta line', async () => {
    serve({ items: [], total: 0 });
    renderIn(<InstrumentRow instrument={fffs} />);
    const row = await screen.findByRole('link');
    expect(row).toHaveAttribute('href', '/inventory/instruments/in-1');
    expect(row).toHaveAttribute('data-instrument', 'fffs-2017-2');
    expect(row).not.toHaveAttribute('data-outside-footprint');
    expect(within(row).getByRole('heading', { level: 3 })).toHaveTextContent('FFFS 2017:2 om värdepappersrörelse');
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => [pill.getAttribute('data-pill'), pill.textContent])).toEqual([
      ['brand', 'FFFS 2017:2'],
      ['information', 'Supervisory regulation'],
      ['information', 'Binding'],
      ['brand', 'Sweden'],
      ['information', 'Securities'],
    ]);
    expect(within(row).getByText('Finansinspektionen')).toBeVisible();
    expect(within(row).getByText('In force from 3 Jan 2018')).toBeVisible();
    expect(within(row).getByText('Implements MiFID II delegated directive (EU) 2017/593')).toBeVisible();
    expect(within(row).getByText('2 obligations')).toBeVisible();
  });

  it('renders a row outside the footprint dashed, and falls back to the short name with no name', async () => {
    serve({ items: [], total: 0 });
    renderIn(<InstrumentRow instrument={{ ...fffs, name: null, inFootprint: false }} />);
    const row = await screen.findByRole('link');
    expect(row).toHaveAttribute('data-outside-footprint', '');
    expect(row.className).toContain('border-dashed');
    expect(within(row).getByRole('heading', { level: 3 })).toHaveTextContent('FFFS 2017:2');
  });
});

// Bulk tagging (VOC-08; the card's blocks 1 to 12): a holder of vocab.manage selects
// rows on the page, picks one of the bank's tags, sees the server's preview and commits
// the ids that preview showed, in one call. Everyone reads the tags and the tag filter.
describe('bulk tagging on the inventory', () => {
  const third: Obligation = { ...research, id: 'ob-3', stableKey: 'obl-client-assets', refLabel: 'Client assets', title: { text: 'Keep client assets apart', language: 'en', isOriginal: true, isMachine: false }, tenantTags: [] };
  const tagRows = [
    { key: 'custody', kind: null, label: 'Custody', labels: { en: 'Custody' }, usageNote: '', sortOrder: 1, active: true, isSystem: false, isDefault: false, usageCount: 4, extra: {} },
    { key: 'onboarding', kind: null, label: 'Onboarding', labels: { en: 'Onboarding' }, usageNote: '', sortOrder: 2, active: true, isSystem: false, isDefault: false, usageCount: 2, extra: {} },
  ];
  const custody = { key: 'custody', kind: null, label: 'Custody' };

  /** The inventory's reads, the bank's tags, and whatever `write` answers for a POST. */
  function serveBulk(items: Obligation[], write: (sent: Sent) => Answer = () => ({ status: 500 }), tags: typeof tagRows = tagRows) {
    return installAdapter((sent) => {
      if (sent.method === 'post') return write(sent);
      if (sent.path === '/api/v1/obligations') return { status: 200, data: { items, total: items.length } };
      if (sent.path === '/api/v1/instruments') return { status: 200, data: { items: [fffs], total: 1 } };
      if (sent.path === '/api/v1/vocab/tenant_tag') return { status: 200, data: tags };
      if (sent.path === '/api/v1/taxonomy/terms') return { status: 200, data: { items: [], total: 0 } };
      if (sent.path === '/api/v1/me') return { status: 200, data: { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false } };
      return { status: 200, data: [] };
    });
  }

  /** Renders once and hands back a re-render over the same client, for a URL that changed. */
  function renderScreen(permissions: readonly string[]) {
    const { wrapper } = queryWrapper();
    const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
    const tree = () => (
      <Wrapper>
        <PermissionsProvider permissions={permissions}>
          <LocaleProvider locale="en">
            <InventoryScreen />
          </LocaleProvider>
        </PermissionsProvider>
      </Wrapper>
    );
    const view = render(tree());
    return () => view.rerender(tree());
  }

  function box(stableKey: string): HTMLInputElement {
    return document.querySelector(`[data-obligation-select="${stableKey}"]`) as HTMLInputElement;
  }

  async function chooseTag(text: string) {
    const dialog = await screen.findByRole('dialog');
    const input = within(dialog).getByRole('combobox');
    await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(input, { target: { value: text } });
    fireEvent.keyDown(input, { key: 'Enter' });
    return dialog;
  }

  const outcome = (gained: string[], already: string[], skipped = 0) => ({
    status: 200,
    data: { tag: custody, subjectType: 'obligation', gained: { count: gained.length, ids: gained }, alreadyTagged: { count: already.length, ids: already }, skipped: { count: skipped } },
  });

  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
    nav.search = '';
    nav.replace.mockReset();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('shows a member without vocab.manage the tags and the filter, and no checkbox, select-all or Tag', async () => {
    serveBulk([research, adviceOnly]);
    renderScreen(['library.read']);
    await screen.findByText('2 obligations');
    expect(document.querySelectorAll('input[type="checkbox"]')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: 'Tag' })).toBeNull();
    // The bank's tag on the row is an outlined information pill, from the row's facts.
    const pill = within(document.querySelector('[data-obligation="obl-research-payments"]') as HTMLElement).getByText('Custody').closest('[data-pill]');
    expect(pill).toHaveAttribute('data-pill', 'information');
    expect(pill).toHaveAttribute('data-outlined');
    expect(await screen.findByRole('option', { name: 'Custody' })).toBeTruthy();
    expect(screen.getByRole('combobox', { name: 'Our tags' })).toBeTruthy();
  });

  it('previews the selection, commits the ids the preview showed in one call, and shows the server\'s counts', async () => {
    const sent = serveBulk([research, adviceOnly, third], (s) =>
      // The preview skips ob-3; the commit answers what it did.
      s.path === '/api/v1/taggings/preview' ? outcome(['ob-2'], ['ob-1'], 1) : outcome(['ob-2'], ['ob-1']),
    );
    renderScreen(['library.read', 'vocab.manage']);
    await screen.findByText('3 obligations');
    fireEvent.click(box('obl-research-payments'));
    fireEvent.click(box('obl-suitability-statement'));
    fireEvent.click(box('obl-client-assets'));
    expect(screen.getByRole('region', { name: 'Selection' })).toHaveTextContent('3 selected');
    fireEvent.click(screen.getByRole('button', { name: 'Tag' }));
    const dialog = await chooseTag('Cust');
    expect(within(dialog).getByRole('heading', { name: 'Tag 3 obligations' })).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Preview' }));

    await within(dialog).findByRole('heading', { name: 'Add "Custody" to 3 obligations?' });
    const preview = sent.find((s) => s.path === '/api/v1/taggings/preview');
    expect(preview?.body).toEqual({ tagKey: 'custody', subjectType: 'obligation', subjectIds: ['ob-1', 'ob-2', 'ob-3'] });
    expect(sent.filter((s) => s.path === '/api/v1/taggings/batch')).toHaveLength(0);
    expect(document.querySelector('[data-bulk-count="gained"]')).toHaveTextContent('1Would gain the tag');
    expect(document.querySelector('[data-bulk-count="already"]')).toHaveTextContent('1Already carry it');
    expect(document.querySelector('[data-bulk-count="skipped"]')).toHaveTextContent('1Skipped');
    expect(document.querySelector('[data-bulk-preview-row="gains"]')).toHaveTextContent('Give the retail client a suitability statement before an advised trade');
    expect(document.querySelector('[data-bulk-preview-row="carries"]')).toHaveTextContent('Pay for third-party research only under the permitted models');
    // A skipped record is counted and never named.
    expect(within(dialog).queryByText('Keep client assets apart')).toBeNull();
    expect(within(dialog).getByText('1 obligation is left out: you cannot read it any more, or it cannot be tagged.')).toBeTruthy();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Tag 1 obligation' }));
    await screen.findByText('"Custody" added to 1 obligation. 1 already carried it.');
    const batches = sent.filter((s) => s.path === '/api/v1/taggings/batch');
    expect(batches).toHaveLength(1);
    expect(batches[0]?.body).toEqual({ tagKey: 'custody', subjectType: 'obligation', subjectIds: ['ob-2', 'ob-1'] });
    expect(sent.filter((s) => s.path === '/api/v1/taggings')).toHaveLength(0);
    // The selection is cleared once the batch is in.
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(box('obl-research-payments').checked).toBe(false);
    expect(screen.queryByRole('region', { name: 'Selection' })).toBeNull();
  });

  it('keeps the selection through a filter change on the page, counts only rows still in view, and clears it when the page changes', async () => {
    serveBulk([research, adviceOnly]);
    const rerender = renderScreen(['library.read', 'vocab.manage']);
    await screen.findByText('2 obligations');
    fireEvent.click(box('obl-research-payments'));
    fireEvent.click(box('obl-suitability-statement'));
    expect(screen.getByRole('region', { name: 'Selection' })).toHaveTextContent('2 selected');

    // A filter that leaves one of the two in view: that one stays selected, and only it counts.
    serveBulk([research]);
    nav.search = 'regime=securities';
    rerender();
    await waitFor(() => expect(box('obl-research-payments')).not.toBeNull());
    expect(document.querySelector('[data-obligation="obl-suitability-statement"]')).toBeNull();
    expect(box('obl-research-payments').checked).toBe(true);
    expect(screen.getByRole('region', { name: 'Selection' })).toHaveTextContent('1 selected');

    // Another page: the Instruments tab and back. Nothing is selected any more.
    nav.search = 'tab=instruments';
    rerender();
    await screen.findByRole('tab', { name: 'Instruments', selected: true });
    nav.search = 'regime=securities';
    rerender();
    await waitFor(() => expect(box('obl-research-payments')).not.toBeNull());
    expect(box('obl-research-payments').checked).toBe(false);
    expect(screen.queryByRole('region', { name: 'Selection' })).toBeNull();
  });

  it('selects and clears every row on the page from the select-all, mixed while only some are', async () => {
    serveBulk([research, adviceOnly]);
    renderScreen(['library.read', 'vocab.manage']);
    await screen.findByText('2 obligations');
    const all = screen.getByRole('checkbox', { name: 'Select all 2 on this page' }) as HTMLInputElement;
    fireEvent.click(box('obl-research-payments'));
    expect(all.indeterminate).toBe(true);
    fireEvent.click(all);
    expect(box('obl-suitability-statement').checked).toBe(true);
    expect(all.checked).toBe(true);
    fireEvent.click(all);
    expect(box('obl-research-payments').checked).toBe(false);
    fireEvent.click(box('obl-research-payments'));
    fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }));
    expect(box('obl-research-payments').checked).toBe(false);
  });

  it('refuses above the cap before calling', async () => {
    vi.stubEnv('NEXT_PUBLIC_BULK_TAGGING_MAX_RECORDS', '1');
    const sent = serveBulk([research, adviceOnly]);
    renderScreen(['library.read', 'vocab.manage']);
    await screen.findByText('2 obligations');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all 2 on this page' }));
    const tag = screen.getByRole('button', { name: 'Tag' });
    expect(tag).toBeDisabled();
    expect(tag).toHaveAccessibleDescription('You can tag at most 1 obligations at a time. Clear some rows first.');
    fireEvent.click(tag);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(sent.filter((s) => s.method === 'post')).toHaveLength(0);
  });

  it('says there is nothing to add when every selected row already carries the tag, with no commit', async () => {
    const sent = serveBulk([research], () => outcome([], ['ob-1']));
    renderScreen(['library.read', 'vocab.manage']);
    await screen.findByText('1 obligation');
    fireEvent.click(box('obl-research-payments'));
    fireEvent.click(screen.getByRole('button', { name: 'Tag' }));
    const dialog = await chooseTag('Cust');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Preview' }));
    await within(dialog).findByRole('heading', { name: 'Nothing to add' });
    expect(within(dialog).getByText('All 1 already carry "Custody".')).toBeTruthy();
    expect(within(dialog).queryByRole('button', { name: /^Tag / })).toBeNull();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(sent.filter((s) => s.path === '/api/v1/taggings/batch')).toHaveLength(0);
  });

  it.each([
    [422, 'too_many_records', 'Too many at once. Clear some rows and try again.'],
    [422, 'unknown_key', '"Custody" was retired while you were choosing. Pick another tag.'],
    [403, 'permission_denied', 'Your roles no longer include managing vocabularies. Nothing was tagged.'],
  ])('says the server\'s %s %s in its own words', async (status, code, words) => {
    serveBulk([research], () => ({ status, data: { type: 'about:blank', title: 'Refused', status, detail: 'server wording', code } }));
    renderScreen(['library.read', 'vocab.manage']);
    await screen.findByText('1 obligation');
    fireEvent.click(box('obl-research-payments'));
    fireEvent.click(screen.getByRole('button', { name: 'Tag' }));
    const dialog = await chooseTag('Cust');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Preview' }));
    expect(await within(dialog).findByText(words)).toBeTruthy();
    expect(within(dialog).queryByText('server wording')).toBeNull();
  });

  it('offers Try again after a failed commit, and sends the same previewed ids again', async () => {
    let batches = 0;
    const sent = serveBulk([research, adviceOnly], (s) => {
      if (s.path === '/api/v1/taggings/preview') return outcome(['ob-2'], ['ob-1']);
      batches += 1;
      return batches === 1 ? { status: 500 } : outcome(['ob-2'], ['ob-1']);
    });
    renderScreen(['library.read', 'vocab.manage']);
    await screen.findByText('2 obligations');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all 2 on this page' }));
    fireEvent.click(screen.getByRole('button', { name: 'Tag' }));
    const dialog = await chooseTag('Cust');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Preview' }));
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Tag 1 obligation' }));
    expect(await within(dialog).findByText('Could not tag the obligations. Nothing was changed.')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Try again' }));
    await screen.findByText('"Custody" added to 1 obligation. 1 already carried it.');
    const bodies = sent.filter((s) => s.path === '/api/v1/taggings/batch').map((s) => s.body);
    expect(bodies).toEqual([
      { tagKey: 'custody', subjectType: 'obligation', subjectIds: ['ob-2', 'ob-1'] },
      { tagKey: 'custody', subjectType: 'obligation', subjectIds: ['ob-2', 'ob-1'] },
    ]);
  });

  it('filters by one of the bank\'s tags by key, and says so when no obligation carries it', async () => {
    serveBulk([research]);
    const rerender = renderScreen(['library.read']);
    await screen.findByText('1 obligation');
    await screen.findByRole('option', { name: 'Custody' });
    fireEvent.change(screen.getByRole('combobox', { name: 'Our tags' }), { target: { value: 'custody' } });
    expect(nav.replace).toHaveBeenCalledWith('/inventory?tenantTag=custody');

    const sent = serveBulk([]);
    nav.search = 'tenantTag=custody';
    rerender();
    expect(await screen.findByText('No obligations carry this tag')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Clear our tags' })).toHaveAttribute('href', '/inventory');
    expect(sent.find((s) => s.path === '/api/v1/obligations')?.params).toMatchObject({ tenantTag: ['custody'] });
    expect(queryOf(filtersFrom(new URLSearchParams('tenantTag=custody')))).toEqual({ tenantTag: ['custody'] });
  });

  it('shows the filter disabled while the bank has no tags of its own', async () => {
    serveBulk([research], undefined, []);
    renderScreen(['library.read']);
    await screen.findByText('1 obligation');
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Our tags' })).toBeDisabled());
    expect(screen.getByRole('option', { name: 'No tags of our own yet' })).toBeTruthy();
  });

  it('counts only the selected rows that are on the page', () => {
    expect(selectedInView(new Set(['ob-1', 'gone']), [research, adviceOnly]).map((o) => o.id)).toEqual(['ob-1']);
  });
});

// c8-ui-inventory-overlay (REG-01, REG-02, INV-03): the bank's register overlay on the row,
// through register-presentation, and as filters kept in the URL.
describe('the register overlay on the inventory', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
    nav.search = '';
    nav.replace.mockReset();
  });

  const owned: Obligation = {
    ...research,
    id: 'ob-owned',
    applicability: 'applies',
    complianceStatus: { key: 'partly_compliant', kind: 'partly', label: 'Partly compliant' },
    firstLineOwner: { id: 'u-7', name: 'Johan Berg' },
    ownerTeam: { key: 'retail_compliance', kind: null, label: 'Retail compliance' },
  };
  const pills = (obligation: Obligation) => pillsOf(obligation, t).map((pill) => [pill.label, pill.tone]);

  it('puts applicability and compliance status in their slots, after the level and before the open changes, each toned by its kind', () => {
    expect(pills(owned)).toEqual([
      ['FFFS 2017:2', 'brand'],
      ['Applies', 'positive'],
      ['Partly compliant', 'warning'],
      ['1 open change', 'notice'],
      ['Research', 'brand'],
      ['Custody', 'information'],
    ]);
    expect(pills({ ...owned, binding: false, complianceStatus: { key: 'gap', kind: 'gap', label: 'Gap' } }).slice(0, 4)).toEqual([
      ['FFFS 2017:2', 'brand'],
      ['Guidance', 'information'],
      ['Applies', 'positive'],
      ['Gap', 'negative'],
    ]);
  });

  it('says a duty does not apply with no status beside it, and never marks a change waiting for approval', () => {
    const labels = pillsOf({ ...owned, applicability: 'not_applicable', complianceStatus: null, openChangeCount: 0 }, t).map((pill) => pill.label);
    expect(labels).toEqual(['FFFS 2017:2', 'Does not apply', 'Research', 'Custody']);
    expect(labels.join(' ')).not.toMatch(/pending|approval/i);
  });

  it('leaves the columns empty for a duty the bank has not answered, as for a bank with no entries', () => {
    expect(pillsOf(research, t).map((pill) => pill.key)).toEqual(['instrument:fffs-2017-2', 'open-changes', 'library-tag:research', 'tenant-tag:custody']);
    expect(metaOf(research, t, defaultFormatContext)).toEqual(['Advice, Portfolio management', 'Version 2, from 1 Oct 2026', 'Verified 30 Jun 2026']);
  });

  it('ends the meta line with the first-line owner and the owning team', () => {
    expect(metaOf(owned, t, defaultFormatContext).slice(-2)).toEqual(['Johan Berg', 'Retail compliance']);
    expect(metaOf({ ...owned, firstLineOwner: null }, t, defaultFormatContext).at(-1)).toBe('Retail compliance');
  });

  it('keeps "Private to us" first and the bank\'s tags last beside the overlay', () => {
    expect(pillsOf({ ...owned, privateToUs: true }, t).map((pill) => pill.label)).toEqual(['Private to us', 'FFFS 2017:2', 'Applies', 'Partly compliant', '1 open change', 'Research', 'Custody']);
  });

  it('reads the overlay filters from the URL as keys, refuses an applicability it does not know, and sends them to the read', () => {
    const filters = filtersFrom(new URLSearchParams('applicability=applies&complianceStatus=gap&owner=u-7&ownerTeam=retail_compliance'));
    expect(filters).toMatchObject({ applicability: 'applies', complianceStatus: 'gap', owner: 'u-7', ownerTeam: 'retail_compliance' });
    expect(filtersFrom(new URLSearchParams('applicability=pending')).applicability).toBe('');
    expect(searchOf('obligations', filters)).toBe('applicability=applies&complianceStatus=gap&owner=u-7&ownerTeam=retail_compliance');
    expect(queryOf(filters)).toEqual({ applicability: 'applies', complianceStatus: 'gap', owner: 'u-7', ownerTeam: 'retail_compliance' });
    expect(isNarrowed(filtersFrom(new URLSearchParams('ownerTeam=cards')))).toBe(true);
    expect(isNarrowed(filtersFrom(new URLSearchParams('')))).toBe(false);
  });

  it('offers the bank\'s own statuses, people and teams, and stores the key or the member id in the URL', async () => {
    nav.search = 'asOf=2026-09-16';
    const row = (key: string, kind: string | null, label: string) => ({ key, kind, label, labels: { en: label }, usageNote: '', sortOrder: 1, active: true, isSystem: true, isDefault: false, usageCount: 1, extra: {} });
    const sent = installAdapter((request) => {
      if (request.path === '/api/v1/obligations') return { status: 200, data: { items: [owned], total: 1 } };
      if (request.path === '/api/v1/instruments') return { status: 200, data: { items: [fffs], total: 1 } };
      if (request.path === '/api/v1/me') return { status: 200, data: { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false } };
      if (request.path === '/api/v1/taxonomy/terms') return { status: 200, data: { items: [], total: 0 } };
      if (request.path === '/api/v1/reference/people') return { status: 200, data: [{ id: 'u-7', name: 'Johan Berg' }] };
      if (request.path === '/api/v1/vocab/compliance_status') return { status: 200, data: [row('gap', 'gap', 'Gap')] };
      if (request.path === '/api/v1/vocab/team') return { status: 200, data: [row('retail_compliance', null, 'Retail compliance')] };
      return { status: 200, data: [] };
    });
    renderIn(<InventoryScreen />);
    const status = await screen.findByLabelText('Compliance status');
    await waitFor(() => expect(within(status).getByRole('option', { name: 'Gap' })).toBeDefined());
    fireEvent.change(status, { target: { value: 'gap' } });
    expect(nav.replace).toHaveBeenLastCalledWith('/inventory?asOf=2026-09-16&complianceStatus=gap');
    const owner = screen.getByLabelText('Owner');
    await waitFor(() => expect(within(owner).getByRole('option', { name: 'Johan Berg' })).toBeDefined());
    fireEvent.change(owner, { target: { value: 'u-7' } });
    expect(nav.replace).toHaveBeenLastCalledWith('/inventory?asOf=2026-09-16&owner=u-7');
    const team = screen.getByLabelText('Owning team');
    await waitFor(() => expect(within(team).getByRole('option', { name: 'Retail compliance' })).toBeDefined());
    fireEvent.change(team, { target: { value: 'retail_compliance' } });
    expect(nav.replace).toHaveBeenLastCalledWith('/inventory?asOf=2026-09-16&ownerTeam=retail_compliance');
    const applies = screen.getByLabelText('Applies to us');
    expect(within(applies).getAllByRole('option').map((option) => option.textContent)).toEqual(['Applies or not', 'Applies', 'Does not apply', 'Not assessed']);
    fireEvent.change(applies, { target: { value: 'not_applicable' } });
    expect(nav.replace).toHaveBeenLastCalledWith('/inventory?asOf=2026-09-16&applicability=not_applicable');
    // The row itself: the overlay's pills and its owner and team.
    const link = document.querySelector('[data-obligation="obl-research-payments"]') as HTMLElement;
    expect(within(link).getByText('Johan Berg')).toBeVisible();
    expect(within(link).getByText('Partly compliant')).toHaveAttribute('data-pill', 'warning');
    expect(sent.filter((request) => request.path === '/api/v1/obligations').at(-1)?.params).toEqual({ asOf: '2026-09-16', limit: 20, offset: 0 });
  });

  it('asks for the filtered view the URL names, and says nothing matches with the offer to look outside our scope', async () => {
    nav.search = 'applicability=applies&ownerTeam=cards';
    const sent = serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('No obligations match')).toBeVisible();
    expect(sent.find((request) => request.path === '/api/v1/obligations')?.params).toMatchObject({ applicability: 'applies', ownerTeam: 'cards' });
    expect(screen.getByRole('link', { name: 'Show outside our scope' })).toHaveAttribute('href', '/inventory?scope=all&applicability=applies&ownerTeam=cards');
  });
});
