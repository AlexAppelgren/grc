import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { InstrumentRow } from './InstrumentRow';
import { InventoryScreen, filtersFrom, isNarrowed, queryOf, searchOf } from './InventoryScreen';
import { ObligationRow, factsOf, metaOf } from './ObligationRow';
import type { Instrument, Obligation } from '@/features/library/types';
import type { SearchHit } from '@/features/search/types';
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
  pendingApplicability: null,
  complianceStatus: null,
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
  pendingApplicability: true,
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
  lastVerifiedAt: '2026-06-30',
  sourceUrl: 'https://www.fi.se/en/published/regulations/2017/fffs-20172/',
};

const regimes = [
  { dimension: { key: 'regime' }, key: 'securities', kind: null, label: 'Securities' },
  { dimension: { key: 'regime' }, key: 'insurance', kind: null, label: 'Insurance' },
];
const services = [
  { dimension: { key: 'service_type' }, key: 'advice', kind: null, label: 'Advice' },
  { dimension: { key: 'service_type' }, key: 'custody', kind: null, label: 'Custody' },
];
/** The bank's regulatory scope: securities only; services restrict nothing, so every one is offered. */
const footprint = {
  dimensions: [
    { dimension: { key: 'regime', kind: null, label: 'Regime' }, restrictsFootprint: true, terms: [{ key: 'securities', kind: null, label: 'Securities' }], allSelected: false },
    { dimension: { key: 'service_type', kind: null, label: 'Service' }, restrictsFootprint: true, terms: [], allSelected: false },
  ],
  pendingRequest: null,
  markets: [],
};

const obligationHit: SearchHit = {
  type: 'obligation',
  id: 'ob-1',
  title: 'Assess appropriateness before non-advised trades',
  snippet: 'Before providing a non-advised service, the institution warns when the appropriateness test fails.',
  matchKind: 'both',
  score: 0.9,
  instrumentShortName: 'LVM',
  binding: true,
  validFrom: '2026-01-01',
  validTo: null,
  versionNo: 1,
  urgency: null,
};
const provisionHit: SearchHit = { ...obligationHit, type: 'provision', id: 'prov-1', title: '9 kap. Protection of clients', matchKind: 'keyword', versionNo: null, validFrom: null };

/** Opens the Filters sheet and answers the dialog. */
async function openFilters() {
  fireEvent.click(await screen.findByRole('button', { name: 'Filters' }));
  return screen.findByRole('dialog', { name: 'Filters' });
}

/**
 * The server: /me for the format context, the taxonomy and vocabulary reads for the filters, and the page.
 * `outsidePage` answers the instrument reads that lift the footprint filter; by default the same page.
 */
function serve(
  page: { items: Obligation[]; total: number } | 'error',
  instrumentPage: { items: Instrument[]; total: number } = { items: [fffs], total: 1 },
  outsidePage: { items: Instrument[]; total: number } = instrumentPage,
  hits: SearchHit[] = [],
) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/search') return { status: 200, data: { items: hits, asOf: '2026-09-25' } };
    if (sent.path === '/api/v1/tenant/footprint') return { status: 200, data: footprint };
    if (sent.path === '/api/v1/obligations') return page === 'error' ? { status: 500 } : { status: 200, data: page };
    if (sent.path === '/api/v1/instruments') {
      const outside = (sent.params as { footprint?: string } | null)?.footprint === 'all';
      return { status: 200, data: outside ? outsidePage : instrumentPage };
    }
    if (sent.path === '/api/v1/me') return { status: 200, data: { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false } };
    if (sent.path === '/api/v1/taxonomy/terms') {
      const items = (sent.params as { dimension?: string } | null)?.dimension === 'service_type' ? services : regimes;
      return { status: 200, data: { items, total: items.length } };
    }
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
    });
    expect(filtersFrom(new URLSearchParams(''))).toEqual({ instrument: '', regime: '', service: '', dutyType: '', asOf: '', scope: 'in' });
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
      complianceStatus: undefined,
      changeWaitingForApproval: false,
      openChangeCount: 1,
      libraryTags: [{ key: 'research', kind: null, label: 'Research' }],
    });
    expect(factsOf(adviceOnly)).toMatchObject({ binding: false, changeWaitingForApproval: true, complianceStatus: { kind: 'gap' } });
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
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => pill.getAttribute('data-pill'))).toEqual(['brand', 'information', 'negative', 'warning']);
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
    // Not binding, an applicability change waiting, and a gap: each pill from its slot or kind.
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => pill.getAttribute('data-pill'))).toEqual(['brand', 'information', 'negative', 'warning']);
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

  it('offers every item when a filter matched nothing', async () => {
    nav.search = 'service=advice';
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('No obligations match')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Show all items' })).toHaveAttribute('href', '/inventory?service=advice&scope=all');
  });

  it('drops the offer once the reader is already looking outside the footprint', async () => {
    nav.search = 'service=advice&scope=all';
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('No obligations match')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Show all items' })).toBeNull();
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

  it('stores a filter chosen in the sheet as a key in the URL, never a label', async () => {
    serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    const sheet = await openFilters();
    fireEvent.click(await within(within(sheet).getByRole('group', { name: 'Regime' })).findByRole('button', { name: 'Securities' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?regime=securities');

    fireEvent.click(await within(within(sheet).getByRole('group', { name: 'Duty type' })).findByRole('button', { name: 'Conduct' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?dutyType=conduct');
    fireEvent.change(within(sheet).getByLabelText('As of'), { target: { value: '2026-09-16' } });
    expect(nav.replace).toHaveBeenCalledWith('/inventory?asOf=2026-09-16');
    // Done only closes: every change above applied at once.
    fireEvent.click(within(sheet).getByRole('button', { name: 'Done' }));
    expect(screen.queryByRole('dialog', { name: 'Filters' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show all items' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?scope=all');
  });

  it('clears a pressed value when it is pressed again, and everything with "Clear all"', async () => {
    nav.search = 'regime=securities&asOf=2026-06-01';
    serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    const sheet = await openFilters();
    const securities = await within(within(sheet).getByRole('group', { name: 'Regime' })).findByRole('button', { name: 'Securities' });
    expect(securities).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(securities);
    expect(nav.replace).toHaveBeenCalledWith('/inventory?asOf=2026-06-01');
    fireEvent.click(within(sheet).getByRole('button', { name: 'Clear all' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory');
  });

  it('offers only the regimes inside the scope, and every one under "Show all items"', async () => {
    serve({ items: [research], total: 1 });
    const { unmount } = renderIn(<InventoryScreen />);
    let regime = within(await openFilters()).getByRole('group', { name: 'Regime' });
    await waitFor(() => expect(within(regime).getAllByRole('button').map((chip) => chip.textContent)).toEqual(['Securities']));
    // Services restrict nothing in this scope, so every one is offered.
    await waitFor(() => expect(within(screen.getByRole('group', { name: 'Service' })).getAllByRole('button').map((chip) => chip.textContent)).toEqual(['Advice', 'Custody']));
    unmount();

    nav.search = 'scope=all';
    renderIn(<InventoryScreen />);
    regime = within(await openFilters()).getByRole('group', { name: 'Regime' });
    await waitFor(() => expect(within(regime).getAllByRole('button').map((chip) => chip.textContent)).toEqual(['Securities', 'Insurance']));
  });

  it('shows each set filter as a chip that removes it, then "Clear filters" for all of them', async () => {
    nav.search = 'regime=securities&dutyType=conduct';
    serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    await waitFor(() => expect([...document.querySelectorAll('[data-set-filter]')].map((chip) => chip.textContent)).toEqual(['Securities', 'Conduct']));
    fireEvent.click(screen.getByRole('button', { name: 'Remove the Regime filter, Securities' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?dutyType=conduct');
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory');
  });

  it('offers the scope as one filter of three values, exactly one pressed', async () => {
    serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    const scope = await screen.findByRole('group', { name: 'Scope' });
    expect(within(scope).getAllByRole('button').map((chip) => [chip.textContent, chip.getAttribute('aria-pressed')])).toEqual([
      ['My scope', 'true'],
      ['Markets we watch', 'false'],
      ['Show all items', 'false'],
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
    expect(screen.queryByRole('link', { name: 'Show all items' })).toBeNull();
  });

  it('asks for everything with the reason once "Show all items" is on', async () => {
    nav.search = 'scope=all';
    const sent = serve({ items: [adviceOnly], total: 1 });
    renderIn(<InventoryScreen />);
    await waitFor(() => expect(document.querySelector('[data-obligation-rows] [data-outside-footprint]')).not.toBeNull());
    expect(sent.find((s) => s.path === '/api/v1/obligations')?.params).toMatchObject({ footprint: 'all' });
    expect(screen.getByRole('button', { name: 'Show all items' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('reads the instrument options, each with its obligation count, at the route maximum of 100, only once the sheet opens', async () => {
    const sent = serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    await screen.findByText('1 obligation');
    // Nothing is set and the sheet is shut, so a hundred instruments are not read.
    expect(sent.filter((s) => s.path === '/api/v1/instruments')).toEqual([]);
    const picker = within(within(await openFilters()).getByRole('group', { name: 'Instrument' }));
    const option = await picker.findByRole('button', { name: 'FFFS 2017:2 (2)' });
    expect(picker.getByRole('button', { name: 'All instruments' })).toHaveAttribute('aria-pressed', 'true');
    expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toEqual([expect.objectContaining({ limit: 100 })]);
    fireEvent.click(option);
    expect(nav.replace).toHaveBeenCalledWith('/inventory?instrument=fffs-2017-2');
  });

  it('finds an instrument by its name inside the sheet', async () => {
    const lvm: Instrument = { ...fffs, id: 'in-3', stableKey: 'sfs-2007-528', shortName: 'LVM' };
    serve({ items: [research], total: 1 }, { items: [fffs, lvm], total: 2 });
    renderIn(<InventoryScreen />);
    const picker = within(within(await openFilters()).getByRole('group', { name: 'Instrument' }));
    await picker.findByRole('button', { name: 'LVM (2)' });
    fireEvent.change(picker.getByRole('searchbox', { name: 'Find an instrument' }), { target: { value: 'lv' } });
    expect(picker.queryByRole('button', { name: 'FFFS 2017:2 (2)' })).toBeNull();
    expect(picker.getByRole('button', { name: 'LVM (2)' })).toBeVisible();
  });

  it('names an instrument outside our scope in its chip while it filters, read from the instruments outside it', async () => {
    // An instrument outside our scope, reached from its own card: the list is
    // filtered by it, so the chip names it from the instruments outside our
    // scope, read only for this.
    nav.search = 'instrument=lfd-2005-405';
    const lfd: Instrument = { ...fffs, id: 'in-2', stableKey: 'lfd-2005-405', shortName: 'LFD', inFootprint: false };
    const sent = serve({ items: [], total: 0 }, { items: [fffs], total: 1 }, { items: [fffs, lfd], total: 2 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByRole('button', { name: 'Remove the Instrument filter, LFD' })).toBeVisible();
    expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toContainEqual(expect.objectContaining({ footprint: 'all', limit: 100 }));
    expect(sent.find((s) => s.path === '/api/v1/obligations')?.params).toMatchObject({ instrument: 'lfd-2005-405' });
    fireEvent.click(screen.getByRole('button', { name: 'Remove the Instrument filter, LFD' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory');
  });

  it('falls back to the key only for an instrument no read names', async () => {
    nav.search = 'instrument=sfs-1999-999';
    const sent = serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    // Neither the options in our scope nor the ones outside it name this key.
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toContainEqual(expect.objectContaining({ footprint: 'all' })));
    expect(await screen.findByRole('button', { name: 'Remove the Instrument filter, sfs-1999-999' })).toBeVisible();
  });

  it('asks for the instruments outside our scope only when the picked one is not an option', async () => {
    nav.search = 'instrument=fffs-2017-2';
    const sent = serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByRole('button', { name: 'Remove the Instrument filter, FFFS 2017:2' })).toBeVisible();
    await screen.findByText('1 obligation');
    expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).not.toContainEqual(expect.objectContaining({ footprint: 'all' }));
  });

  it('searches inside the scope and every filter that is set, over obligations and provisions, and Clear returns the list', async () => {
    nav.search = 'instrument=fffs-2017-2&regime=securities&dutyType=conduct&asOf=2026-06-01&scope=watched';
    const sent = serve({ items: [research], total: 1 }, undefined, undefined, [obligationHit, provisionHit]);
    renderIn(<InventoryScreen />, ['library.read', 'search.use']);
    fireEvent.change(await screen.findByRole('searchbox', { name: 'Search the inventory' }), { target: { value: ' appropriateness ' } });
    fireEvent.submit(screen.getByRole('search'));
    expect(await screen.findByText('2 results')).toBeVisible();
    expect(sent.find((s) => s.path === '/api/v1/search')?.body).toEqual({
      q: 'appropriateness',
      limit: 20,
      types: ['obligation', 'provision'],
      asOf: '2026-06-01',
      filters: { footprint: 'watched', instrument: 'fffs-2017-2', term: ['regime:securities'], dutyType: 'conduct' },
    });
    const rows = document.querySelector('[data-search-rows]') as HTMLElement;
    expect(within(rows).getByRole('link')).toHaveAttribute('href', '/inventory/obligations/ob-1');
    expect(rows.querySelector('[data-hit-type="provision"]')).toHaveTextContent('9 kap. Protection of clients');
    expect(within(rows).getAllByText('appropriateness')[0]?.tagName).toBe('MARK');
    // The words typed are the bank's own: they never reach the address bar.
    expect(nav.replace).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Clear the search' }));
    expect(await screen.findByRole('link', { name: /Pay for third-party research/ })).toBeVisible();
    expect(document.querySelector('[data-search-rows]')).toBeNull();
  });

  it('says a search matched nothing and offers every item', async () => {
    serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />, ['library.read', 'search.use']);
    fireEvent.change(await screen.findByRole('searchbox', { name: 'Search the inventory' }), { target: { value: 'crypto custody' } });
    fireEvent.submit(screen.getByRole('search'));
    expect(await screen.findByText('No match in the inventory')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Show all items' })).toHaveAttribute('href', '/inventory?scope=all');
  });

  it('shows the obligations search only to a reader who may search, and the instruments search to every reader', async () => {
    serve({ items: [research], total: 1 });
    const { unmount } = renderIn(<InventoryScreen />, ['library.read']);
    await screen.findByText('1 obligation');
    expect(screen.queryByRole('searchbox', { name: 'Search the inventory' })).toBeNull();
    unmount();

    nav.search = 'tab=instruments';
    renderIn(<InventoryScreen />, ['library.read']);
    expect(await screen.findByRole('searchbox', { name: 'Search the inventory' })).toBeVisible();
  });

  it('finds instruments by reference or name on the Instruments tab', async () => {
    nav.search = 'tab=instruments';
    const sent = serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    const box = await screen.findByRole('searchbox', { name: 'Search the inventory' });
    expect(box).toHaveAttribute('placeholder', 'Find an instrument by reference or name');
    fireEvent.change(box, { target: { value: 'FFFS' } });
    fireEvent.submit(screen.getByRole('search'));
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toContainEqual(expect.objectContaining({ q: 'FFFS' })));
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

  it('narrows the Instruments tab by regime from its sheet, and shows every item on request', async () => {
    nav.search = 'tab=instruments';
    const sent = serve({ items: [], total: 0 }, { items: [], total: 0 });
    renderIn(<InventoryScreen />);
    await screen.findByText('No instruments match');
    expect(sent.find((s) => s.path === '/api/v1/instruments')?.params).not.toHaveProperty('footprint');
    const sheet = await openFilters();
    expect(within(sheet).queryByRole('group', { name: 'Duty type' })).toBeNull();
    fireEvent.click(await within(within(sheet).getByRole('group', { name: 'Regime' })).findByRole('button', { name: 'Securities' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?tab=instruments&regime=securities');
    fireEvent.click(within(sheet).getByRole('button', { name: 'Close filters' }));
    fireEvent.click(screen.getByRole('button', { name: 'Show all items' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?tab=instruments&scope=all');
  });

  it('asks the Instruments tab for what the watched markets add, and says so when they add nothing', async () => {
    nav.search = 'tab=instruments&scope=watched';
    const sent = serve({ items: [], total: 0 }, { items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('The markets we watch add nothing here')).toBeVisible();
    expect(sent.find((s) => s.path === '/api/v1/instruments')?.params).toMatchObject({ footprint: 'watched' });
    expect(screen.queryByRole('link', { name: 'Show all items' })).toBeNull();
  });

  it('asks the Instruments tab for everything once "Show all items" is on', async () => {
    nav.search = 'tab=instruments&scope=all';
    const sent = serve({ items: [], total: 0 }, { items: [{ ...fffs, inFootprint: false }], total: 1 });
    renderIn(<InventoryScreen />);
    await waitFor(() => expect(document.querySelector('[data-instrument-rows]')).not.toBeNull());
    expect(sent.find((s) => s.path === '/api/v1/instruments')?.params).toMatchObject({ footprint: 'all' });
    expect(screen.getByRole('button', { name: 'Show all items' })).toHaveAttribute('aria-pressed', 'true');
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
