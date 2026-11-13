import { QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { DECIDE_ALL_POLL_MS } from '@/features/applies/hooks';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { renderWith } from '@/shared/testing/render';

import { AppliesScreen, appliesSearch, filterFrom } from './AppliesScreen';

// What applies (REG-01, FP-05; REG-S22): the companies, the address that carries the view,
// the filters, a regulation's rows read only while it is open, the ticks and their bar, the
// three ways into the one dialog and what each sends, the run, every empty state, with and
// without applicability.approve.

const nav = { search: '', replace: vi.fn() };

vi.mock('next/navigation', () => ({
  usePathname: () => '/applies',
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const COMPANIES = '/api/v1/applicability/companies';
const REGULATIONS = '/api/v1/applicability/regulations';
const ROWS = '/api/v1/applicability/rows';
const DECIDE_ALL = '/api/v1/applicability/decide-all';
const UNITS = '/api/v1/tenant/org-units';

const OFFICER = ['register.read', 'applicability.approve'];
const READER = ['register.read'];

const company = (id: string, name: string, offered: number, toDecide: number) => ({ orgUnit: { id, name }, offered, applies: offered - toDecide, notApplicable: 0, underAssessment: toDecide, toDecide });
const bank = company('bank', 'Example Bank AB', 5, 0);
const fonder = company('fonder', 'Example Fonder AB', 20, 13);
const liv = company('liv', 'Example Liv Försäkring AB', 0, 0);

const term = (key: string, label: string, dimension = 'regime') => ({ key, label, kind: null, dimension });
const regulation = (key: string, shortName: string, toDecide: number, offered: number, through: { term: ReturnType<typeof term>; lines: string[] }) => ({
  instrument: { id: `id-${key}`, key, shortName, jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' } },
  offered,
  applies: offered - toDecide,
  notApplicable: 0,
  underAssessment: toDecide,
  toDecide,
  through,
});
const lvf = regulation('sfs-2004-46', 'LVF', 9, 12, { term: term('funds', 'Funds'), lines: ['Tillstånd att driva fondverksamhet'] });
const aml = regulation('sfs-2017-630', 'Penningtvättslagen', 4, 8, { term: term('aml', 'Anti-money laundering'), lines: [] });

const answer = (id: string, refLabel: string, title: string, extra: Record<string, unknown> = {}) => ({
  obligationId: id,
  refLabel,
  title,
  orgUnitId: 'fonder',
  applicability: 'under_assessment',
  reason: null,
  decidedAt: null,
  decidedBy: null,
  version: 0,
  matchedTerms: [],
  ...extra,
});
const sara = { id: 'u-sara', name: 'Sara Lindqvist' };
const lvfRows = [
  answer('o1', '2 kap. 8 §', 'Hold own funds that match the assets under management'),
  answer('o2', '4 kap. 2 §', "Act only in the unit holders' common interest", { applicability: 'applies', reason: 'Licensed.', decidedAt: '2026-09-20T08:00:00Z', decidedBy: sara, version: 1 }),
  answer('o3', '7 kap. 3 §', 'Follow the investor protection rules', { matchedTerms: [term('funds', 'Funds'), term('portfolio_management', 'Portfolio management', 'service_type')] }),
  answer('o4', '7 kap. 9 §', 'Keep a register of unit holders', { reason: 'Waiting for the depositary.', decidedAt: '2026-10-01T08:00:00Z', decidedBy: sara, version: 1 }),
];
const amlRows = [answer('o9', '2 kap. 1 §', 'Assess how the business could be used for money laundering', { matchedTerms: [term('aml', 'Anti-money laundering')] })];

const idle = { status: 'idle', total: 0, set: 0, skipped: 0, refused: 0, refusals: [], stopped: null, applicability: null, instrument: null, orgUnitId: null, startedAt: null, updatedAt: null };
const running = { ...idle, status: 'running', total: 9, set: 3, skipped: 1, applicability: 'applies', instrument: 'sfs-2004-46', orgUnitId: 'fonder', startedAt: '2026-11-13T09:00:00Z', updatedAt: '2026-11-13T09:00:02Z' };
const finished = { ...running, status: 'finished', set: 7, skipped: 1, refused: 1, refusals: [{ obligationId: 'o3', title: 'Follow the investor protection rules', code: 'not_found', detail: 'No longer offered for this company.' }] };

const unit = (id: string, name: string, registerEntry: unknown = null) => ({ id, kind: 'legal_entity', name, parentId: null, orgNumber: '', lei: '', countryCode: 'SE', entityTerm: null, head: null, active: true, version: 1, registerEntry, licences: [] });
const fonderEntry = { authority: { key: 'fi', name: 'Finansinspektionen' }, readAt: '2026-11-11T03:17:00Z' };

interface Script {
  companies?: unknown[];
  regulations?: unknown[];
  run?: () => unknown;
  start?: (sent: Sent) => Answer;
  registerEntry?: unknown;
}

function server({ companies = [bank, fonder, liv], regulations = [lvf, aml], run = () => idle, start, registerEntry = fonderEntry }: Script = {}): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === COMPANIES) return { status: 200, data: companies };
    if (sent.path === UNITS) return { status: 200, data: { items: [unit('bank', 'Example Bank AB'), unit('fonder', 'Example Fonder AB', registerEntry)], total: 2 } };
    if (sent.path === REGULATIONS) {
      const params = sent.params as { limit: number; offset: number };
      return { status: 200, data: { items: params.limit === 1 ? regulations.slice(0, 1) : regulations, total: regulations.length } };
    }
    if (sent.path === ROWS) {
      const params = sent.params as { instrument: string };
      const items = params.instrument === lvf.instrument.key ? lvfRows : amlRows;
      return { status: 200, data: { items, total: items.length } };
    }
    if (sent.path === DECIDE_ALL && sent.method === 'get') return { status: 200, data: run() };
    if (sent.path === DECIDE_ALL && start !== undefined) return start(sent);
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

const reads = (sent: Sent[], path: string) => sent.filter((s) => s.path === path).map((s) => s.params);
const regulationLine = (key: string) => document.querySelector<HTMLElement>(`[data-regulation="${key}"]`)!;
const row = (id: string) => document.querySelector<HTMLElement>(`[data-row="${id}"]`)!;

async function renderScreen(permissions: readonly string[] = OFFICER, locale: 'en' | 'sv' = 'en') {
  renderWith(<AppliesScreen />, { permissions, locale });
  await waitFor(() => expect(document.querySelector('[data-regulations], [data-empty-state], [data-nothing-offered], [data-no-regulation]')).not.toBeNull());
}

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

beforeEach(() => {
  resetApiForTests();
  nav.search = '';
  nav.replace.mockReset();
  window.localStorage.clear();
  vi.mocked(Element.prototype.scrollIntoView).mockClear();
});

describe('the address', () => {
  it('carries the company, the open regulation and a filter other than the default', () => {
    expect(appliesSearch({ company: 'fonder', instrument: null, filter: 'to_decide' })).toBe('company=fonder');
    expect(appliesSearch({ company: 'fonder', instrument: 'sfs-2004-46', filter: 'all' })).toBe('company=fonder&instrument=sfs-2004-46&state=all');
    expect(filterFrom('decided')).toBe('decided');
    expect(filterFrom('nonsense')).toBe('to_decide');
    expect(filterFrom(null)).toBe('to_decide');
  });
});

describe('the companies', () => {
  it('picks the first company with something to decide, and changes company in the address', async () => {
    server();
    await renderScreen();
    expect(screen.getByRole('heading', { level: 1, name: 'What applies' })).toBeInTheDocument();
    const companies = within(screen.getByRole('group', { name: 'Company' }));
    expect(companies.getByRole('button', { name: 'Example Fonder AB 13 to decide' })).toHaveAttribute('aria-pressed', 'true');
    expect(companies.getByRole('button', { name: 'Example Bank AB 0 to decide' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('link', { name: 'Licences' })).toHaveAttribute('href', '/admin/licences');
    fireEvent.click(companies.getByRole('button', { name: 'Example Bank AB 0 to decide' }));
    expect(nav.replace).toHaveBeenCalledWith('/applies?company=bank', { scroll: false });
  });

  it('opens the company the address names, and the first when none has anything to decide', async () => {
    nav.search = 'company=bank';
    server();
    await renderScreen();
    expect(screen.getByRole('button', { name: 'Example Bank AB 0 to decide' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('heading', { name: 'Everything is decided for Example Bank AB.' })).toBeInTheDocument();
  });

  it('shows the one company of a bank by name, with no chips', async () => {
    server({ companies: [fonder] });
    await renderScreen();
    expect(screen.queryByRole('group', { name: 'Company' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Example Fonder AB' })).toBeInTheDocument();
  });

  it('drops the ticks when the company changes', async () => {
    server();
    const { queryClient } = queryWrapper();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <LocaleProvider locale="en">
          <PermissionsProvider permissions={OFFICER}>{children}</PermissionsProvider>
        </LocaleProvider>
      </QueryClientProvider>
    );
    const view = render(<AppliesScreen />, { wrapper });
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Hold own funds that match the assets under management' }));
    expect(screen.getByRole('region', { name: 'Selected obligations' })).toBeInTheDocument();
    // The address names another company, then this one again: it starts with nothing ticked.
    nav.search = 'company=bank';
    view.rerender(<AppliesScreen />);
    expect(await screen.findByRole('heading', { name: 'Everything is decided for Example Bank AB.' })).toBeInTheDocument();
    nav.search = 'company=fonder';
    view.rerender(<AppliesScreen />);
    await screen.findByRole('checkbox', { name: 'Hold own funds that match the assets under management' });
    expect(screen.getByRole('checkbox', { name: 'Hold own funds that match the assets under management' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByRole('region', { name: 'Selected obligations' })).not.toBeInTheDocument();
  });
});

describe('the summary and the filters', () => {
  it('counts what is offered, in how many regulations, and what is left to decide', async () => {
    const sent = server();
    await renderScreen();
    expect(await screen.findByText('20 obligations in 2 regulations · 13 to decide')).toBeInTheDocument();
    const show = within(screen.getByRole('group', { name: 'Show' }));
    expect(show.getByRole('button', { name: 'To decide 13' })).toHaveAttribute('aria-pressed', 'true');
    expect(show.getByRole('button', { name: 'Decided 7' })).toHaveAttribute('aria-pressed', 'false');
    expect(show.getByRole('button', { name: 'All 20' })).toHaveAttribute('aria-pressed', 'false');
    expect(reads(sent, REGULATIONS)).toContainEqual({ orgUnitId: 'fonder', state: 'to_decide', limit: 20, offset: 0 });
    fireEvent.click(show.getByRole('button', { name: 'Decided 7' }));
    expect(nav.replace).toHaveBeenLastCalledWith('/applies?company=fonder&state=decided', { scroll: false });
  });

  it('reads the filter from the address, and All sends no state', async () => {
    nav.search = 'company=fonder&state=all';
    const sent = server();
    await renderScreen();
    expect(screen.getByRole('button', { name: 'All 20' })).toHaveAttribute('aria-pressed', 'true');
    expect(reads(sent, REGULATIONS)).toContainEqual({ orgUnitId: 'fonder', limit: 20, offset: 0 });
    await waitFor(() => expect(reads(sent, ROWS)).toEqual([{ orgUnitId: 'fonder', instrument: 'sfs-2004-46', limit: 20, offset: 0 }]));
  });

  it('finds a regulation on Enter, never on each key, and clears at once when emptied', async () => {
    const sent = server();
    await renderScreen();
    const find = screen.getByRole('searchbox', { name: 'Find a regulation' });
    expect(find).toHaveAttribute('placeholder', 'e.g. penningtvätt');
    fireEvent.change(find, { target: { value: 'penning' } });
    expect(reads(sent, REGULATIONS).some((params) => (params as { q?: string }).q !== undefined)).toBe(false);
    fireEvent.submit(find.closest('form')!);
    await waitFor(() => expect(reads(sent, REGULATIONS)).toContainEqual({ orgUnitId: 'fonder', state: 'to_decide', q: 'penning', limit: 20, offset: 0 }));
    fireEvent.change(find, { target: { value: '' } });
    await waitFor(() => expect(screen.getByRole('link', { name: 'LVF' })).toBeInTheDocument());
  });

  it('says when no regulation matches the search, and nothing is left without claiming nothing is decided', async () => {
    server({ regulations: [] });
    await renderScreen();
    expect(screen.getByText('Nothing to show here.')).toBeInTheDocument();
    expect(screen.queryByText('Nothing is decided for Example Fonder AB yet.')).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Find a regulation' }), { target: { value: 'zzz' } });
    fireEvent.submit(screen.getByRole('search'));
    expect(await screen.findByText('No regulation matches.')).toBeInTheDocument();
  });

  it('says nothing is decided yet only under Decided', async () => {
    nav.search = 'company=fonder&state=decided';
    server({ regulations: [] });
    await renderScreen();
    expect(screen.getByText('Nothing is decided for Example Fonder AB yet.')).toBeInTheDocument();
  });

  it('steps back to the last page that holds anything when a later page comes back empty', async () => {
    const many = Array.from({ length: 21 }, (_, i) => regulation(`reg-${i}`, `Reg ${i}`, 1, 1, { term: term('funds', 'Funds'), lines: [] }));
    // A run finished while page 2 was asked for: what is left fits on page 1.
    let left = 21;
    const sent = installAdapter((s) => {
      if (s.path === COMPANIES) return { status: 200, data: [fonder] };
      if (s.path === REGULATIONS) {
        const { offset, limit } = s.params as { offset: number; limit: number };
        return { status: 200, data: { items: many.slice(0, left).slice(offset, offset + limit), total: left } };
      }
      if (s.path === ROWS) return { status: 200, data: { items: amlRows, total: 1 } };
      if (s.path === DECIDE_ALL) return { status: 200, data: idle };
      return { status: 404, data: { code: 'not_found', detail: 'x' } };
    });
    await renderScreen();
    await screen.findByRole('link', { name: 'Reg 0' });
    left = 20;
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(reads(sent, REGULATIONS)).toContainEqual({ orgUnitId: 'fonder', state: 'to_decide', limit: 20, offset: 20 }));
    expect(await screen.findByRole('link', { name: 'Reg 0' })).toBeInTheDocument();
    expect(screen.queryByText('Nothing to show here.')).not.toBeInTheDocument();
  });
});

describe('the regulations', () => {
  it('lists each with its page, why it is listed and what is left, and reads rows only while open', async () => {
    const sent = server();
    await renderScreen();
    const first = within(regulationLine(lvf.instrument.key));
    expect(first.getByRole('link', { name: 'LVF' })).toHaveAttribute('href', '/inventory/instruments/id-sfs-2004-46');
    expect(first.getByText('From its licence: Tillstånd att driva fondverksamhet')).toBeInTheDocument();
    expect(first.getByText('9 of 12 to decide')).toBeInTheDocument();
    const second = within(regulationLine(aml.instrument.key));
    expect(second.getByText("From the bank's scope: Anti-money laundering")).toBeInTheDocument();
    // The first starts open, the rest closed: only its rows are read.
    await waitFor(() => expect(reads(sent, ROWS)).toEqual([{ orgUnitId: 'fonder', instrument: 'sfs-2004-46', state: 'to_decide', limit: 20, offset: 0 }]));
    expect(second.getByRole('button', { name: /^Penningtvättslagen / })).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(second.getByRole('button', { name: /^Penningtvättslagen / }));
    expect(nav.replace).toHaveBeenLastCalledWith('/applies?company=fonder&instrument=sfs-2017-630', { scroll: false });
    await waitFor(() => expect(reads(sent, ROWS)).toHaveLength(2));
    expect(first.getByRole('button', { name: /^LVF / })).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(first.getByRole('button', { name: /^LVF / }));
    expect(first.getByRole('button', { name: /^LVF / })).toHaveAttribute('aria-expanded', 'false');
  });

  it('opens the regulation the address names and scrolls it into view', async () => {
    nav.search = 'company=fonder&instrument=sfs-2017-630';
    server();
    await renderScreen();
    expect(within(regulationLine(aml.instrument.key)).getByRole('button', { name: /^Penningtvättslagen / })).toHaveAttribute('aria-expanded', 'true');
    expect(within(regulationLine(lvf.instrument.key)).getByRole('button', { name: /^LVF / })).toHaveAttribute('aria-expanded', 'false');
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1));
  });

  it('turns to the page that holds the regulation the address names, opens it and scrolls it into view', async () => {
    const many = Array.from({ length: 25 }, (_, i) => regulation(`reg-${i}`, `Reg ${i}`, 1, 1, { term: term('funds', 'Funds'), lines: [] }));
    nav.search = 'company=fonder&instrument=reg-22';
    const sent = installAdapter((s) => {
      if (s.path === COMPANIES) return { status: 200, data: [fonder] };
      if (s.path === REGULATIONS) {
        const { offset, limit } = s.params as { offset: number; limit: number };
        return { status: 200, data: { items: many.slice(offset, offset + limit), total: many.length } };
      }
      if (s.path === ROWS) return { status: 200, data: { items: amlRows, total: 1 } };
      if (s.path === DECIDE_ALL) return { status: 200, data: idle };
      return { status: 404, data: { code: 'not_found', detail: 'x' } };
    });
    await renderScreen();
    await waitFor(() => expect(within(regulationLine('reg-22')).getByRole('button', { name: /^Reg 22 / })).toHaveAttribute('aria-expanded', 'true'));
    expect(reads(sent, REGULATIONS)).toContainEqual({ orgUnitId: 'fonder', state: 'to_decide', limit: 20, offset: 20 });
    expect(within(regulationLine('reg-20')).getByRole('button', { name: /^Reg 20 / })).toHaveAttribute('aria-expanded', 'false');
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1));
    // Paging back does not pull the page to the named regulation again.
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    expect(await screen.findByRole('link', { name: 'Reg 0' })).toBeInTheDocument();
    expect(within(regulationLine('reg-0')).getByRole('button', { name: /^Reg 0 / })).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens the first regulation when the one the address names is not listed', async () => {
    nav.search = 'company=fonder&instrument=gone';
    server();
    await renderScreen();
    await waitFor(() => expect(within(regulationLine(lvf.instrument.key)).getByRole('button', { name: /^LVF / })).toHaveAttribute('aria-expanded', 'true'));
    expect(within(regulationLine(aml.instrument.key)).getByRole('button', { name: /^Penningtvättslagen / })).toHaveAttribute('aria-expanded', 'false');
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it('draws a row to decide with its box and words, an answered one with its pill, name and date, and what it covers', async () => {
    server();
    await renderScreen();
    await screen.findByRole('checkbox', { name: 'Hold own funds that match the assets under management' });
    expect(within(row('o1')).getByText('2 kap. 8 §')).toHaveClass('font-mono');
    expect(within(row('o1')).getByRole('link', { name: 'Hold own funds that match the assets under management' })).toHaveAttribute('href', '/inventory/obligations/o1');
    expect(within(row('o1')).getByText('to decide')).toBeInTheDocument();
    expect(within(row('o2')).queryByRole('checkbox')).not.toBeInTheDocument();
    expect(within(row('o2')).getByText('Applies')).toHaveAttribute('data-pill', 'positive');
    expect(within(row('o2')).getByText(/^Sara Lindqvist, 20 Sept? 2026$/)).toBeInTheDocument();
    // Parked by a colleague with a reason: answered, never a target.
    expect(within(row('o4')).queryByRole('checkbox')).not.toBeInTheDocument();
    expect(within(row('o4')).getByText('Not assessed')).toHaveAttribute('data-pill');
    // The regulation's own term is not repeated; another is.
    expect(within(row('o3')).getByText('Covers: Portfolio management')).toBeInTheDocument();
    expect(within(row('o1')).queryByText(/^Covers:/)).not.toBeInTheDocument();
  });

  it('says when an open regulation holds nothing in the view, pages a long list, and shows a refused read', async () => {
    const many = Array.from({ length: 21 }, (_, i) => regulation(`reg-${i}`, `Reg ${i}`, 1, 1, { term: term('funds', 'Funds'), lines: [] }));
    const sent = installAdapter((s) => {
      if (s.path === COMPANIES) return { status: 200, data: [fonder] };
      if (s.path === REGULATIONS) return { status: 200, data: { items: many.slice(0, 20), total: 21 } };
      if (s.path === ROWS) return (s.params as { instrument: string }).instrument === 'reg-0' ? { status: 200, data: { items: [], total: 0 } } : { status: 500, data: { code: 'server_error', detail: 'Rows could not be read.' } };
      if (s.path === DECIDE_ALL) return { status: 200, data: idle };
      return { status: 404, data: { code: 'not_found', detail: 'x' } };
    });
    await renderScreen();
    expect(await screen.findByText('Nothing to show here.')).toBeInTheDocument();
    fireEvent.click(within(regulationLine('reg-1')).getByRole('button', { name: /^Reg 1 / }));
    expect(await screen.findByText('Rows could not be read.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(reads(sent, REGULATIONS)).toContainEqual({ orgUnitId: 'fonder', state: 'to_decide', limit: 20, offset: 20 }));
  });

  it('pages the rows of a long regulation', async () => {
    const long = Array.from({ length: 20 }, (_, i) => answer(`r${i}`, `${i} §`, `Duty ${i}`));
    const sent = installAdapter((s) => {
      if (s.path === COMPANIES) return { status: 200, data: [fonder] };
      if (s.path === REGULATIONS) return { status: 200, data: { items: [lvf], total: 1 } };
      if (s.path === ROWS) return { status: 200, data: { items: long, total: 25 } };
      if (s.path === DECIDE_ALL) return { status: 200, data: idle };
      return { status: 404, data: { code: 'not_found', detail: 'x' } };
    });
    await renderScreen();
    await screen.findByText('Duty 0');
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(reads(sent, ROWS)).toContainEqual({ orgUnitId: 'fonder', instrument: 'sfs-2004-46', state: 'to_decide', limit: 20, offset: 20 }));
  });

  it('starts the rows on their first page under a new filter, and steps back from a page a run emptied', async () => {
    const long = Array.from({ length: 25 }, (_, i) => answer(`r${i}`, `${i} §`, `Duty ${i}`));
    let total = 25;
    const sent = installAdapter((s) => {
      if (s.path === COMPANIES) return { status: 200, data: [fonder] };
      if (s.path === REGULATIONS) return { status: 200, data: { items: [lvf], total: 1 } };
      if (s.path === ROWS) {
        const { offset } = s.params as { offset: number };
        return { status: 200, data: { items: long.slice(0, total).slice(offset, offset + 20), total } };
      }
      if (s.path === DECIDE_ALL) return { status: 200, data: idle };
      return { status: 404, data: { code: 'not_found', detail: 'x' } };
    });
    const { queryClient } = queryWrapper();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <LocaleProvider locale="en">
          <PermissionsProvider permissions={OFFICER}>{children}</PermissionsProvider>
        </LocaleProvider>
      </QueryClientProvider>
    );
    const view = render(<AppliesScreen />, { wrapper });
    await screen.findByText('Duty 0');
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByText('Duty 24')).toBeInTheDocument();
    nav.search = 'company=fonder&state=all';
    view.rerender(<AppliesScreen />);
    await waitFor(() => expect(reads(sent, ROWS)).toContainEqual({ orgUnitId: 'fonder', instrument: 'sfs-2004-46', limit: 20, offset: 0 }));
    expect(reads(sent, ROWS)).not.toContainEqual({ orgUnitId: 'fonder', instrument: 'sfs-2004-46', limit: 20, offset: 20 });
    expect(await screen.findByText('Duty 0')).toBeInTheDocument();
    // A run finished meanwhile: what is left fits on page 1, so page 2 comes back empty.
    total = 20;
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(reads(sent, ROWS)).toContainEqual({ orgUnitId: 'fonder', instrument: 'sfs-2004-46', limit: 20, offset: 20 }));
    expect(await screen.findByText('Duty 0')).toBeInTheDocument();
    expect(screen.queryByText('Nothing to show here.')).not.toBeInTheDocument();
  });
});

describe('deciding', () => {
  it('ticks rows into a bar that clears or decides them, through the dialog, with their ids', async () => {
    const sent = server({ start: () => ({ status: 202, data: { ...running, instrument: null, total: 2, set: 0, skipped: 0 } }) });
    await renderScreen();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Hold own funds that match the assets under management' }));
    const bar = within(screen.getByRole('region', { name: 'Selected obligations' }));
    expect(bar.getByText('1 selected')).toBeInTheDocument();
    fireEvent.click(bar.getByRole('button', { name: 'Clear' }));
    expect(screen.queryByRole('region', { name: 'Selected obligations' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Hold own funds that match the assets under management' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Follow the investor protection rules' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Follow the investor protection rules' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Follow the investor protection rules' }));
    expect(screen.getByRole('checkbox', { name: 'Follow the investor protection rules' })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(within(screen.getByRole('region', { name: 'Selected obligations' })).getByRole('button', { name: 'Decide 2' }));
    const dialog = screen.getByRole('dialog', { name: 'Does it apply to Example Fonder AB?' });
    expect(dialog).toHaveAccessibleDescription('2 selected obligations');
    expect(within(dialog).getByLabelText<HTMLTextAreaElement>('Reason').value).toBe(
      "Within the scope of its licence Tillstånd att driva fondverksamhet, which brings Funds into scope. Read from Finansinspektionen's register on 11 Nov 2026.",
    );
    fireEvent.click(within(dialog).getByRole('button', { name: 'Set 2 to Applies' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(sent.find((s) => s.method === 'post' && s.path === DECIDE_ALL)?.body).toEqual({
      orgUnitId: 'fonder',
      obligationIds: ['o1', 'o3'],
      applicability: 'applies',
      reason: "Within the scope of its licence Tillstånd att driva fondverksamhet, which brings Funds into scope. Read from Finansinspektionen's register on 11 Nov 2026.",
    });
    expect(screen.queryByRole('region', { name: 'Selected obligations' })).not.toBeInTheDocument();
    expect(screen.getByText('Setting 2 obligations to Applies')).toBeInTheDocument();
  });

  it("ticks every row to decide on an open regulation's page from its line, mixed when only some are", async () => {
    const sent = server({ start: () => ({ status: 202, data: { ...running, instrument: null, total: 1, set: 0, skipped: 0 } }) });
    await renderScreen();
    const all = await screen.findByRole('checkbox', { name: 'Select all to decide in LVF' });
    // A closed regulation has no rows read, so no box to tick them.
    expect(screen.queryByRole('checkbox', { name: 'Select all to decide in Penningtvättslagen' })).not.toBeInTheDocument();
    expect(all).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(all);
    expect(all).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('checkbox', { name: 'Hold own funds that match the assets under management' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('checkbox', { name: 'Follow the investor protection rules' })).toHaveAttribute('aria-checked', 'true');
    expect(within(screen.getByRole('region', { name: 'Selected obligations' })).getByText('2 selected')).toBeInTheDocument();
    // All but one: the line reads mixed.
    fireEvent.click(screen.getByRole('checkbox', { name: 'Follow the investor protection rules' }));
    expect(all).toHaveAttribute('aria-checked', 'mixed');
    fireEvent.click(within(screen.getByRole('region', { name: 'Selected obligations' })).getByRole('button', { name: 'Decide 1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Set 1 to Applies' }));
    await waitFor(() => expect(sent.find((s) => s.method === 'post' && s.path === DECIDE_ALL)?.body).toMatchObject({ obligationIds: ['o1'] }));
    expect(all).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(all);
    fireEvent.click(all);
    expect(all).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByRole('region', { name: 'Selected obligations' })).not.toBeInTheDocument();
  });

  it("decides one regulation, with its key and the bank's scope as the suggestion", async () => {
    // The company has register facts, but the bank's scope is not read from them.
    const sent = server({ start: () => ({ status: 202, data: running }) });
    await renderScreen();
    fireEvent.click(within(regulationLine(aml.instrument.key)).getByRole('button', { name: 'Decide 4' }));
    const dialog = screen.getByRole('dialog', { name: 'Does it apply to Example Fonder AB?' });
    expect(dialog).toHaveAccessibleDescription('4 obligations in Penningtvättslagen');
    expect(within(dialog).getByLabelText<HTMLTextAreaElement>('Reason').value).toBe("Within the bank's scope Anti-money laundering, which includes Example Fonder AB.");
    fireEvent.click(within(dialog).getByRole('button', { name: 'Does not apply' }));
    fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'The company takes no deposits.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Set 4 to Does not apply' }));
    await waitFor(() => expect(sent.some((s) => s.method === 'post' && s.path === DECIDE_ALL)).toBe(true));
    expect(sent.find((s) => s.method === 'post' && s.path === DECIDE_ALL)?.body).toEqual({ orgUnitId: 'fonder', instrument: 'sfs-2017-630', applicability: 'not_applicable', reason: 'The company takes no deposits.' });
  });

  it('decides everything to decide for the company, over every regulation, and closes on Cancel', async () => {
    const sent = server({ start: () => ({ status: 202, data: running }) });
    await renderScreen();
    const all = await screen.findByRole('button', { name: 'Decide all 13' });
    await waitFor(() => expect(all).toBeEnabled());
    fireEvent.click(all);
    expect(screen.getByRole('dialog')).toHaveAccessibleDescription('13 obligations in 2 regulations');
    expect(screen.getByLabelText<HTMLTextAreaElement>('Reason').value).toBe(
      "Within the scope of Example Fonder AB's licences and the bank's regulatory scope. Read from Finansinspektionen's register on 11 Nov 2026.",
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(all);
    fireEvent.click(screen.getByRole('button', { name: 'Set 13 to Applies' }));
    await waitFor(() => expect(sent.some((s) => s.method === 'post' && s.path === DECIDE_ALL)).toBe(true));
    expect(sent.find((s) => s.method === 'post' && s.path === DECIDE_ALL)?.body).toEqual({
      orgUnitId: 'fonder',
      applicability: 'applies',
      reason: "Within the scope of Example Fonder AB's licences and the bank's regulatory scope. Read from Finansinspektionen's register on 11 Nov 2026.",
    });
    expect(reads(sent, REGULATIONS)).toContainEqual({ orgUnitId: 'fonder', state: 'to_decide', limit: 100, offset: 0 });
  });

  it('suggests the shared basis when every regulation to decide stands on one', async () => {
    server({ regulations: [lvf] });
    await renderScreen();
    const all = await screen.findByRole('button', { name: 'Decide all 13' });
    await waitFor(() => expect(all).toBeEnabled());
    fireEvent.click(all);
    expect(screen.getByRole('dialog')).toHaveAccessibleDescription('13 obligations in 1 regulation');
    expect(screen.getByLabelText<HTMLTextAreaElement>('Reason').value).toMatch(/^Within the scope of its licence Tillstånd att driva fondverksamhet/);
  });

  it('drops the still-running sentence once the earlier run has finished', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let run: unknown = idle;
      server({ run: () => run, start: () => ({ status: 409, data: { code: 'decision_running', detail: 'Running.' } }) });
      await renderScreen();
      fireEvent.click(within(regulationLine(lvf.instrument.key)).getByRole('button', { name: 'Decide 9' }));
      run = running;
      fireEvent.click(screen.getByRole('button', { name: 'Set 9 to Applies' }));
      expect(await screen.findByText('Your earlier decision is still running. When it has finished, decide the rest.')).toBeInTheDocument();
      run = finished;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(DECIDE_ALL_POLL_MS);
      });
      expect(await screen.findByText('7 set to Applies.')).toBeInTheDocument();
      expect(screen.queryByText('Your earlier decision is still running. When it has finished, decide the rest.')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows the running run and says so when an earlier decision is still running', async () => {
    let run: unknown = idle;
    server({ run: () => run, start: () => ({ status: 409, data: { code: 'decision_running', detail: 'Running.' } }) });
    await renderScreen();
    fireEvent.click(within(regulationLine(lvf.instrument.key)).getByRole('button', { name: 'Decide 9' }));
    run = running;
    fireEvent.click(screen.getByRole('button', { name: 'Set 9 to Applies' }));
    expect(await screen.findByText('Your earlier decision is still running. When it has finished, decide the rest.')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(await screen.findByText('Setting 9 obligations to Applies')).toBeInTheDocument();
  });

  it('keeps the dialog open with the reason a start was refused', async () => {
    server({ start: () => ({ status: 404, data: { code: 'not_found', detail: 'Not offered.' } }) });
    await renderScreen();
    fireEvent.click(within(regulationLine(lvf.instrument.key)).getByRole('button', { name: 'Decide 9' }));
    fireEvent.click(screen.getByRole('button', { name: 'Set 9 to Applies' }));
    expect(await screen.findByText('One of these obligations is no longer offered for this company, so nothing was set. Read the page again.')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('draws no box and no Decide button for a member without applicability.approve, and reads no run', async () => {
    const sent = server();
    await renderScreen(READER);
    await waitFor(() => expect(row('o1')).not.toBeNull());
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Decide( all)? \d+$/ })).not.toBeInTheDocument();
    expect(reads(sent, DECIDE_ALL)).toEqual([]);
    expect(reads(sent, REGULATIONS).some((params) => (params as { limit: number }).limit === 100)).toBe(false);
  });
});

describe('the run', () => {
  it('shows a running run with its progress, polls it, and disables every Decide meanwhile', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let run: unknown = running;
      server({ run: () => run });
      await renderScreen();
      const panel = await screen.findByText('Setting 9 obligations to Applies');
      expect(panel).toHaveAttribute('role', 'status');
      expect(screen.getByText('4 of 9')).toBeInTheDocument();
      expect(screen.getByRole('progressbar', { name: 'Obligations set so far' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Decide all 13' })).toBeDisabled();
      expect(within(regulationLine(lvf.instrument.key)).getByRole('button', { name: 'Decide 9' })).toBeDisabled();
      run = finished;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(DECIDE_ALL_POLL_MS);
      });
      expect(await screen.findByText('7 set to Applies.')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('says what a finished run did, what it left and why it stopped, until Done hides it on this visit and the next', async () => {
    server({ run: () => ({ ...finished, stopped: 'reason_expired' }) });
    await renderScreen();
    expect(await screen.findByText('7 set to Applies.')).toBeInTheDocument();
    expect(screen.getByText('1 left as a colleague had answered it.')).toBeInTheDocument();
    expect(screen.getByText('It stopped because the reason was no longer kept. Decide the rest again.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^1 could not be set/ }));
    expect(screen.getByText('Follow the investor protection rules', { selector: 'b' })).toBeInTheDocument();
    expect(screen.getByText('No longer offered for this company.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByText('7 set to Applies.')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('applies.decide-all.dismissed')).toBe(finished.startedAt);
  });

  it('stays hidden on the next visit once dismissed', async () => {
    window.localStorage.setItem('applies.decide-all.dismissed', finished.startedAt);
    server({ run: () => finished });
    await renderScreen();
    await waitFor(() => expect(row('o1')).not.toBeNull());
    expect(screen.queryByText('7 set to Applies.')).not.toBeInTheDocument();
  });

  it("names another company's run, and says each reason a run stops", async () => {
    for (const [stopped, sentence] of [
      ['permission_revoked', 'It stopped because you no longer hold the right to decide what applies.'],
      ['membership_ended', 'It stopped because you are no longer a member of the bank.'],
      ['failed', 'It stopped on an error. Decide the rest again.'],
    ] as const) {
      resetApiForTests();
      server({ run: () => ({ ...finished, orgUnitId: 'bank', applicability: 'not_applicable', refused: 0, refusals: [], skipped: 0, stopped }) });
      const view = renderWith(<AppliesScreen />, { permissions: OFFICER });
      expect(await screen.findByText(sentence)).toBeInTheDocument();
      expect(screen.getByText('For Example Bank AB')).toBeInTheDocument();
      expect(screen.getByText('7 set to Does not apply.')).toBeInTheDocument();
      expect(screen.queryByText(/left as a colleague/)).not.toBeInTheDocument();
      view.unmount();
    }
  });
});

describe('the empty states', () => {
  it('names the next step when the bank has no legal entity yet', async () => {
    server({ companies: [] });
    await renderScreen();
    const empty = screen.getByText('No legal entities yet').closest('[data-empty-state]') as HTMLElement;
    expect(within(empty).getByRole('link', { name: 'Go to Organisation' })).toHaveAttribute('href', '/admin/organisation');
  });

  it("says a company the register offers nothing for, with the way to its licences and, for whoever reaches it, the bank's scope", async () => {
    nav.search = 'company=liv';
    server();
    await renderScreen(OFFICER);
    expect(screen.getByText('The register offers nothing for Example Liv Försäkring AB yet.')).toBeInTheDocument();
    const nothing = within(document.querySelector<HTMLElement>('[data-nothing-offered]')!);
    expect(nothing.getByRole('link', { name: 'Licences' })).toHaveAttribute('href', '/admin/licences');
    expect(nothing.queryByRole('link', { name: 'Regulatory scope' })).not.toBeInTheDocument();
  });

  it("links the bank's scope for someone who reaches it", async () => {
    nav.search = 'company=liv';
    server();
    await renderScreen([...OFFICER, 'footprint.request']);
    expect(within(document.querySelector<HTMLElement>('[data-nothing-offered]')!).getByRole('link', { name: 'Regulatory scope' })).toHaveAttribute('href', '/admin/footprint');
  });

  it('says everything is decided under the default filter, with the way to the decided ones', async () => {
    nav.search = 'company=bank';
    const sent = server();
    await renderScreen();
    const empty = screen.getByRole('heading', { name: 'Everything is decided for Example Bank AB.' }).closest('[data-empty-state]') as HTMLElement;
    expect(within(empty).getByRole('link', { name: 'Show the decided ones' })).toHaveAttribute('href', '/applies?company=bank&state=decided');
    // The heading says it all: no sentence under it repeats it.
    expect(empty.querySelector('p')).toBeNull();
    expect(screen.queryByRole('button', { name: /^Decide all/ })).not.toBeInTheDocument();
    expect(reads(sent, REGULATIONS).some((params) => (params as { limit: number }).limit === 100)).toBe(false);
  });

  it('shows a refused read of the companies and of the regulations', async () => {
    installAdapter((s) => (s.path === COMPANIES ? { status: 500, data: { code: 'server_error', detail: 'Companies could not be read.' } } : { status: 404, data: { code: 'not_found', detail: 'x' } }));
    renderWith(<AppliesScreen />, { permissions: OFFICER });
    expect(await screen.findByText('Companies could not be read.')).toBeInTheDocument();
  });

  it('shows a refused read of the regulations', async () => {
    installAdapter((s) => {
      if (s.path === COMPANIES) return { status: 200, data: [fonder] };
      if (s.path === REGULATIONS) return { status: 500, data: { code: 'server_error', detail: 'Regulations could not be read.' } };
      if (s.path === DECIDE_ALL) return { status: 200, data: idle };
      return { status: 404, data: { code: 'not_found', detail: 'x' } };
    });
    renderWith(<AppliesScreen />, { permissions: OFFICER });
    expect(await screen.findByText('Regulations could not be read.')).toBeInTheDocument();
  });
});

describe('in Swedish', () => {
  it('reads as a Swedish compliance officer writes it', async () => {
    server();
    await renderScreen(OFFICER, 'sv');
    expect(screen.getByRole('heading', { level: 1, name: 'Vad som gäller' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Example Fonder AB 13 att bedöma' })).toBeInTheDocument();
    expect(await screen.findByText('20 skyldigheter i 2 regelverk · 13 att bedöma')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Att bedöma 13' })).toBeInTheDocument();
    expect(within(regulationLine(lvf.instrument.key)).getByText('9 av 12 att bedöma')).toBeInTheDocument();
    expect(await screen.findAllByText('att bedöma')).not.toHaveLength(0);
  });
});
