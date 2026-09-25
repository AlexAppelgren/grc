import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { framesOf, sseResponse, stubFetch } from '@/features/search/ask-testing';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { api, tokenStore } from '@/shared/utils/api-client';

import { EMPTY_SEARCH_FILTERS, SearchScreen, filtersFrom, requestOf, searchOf } from './SearchScreen';

// /search (design/screens/tenant-search.html): the query never reaches the
// URL, every other filter does, each hit's pill contract and link follow
// its type, and every state the card names renders.

const nav = { search: '', replace: vi.fn() };

vi.mock('next/navigation', () => ({
  usePathname: () => '/search',
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

function shell(children: ReactNode): ReactNode {
  const { wrapper: Query } = queryWrapper();
  return (
    <Query>
      <LocaleProvider locale="en">{children}</LocaleProvider>
    </Query>
  );
}

function renderScreen(): void {
  render(shell(<SearchScreen />));
}

const obligationHit = {
  type: 'obligation' as const,
  id: 'ob-1',
  title: 'Assess appropriateness before non-advised trades',
  snippet: 'Before providing a non-advised service, the institution asks about onboarding.',
  matchKind: 'both' as const,
  score: 0.9,
  instrumentShortName: 'FFFS 2017:2',
  binding: true,
  validFrom: '2026-01-01',
  validTo: null,
  versionNo: 2,
  urgency: null,
};

const changeHit = {
  type: 'change' as const,
  id: 'chg-1',
  title: 'FI starts mapping how financial firms use AI',
  snippet: 'FI has started a market survey.',
  matchKind: 'keyword' as const,
  score: 0.5,
  instrumentShortName: null,
  binding: null,
  validFrom: null,
  validTo: null,
  versionNo: null,
  urgency: null,
};

const provisionHit = {
  type: 'provision' as const,
  id: 'prov-1',
  title: 'FFFS 2017:2 9 kap. — Lamna information om kostnader',
  snippet: 'Institutet ska lamna information om kostnader innan tjansten utfors.',
  matchKind: 'keyword' as const,
  score: 0.4,
  instrumentShortName: 'FFFS 2017:2',
  binding: true,
  validFrom: null,
  validTo: null,
  versionNo: null,
  urgency: null,
};

/**
 * The screen's own reads answer fixed data; only the search POST is scripted
 * per test. `GET /me` needs a real shape or `useFormatContext` throws on
 * `me.user`, and the two filters need an option to pick or `fireEvent.change`
 * on a `<select>` with no matching `<option>` leaves the value unchanged.
 */
function serve(script: (sent: Sent, index: number) => { status: number; data: unknown }): Sent[] {
  return installAdapter((sent, index) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: { user: { locale: 'en' }, tenant: null } };
    if (sent.path === '/api/v1/vocab/jurisdiction') return { status: 200, data: [{ key: 'se', label: 'Sweden' }, { key: 'eu', label: 'European Union' }] };
    if (sent.path === '/api/v1/vocab/duty_type') return { status: 200, data: [{ key: 'reporting', label: 'Reporting' }, { key: 'disclosure', label: 'Disclosure' }] };
    return script(sent, index);
  });
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
  nav.search = '';
  nav.replace.mockReset();
});

describe('the search URL', () => {
  it('reads every filter but the typed query, and an unknown value is not a filter', () => {
    const params = new URLSearchParams('type=change&jurisdiction=se&dutyType=reporting&binding=true&lang=sv&asOf=2026-06-30&outside=true');
    expect(filtersFrom(params)).toEqual({
      mode: 'search',
      type: 'change',
      jurisdiction: 'se',
      dutyType: 'reporting',
      binding: 'true',
      lang: 'sv',
      asOf: '2026-06-30',
      outsideScope: true,
    });
    expect(filtersFrom(new URLSearchParams('type=nonsense&binding=nonsense')).type).toBe('');
    expect(filtersFrom(new URLSearchParams('type=nonsense&binding=nonsense')).binding).toBe('');
  });

  it('reads Ask as the second mode, and anything else as search', () => {
    expect(filtersFrom(new URLSearchParams('mode=ask&asOf=2026-06-01')).mode).toBe('ask');
    expect(filtersFrom(new URLSearchParams('mode=nonsense')).mode).toBe('search');
    expect(searchOf({ ...EMPTY_SEARCH_FILTERS, mode: 'ask', asOf: '2026-06-01' })).toBe('mode=ask&asOf=2026-06-01');
  });

  it('leaves out a filter that is not set, and never carries the typed query', () => {
    expect(searchOf(EMPTY_SEARCH_FILTERS)).toBe('');
    expect(searchOf({ ...EMPTY_SEARCH_FILTERS, jurisdiction: 'se', outsideScope: true })).toBe('jurisdiction=se&outside=true');
  });

  it('builds the request body from the filters, keys only, plus the typed query', () => {
    expect(requestOf(EMPTY_SEARCH_FILTERS, 'FFFS 2017:2')).toEqual({ q: 'FFFS 2017:2', limit: 20 });
    expect(
      requestOf({ ...EMPTY_SEARCH_FILTERS, jurisdiction: 'se', dutyType: 'reporting', binding: 'true', asOf: '2026-06-30', outsideScope: true, type: 'obligation', lang: 'sv' }, 'q'),
    ).toEqual({
      q: 'q',
      limit: 20,
      asOf: '2026-06-30',
      lang: 'sv',
      types: ['obligation'],
      filters: { jurisdiction: 'se', dutyType: 'reporting', binding: true, footprint: 'all' },
    });
  });
});

describe('SearchScreen', () => {
  it('starts with the example chips and no request, then searches what the reader picks', async () => {
    const sent = serve(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    renderScreen();
    expect(screen.getByRole('heading', { name: 'Type a question or a reference' })).toBeVisible();
    expect(sent.some((call) => call.path === '/api/v1/search')).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'nudging in onboarding' }));
    await waitFor(() => expect(sent.some((call) => call.path === '/api/v1/search')).toBe(true));
    const search = sent.find((call) => call.path === '/api/v1/search');
    expect(search?.body).toEqual({ q: 'nudging in onboarding', limit: 20 });
  });

  it('searches what is typed and submitted', async () => {
    const sent = serve(() => ({ status: 200, data: { items: [obligationHit], asOf: '2026-09-20' } }));
    renderScreen();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search' }), { target: { value: 'FFFS 2017:2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(screen.getByText('Assess appropriateness before non-advised trades')).toBeVisible());
    expect(sent.find((call) => call.path === '/api/v1/search')?.body).toEqual({ q: 'FFFS 2017:2', limit: 20 });
  });

  it('renders every hit type with its own pills, meta and link', async () => {
    serve(() => ({ status: 200, data: { items: [obligationHit, changeHit, provisionHit], asOf: '2026-09-20' } }));
    renderScreen();
    fireEvent.click(screen.getAllByRole('button', { name: 'research payments' })[0]!);

    const obligationRow = await screen.findByRole('link', { name: /Assess appropriateness/ });
    expect(obligationRow).toHaveAttribute('href', '/inventory/obligations/ob-1');
    expect(within(obligationRow).getByText('FFFS 2017:2')).toBeVisible();
    expect(within(obligationRow).getByText('Keyword and concept')).toBeVisible();
    expect(within(obligationRow).getByText('Version 2')).toBeVisible();
    expect(within(obligationRow).getByText('From 1 Jan 2026')).toBeVisible();

    const changeRow = screen.getByRole('link', { name: /FI starts mapping/ });
    expect(changeRow).toHaveAttribute('href', '/watch/chg-1');
    expect(within(changeRow).getByText('Keyword match')).toBeVisible();

    // A provision has no card of its own yet, so it is a fact, not a link.
    expect(screen.queryByRole('link', { name: /9 kap\./ })).toBeNull();
    expect(screen.getByText(/9 kap\./)).toBeVisible();
  });

  it('marks a binding false hit "Guidance" and highlights the query terms in the snippet', async () => {
    serve(() => ({ status: 200, data: { items: [{ ...obligationHit, binding: false }], asOf: '2026-09-20' } }));
    renderScreen();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search' }), { target: { value: 'onboarding' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    const row = await screen.findByRole('link', { name: /Assess appropriateness/ });
    // "Guidance" is also one of the filter row's own option labels, so the pill is read
    // from inside the row rather than from the page as a whole.
    expect(within(row).getByText('Guidance')).toBeVisible();
    expect(within(row).getByText('onboarding', { selector: 'mark' })).toBeVisible();
  });

  it('shows the error state and retries', async () => {
    let calls = 0;
    serve(() => {
      calls += 1;
      return calls === 1 ? { status: 500, data: {} } : { status: 200, data: { items: [], asOf: '2026-09-20' } };
    });
    renderScreen();
    fireEvent.click(screen.getAllByRole('button', { name: 'research payments' })[0]!);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Search is not answering' })).toBeVisible());
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'No match in the inventory' })).toBeVisible());
  });

  it('renders the Restricted screen on a 403', async () => {
    serve(() => ({ status: 403, data: { detail: '', code: 'forbidden', requiredPermission: 'search.use' } }));
    renderScreen();
    fireEvent.click(screen.getAllByRole('button', { name: 'research payments' })[0]!);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'This page is not available to you' })).toBeVisible());
    expect(screen.getByText(/search use/)).toBeVisible();
  });

  it('offers to search outside the scope on no match', async () => {
    serve(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    renderScreen();
    fireEvent.click(screen.getAllByRole('button', { name: 'research payments' })[0]!);
    await waitFor(() => expect(screen.getByRole('link', { name: 'Search outside our scope' })).toBeVisible());
    expect(screen.getByRole('link', { name: 'Search outside our scope' })).toHaveAttribute('href', '/search?outside=true');
  });

  it('offers no way to widen further, and a narrower message, once already outside the scope', async () => {
    nav.search = 'outside=true';
    serve(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    renderScreen();
    fireEvent.click(screen.getAllByRole('button', { name: 'research payments' })[0]!);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'No match in the inventory' })).toBeVisible());
    expect(screen.getByText('Nothing outside our scope matches either. Try a broader word or another language.')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Search outside our scope' })).toBeNull();
  });

  it('sends a filter chosen from the row, and the outside-scope chip, as the footprint "all"', async () => {
    nav.search = 'jurisdiction=se&dutyType=reporting&outside=true';
    const sent = serve(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    renderScreen();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search' }), { target: { value: 'report' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(sent.some((call) => call.path === '/api/v1/search')).toBe(true));
    expect(sent.find((call) => call.path === '/api/v1/search')?.body).toEqual({
      q: 'report',
      limit: 20,
      filters: { jurisdiction: 'se', dutyType: 'reporting', footprint: 'all' },
    });
    expect(screen.getByRole('button', { name: 'Outside our scope' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows the "as of" banner and clears it back to today', () => {
    nav.search = 'asOf=2026-06-30';
    serve(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    renderScreen();
    expect(screen.getByText('Showing the versions in force on 30 Jun 2026.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Back to today' })).toHaveAttribute('href', '/search');
  });

  it('changing a filter replaces the URL rather than the typed query', async () => {
    serve(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    renderScreen();
    // The option has to have arrived before it can be selected.
    await waitFor(() => expect(screen.getByRole('option', { name: 'Sweden' })).toBeInTheDocument());
    fireEvent.change(screen.getByRole('combobox', { name: 'Jurisdiction' }), { target: { value: 'se' } });
    expect(nav.replace).toHaveBeenCalledWith('/search?jurisdiction=se');
  });
});

describe('SearchScreen in Ask mode', () => {
  beforeEach(() => {
    // A browser resolves the relative route against the page; Node needs an origin.
    api.defaults.baseURL = 'http://app.test';
  });

  afterEach(() => {
    api.defaults.baseURL = '';
    vi.unstubAllGlobals();
  });

  it('switches to Ask through the URL, keeping "as of"', () => {
    nav.search = 'asOf=2026-06-01';
    serve(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    renderScreen();
    fireEvent.click(screen.getByRole('tab', { name: 'Ask a question' }));
    expect(nav.replace).toHaveBeenCalledWith('/search?mode=ask&asOf=2026-06-01');
  });

  it('asks with the carried "as of", and the question never reaches the URL', async () => {
    nav.search = 'mode=ask&asOf=2026-06-01';
    serve(() => ({ status: 200, data: { items: [], asOf: '2026-09-20' } }));
    const requests = stubFetch(() => sseResponse(framesOf([{ event: 'start', id: 'ans-1' }])));
    renderScreen();
    expect(screen.getByRole('tab', { name: 'Ask a question' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('Showing the versions in force on 1 Jun 2026.')).toBeVisible();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Question' }), { target: { value: 'What about research payments?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => expect(requests).toHaveLength(1));
    expect(await requests[0]?.json()).toEqual({ question: 'What about research payments?', asOf: '2026-06-01' });
    for (const [href] of nav.replace.mock.calls) expect(String(href)).not.toContain('research');
  });

  it('"Search instead" searches the question, in search mode, with the same "as of"', async () => {
    nav.search = 'mode=ask&asOf=2026-06-01';
    nav.replace.mockImplementation((href: string) => {
      nav.search = href.split('?')[1] ?? '';
    });
    const sent = serve(() => ({ status: 200, data: { items: [], asOf: '2026-06-01' } }));
    stubFetch(() => sseResponse(framesOf([{ event: 'start', id: 'ans-1' }, { event: 'answer', answer: { id: 'ans-1', question: 'q', asOf: '2026-06-01', statements: [], citations: [], noAnswer: true, model: '', aiGenerated: true, createdAt: '2026-06-01T09:00:00Z' }, stopReason: null }])));
    renderScreen();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Question' }), { target: { value: 'crypto custody' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Search instead' }));

    expect(nav.replace).toHaveBeenLastCalledWith('/search?asOf=2026-06-01');
    await waitFor(() => expect(sent.find((call) => call.path === '/api/v1/search')?.body).toEqual({ q: 'crypto custody', limit: 20, asOf: '2026-06-01' }));
    expect(screen.getByRole('searchbox', { name: 'Search' })).toHaveValue('crypto custody');
  });
});

