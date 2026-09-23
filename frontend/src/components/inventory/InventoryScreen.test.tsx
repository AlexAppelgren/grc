import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { InstrumentRow } from './InstrumentRow';
import { InventoryScreen, filtersFrom, isNarrowed, queryOf, searchOf } from './InventoryScreen';
import { ObligationRow, factsOf, metaOf } from './ObligationRow';
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
  version: { versionNumber: 1, effectiveFrom: { date: '2018-01-03', precision: 'day' } },
  upcomingVersion: { versionNumber: 2, effectiveFrom: { date: '2026-10-01', precision: 'day' } },
  inFootprint: true,
  outsideReason: [],
  lastVerifiedAt: '2026-06-30',
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

function renderIn(node: ReactNode) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(<Wrapper>{<LocaleProvider locale="en">{node}</LocaleProvider>}</Wrapper>);
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
      const outside = (sent.params as { outsideFootprint?: boolean } | null)?.outsideFootprint === true;
      return { status: 200, data: outside ? outsidePage : instrumentPage };
    }
    if (sent.path === '/api/v1/me') return { status: 200, data: { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false } };
    if (sent.path === '/api/v1/taxonomy/terms') return { status: 200, data: { items: [{ dimension: { key: 'regime' }, key: 'securities', kind: null, label: 'Securities' }], total: 1 } };
    return { status: 200, data: [{ key: 'conduct', kind: null, label: 'Conduct', labels: { en: 'Conduct' }, usageNote: '', sortOrder: 1, active: true, isSystem: true, isDefault: true, usageCount: 2, extra: {} }] };
  });
}

describe('inventory filters in the URL', () => {
  it('reads keys and a plain date, and writes them back without the ones that are not set', () => {
    expect(filtersFrom(new URLSearchParams('instrument=fffs-2017-2&regime=securities&service=advice&dutyType=conduct&asOf=2026-09-16&outside=true'))).toEqual({
      instrument: 'fffs-2017-2',
      regime: 'securities',
      service: 'advice',
      dutyType: 'conduct',
      asOf: '2026-09-16',
      outsideFootprint: true,
    });
    expect(filtersFrom(new URLSearchParams(''))).toEqual({ instrument: '', regime: '', service: '', dutyType: '', asOf: '', outsideFootprint: false });
    // Anything but the exact "true" leaves the footprint filter on.
    expect(filtersFrom(new URLSearchParams('outside=1')).outsideFootprint).toBe(false);
    expect(
      searchOf('obligations', { instrument: 'fffs-2017-2', regime: 'securities', service: 'advice', dutyType: 'conduct', asOf: '2026-09-16', outsideFootprint: true }),
    ).toBe('instrument=fffs-2017-2&regime=securities&service=advice&dutyType=conduct&asOf=2026-09-16&outside=true');
    expect(searchOf('obligations', { instrument: '', regime: '', service: '', dutyType: '', asOf: '', outsideFootprint: false })).toBe('');
    // The Instruments tab rides in the same URL, as its own key.
    expect(searchOf('instruments', { instrument: '', regime: '', service: '', dutyType: '', asOf: '', outsideFootprint: false })).toBe('tab=instruments');
  });

  it('turns a scope filter into a dimension:key term and leaves the rest of the query out', () => {
    expect(queryOf({ instrument: '', regime: 'securities', service: 'advice', dutyType: 'conduct', asOf: '2026-09-16', outsideFootprint: true })).toEqual({
      term: ['regime:securities', 'service_type:advice'],
      dutyType: 'conduct',
      asOf: '2026-09-16',
      outsideFootprint: true,
    });
    expect(queryOf({ instrument: 'fffs-2017-2', regime: '', service: '', dutyType: '', asOf: '', outsideFootprint: false })).toEqual({ instrument: 'fffs-2017-2' });
    expect(queryOf({ instrument: '', regime: '', service: 'advice', dutyType: '', asOf: '', outsideFootprint: false })).toEqual({ term: ['service_type:advice'] });
    expect(queryOf({ instrument: '', regime: '', service: '', dutyType: '', asOf: '', outsideFootprint: false })).toEqual({});
    expect(isNarrowed({ instrument: '', regime: '', service: '', dutyType: '', asOf: '', outsideFootprint: true })).toBe(false);
    expect(isNarrowed({ instrument: '', regime: '', service: '', dutyType: '', asOf: '2026-09-16', outsideFootprint: false })).toBe(true);
    expect(isNarrowed({ instrument: '', regime: '', service: '', dutyType: 'conduct', asOf: '', outsideFootprint: false })).toBe(true);
    expect(isNarrowed({ instrument: '', regime: 'securities', service: '', dutyType: '', asOf: '', outsideFootprint: false })).toBe(true);
    expect(isNarrowed({ instrument: '', regime: '', service: 'advice', dutyType: '', asOf: '', outsideFootprint: false })).toBe(true);
    expect(isNarrowed({ instrument: 'fffs-2017-2', regime: '', service: '', dutyType: '', asOf: '', outsideFootprint: false })).toBe(true);
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

  it('names the terms that put a row outside the footprint, and leaves out what the row does not carry', () => {
    expect(metaOf(adviceOnly, t, defaultFormatContext)).toEqual(['Advice, Portfolio management', 'Outside our scope: Advice']);
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

  it('offers to look outside the footprint when a filter matched nothing', async () => {
    nav.search = 'service=advice';
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('No obligations match')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Show outside our scope' })).toHaveAttribute('href', '/inventory?service=advice&outside=true');
  });

  it('drops the offer once the reader is already looking outside the footprint', async () => {
    nav.search = 'service=advice&outside=true';
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('No obligations match')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Show outside our scope' })).toBeNull();
  });

  it('points at the regulatory scope when nothing is in it yet', async () => {
    serve({ items: [], total: 0 });
    renderIn(<InventoryScreen />);
    expect(await screen.findByText('The library has nothing in our scope yet')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Check the regulatory scope under Admin' })).toHaveAttribute('href', '/admin/footprint');
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
    expect(nav.replace).toHaveBeenCalledWith('/inventory?outside=true');
  });

  it('asks for everything with the reason once "Show outside our scope" is on', async () => {
    nav.search = 'outside=true';
    const sent = serve({ items: [adviceOnly], total: 1 });
    renderIn(<InventoryScreen />);
    await screen.findByRole('link');
    expect(sent.find((s) => s.path === '/api/v1/obligations')?.params).toMatchObject({ outsideFootprint: true });
    expect(screen.getByRole('button', { name: 'Show outside our scope' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('lists an instrument filter whose options carry the obligation count, read at the route maximum of 100', async () => {
    const sent = serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    const instrument = await screen.findByLabelText('Instrument');
    await waitFor(() => expect(within(instrument).getByRole('option', { name: 'FFFS 2017:2 (2)' })).toBeDefined());
    // The picker's own read, not the Instruments tab's page of 20.
    expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toContainEqual(expect.objectContaining({ limit: 100 }));
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
    expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toContainEqual(expect.objectContaining({ outsideFootprint: true, limit: 100 }));
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
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).toContainEqual(expect.objectContaining({ outsideFootprint: true })));
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
    expect(sent.filter((s) => s.path === '/api/v1/instruments').map((s) => s.params)).not.toContainEqual(expect.objectContaining({ outsideFootprint: true }));
  });

  it('switches to the Instruments tab, carrying the tab and the filters in the URL', async () => {
    nav.search = 'regime=securities&outside=true';
    serve({ items: [research], total: 1 });
    renderIn(<InventoryScreen />);
    await screen.findByText('1 obligation');
    fireEvent.click(screen.getByRole('tab', { name: 'Instruments' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?tab=instruments&regime=securities&outside=true');
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
    expect(sent.find((s) => s.path === '/api/v1/instruments')?.params).not.toHaveProperty('outsideFootprint');
    fireEvent.change(screen.getByLabelText('Regime'), { target: { value: 'securities' } });
    expect(nav.replace).toHaveBeenCalledWith('/inventory?tab=instruments&regime=securities');
    fireEvent.click(screen.getByRole('button', { name: 'Show outside our scope' }));
    expect(nav.replace).toHaveBeenCalledWith('/inventory?tab=instruments&outside=true');
  });

  it('asks the Instruments tab for everything once "Show outside our scope" is on', async () => {
    nav.search = 'tab=instruments&outside=true';
    const sent = serve({ items: [], total: 0 }, { items: [{ ...fffs, inFootprint: false }], total: 1 });
    renderIn(<InventoryScreen />);
    await waitFor(() => expect(document.querySelector('[data-instrument-rows]')).not.toBeNull());
    expect(sent.find((s) => s.path === '/api/v1/instruments')?.params).toMatchObject({ outsideFootprint: true });
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
