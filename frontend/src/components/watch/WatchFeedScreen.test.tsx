import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';
import { defaultFormatContext } from '@/shared/utils/format';

import type { ChangeRow } from '@/features/watch/api';
import { ChangeFeedRow, WatchFeedScreen, filtersFrom, footMeta, isNarrowed, queryOf, searchOf, tabFrom } from './WatchFeedScreen';
import { EMPTY_FILTERS } from './WatchFilters';

// /watch (design/screens/tenant-watch.html): the URL carries the tab and the
// filters as keys, the row carries the pill contract in the card's slot
// order, a row outside the footprint is dashed and says so, and every state
// the card names renders.

const nav = { search: '', replace: vi.fn() };

vi.mock('next/navigation', () => ({
  usePathname: () => '/watch',
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const t = createT('en');
const ctx = defaultFormatContext;
const TODAY = new Date(Date.UTC(2026, 8, 19));

const fact = (key: string, label: string, suggested = false) => ({ ref: { key, kind: null, label }, confidence: 0.9, suggested });

const research: ChangeRow = {
  id: 'c-1',
  stableKey: 'chg-fi-2026-research-payments',
  title: 'FI adopts amended rules on paying for investment research',
  status: 'active',
  authorityId: 'a-1',
  authorityLabel: 'Finansinspektionen',
  changeType: fact('adopted', 'Adopted rule'),
  flags: [],
  terms: [fact('isk', 'ISK')],
  suggestedUrgency: { key: 'act_now', kind: null, label: 'Act now' },
  publishedOn: '2026-09-15',
  publishedPrecision: 'day',
  keyDate: '2026-10-01',
  keyDateLabel: 'In force',
  keyDatePrecision: 'day',
  firstSeenAt: '2026-09-16T06:02:00Z',
  inFootprint: true,
  market: null,
  case: {
    id: 'case-1',
    category: 'new',
    allowedTransitions: [],
    footprintMatch: true,
    obligationDecisions: [],
    ownerId: null,
    soWhatConfirmed: false,
    soWhatConfirmedAt: null,
    soWhatText: 'Teams that pay for external research should confirm the criteria exist.',
    urgency: null,
    urgencyConfirmed: false,
  },
} as ChangeRow;

const aiMapping: ChangeRow = {
  ...research,
  id: 'c-2',
  stableKey: 'chg-fi-2026-ai-mapping',
  title: 'FI starts mapping how financial firms use AI',
  changeType: fact('supervision', 'Supervision'),
  flags: [fact('ai', 'AI', true)],
  suggestedUrgency: { key: 'monitor', kind: null, label: 'Monitor' },
  keyDate: null,
  keyDateLabel: 'Report date',
  inFootprint: false,
  market: null,
  case: null,
};

/** Everything the screen and its row sit inside: the query cache and the pinned language. */
function shell(children: ReactNode): ReactNode {
  const { wrapper: Query } = queryWrapper();
  return (
    <Query>
      <LocaleProvider locale="en">{children}</LocaleProvider>
    </Query>
  );
}

function renderScreen(): void {
  render(shell(<WatchFeedScreen />));
}

function renderRow(row: ChangeRow): void {
  render(shell(<ChangeFeedRow row={row} today={TODAY} />));
}

/** The feed read answers `rows`; a count read answers `triageTotal`. */
function serve(rows: ChangeRow[], total = rows.length, triageTotal = total): Sent[] {
  return installAdapter((sent) => {
    if ((sent.params as { limit?: number }).limit === 1) return { status: 200, data: { items: [], total: triageTotal } };
    return { status: 200, data: { items: rows, total } };
  });
}

describe('the watch feed URL', () => {
  it('reads the tab and the filters, and an unknown value is not a filter', () => {
    const params = new URLSearchParams('tab=closed&type=adopted&urgency=act_now&term=t-1&week=2026-09-14&unconfirmed=true&scope=all');
    expect(tabFrom(params)).toBe('closed');
    expect(filtersFrom(params)).toEqual({
      regimeTermId: 't-1',
      changeType: 'adopted',
      urgency: 'act_now',
      week: '2026-09-14',
      unconfirmedSoWhat: true,
      scope: 'all',
    });
    expect(tabFrom(new URLSearchParams('tab=nonsense'))).toBe('triage');
    expect(filtersFrom(new URLSearchParams('scope=nonsense')).scope).toBe('in');
  });

  it('writes back only what is set, and triage and "in our scope" are the defaults', () => {
    expect(searchOf(EMPTY_FILTERS, 'triage')).toBe('');
    expect(searchOf({ ...EMPTY_FILTERS, scope: 'watched' }, 'closed')).toBe('tab=closed&scope=watched');
    expect(searchOf({ ...EMPTY_FILTERS, changeType: 'adopted', unconfirmedSoWhat: true, week: '2026-09-14', urgency: 'monitor', regimeTermId: 't-1' }, 'triage')).toBe(
      'term=t-1&type=adopted&urgency=monitor&week=2026-09-14&unconfirmed=true',
    );
  });

  it('sends one footprint value and the term as an id', () => {
    expect(queryOf(EMPTY_FILTERS, '')).toEqual({ footprint: 'in' });
    expect(queryOf({ ...EMPTY_FILTERS, scope: 'all', regimeTermId: 't-1', changeType: 'adopted', urgency: 'monitor', week: '2026-09-14', unconfirmedSoWhat: true }, 'x')).toEqual({
      footprint: 'all',
      termId: ['t-1'],
      changeType: 'adopted',
      urgency: 'monitor',
      week: '2026-09-14',
      unconfirmedSoWhat: true,
      q: 'x',
    });
  });

  it('knows when the reader narrowed the feed', () => {
    expect(isNarrowed(EMPTY_FILTERS, '')).toBe(false);
    expect(isNarrowed({ ...EMPTY_FILTERS, scope: 'all' }, '')).toBe(true);
    expect(isNarrowed(EMPTY_FILTERS, 'research')).toBe(true);
    expect(isNarrowed({ ...EMPTY_FILTERS, unconfirmedSoWhat: true }, '')).toBe(true);
    expect(isNarrowed({ ...EMPTY_FILTERS, regimeTermId: 't-1' }, '')).toBe(true);
    expect(isNarrowed({ ...EMPTY_FILTERS, urgency: 'monitor' }, '')).toBe(true);
    expect(isNarrowed({ ...EMPTY_FILTERS, week: '2026-09-14' }, '')).toBe(true);
  });
});

describe('a change row', () => {
  it('renders the pills in the card’s slot order, then the authority and date as text', () => {
    renderRow({ ...research, flags: [fact('ai', 'AI')] });
    const row = screen.getByRole('link');
    expect(within(row).getAllByText(/./, { selector: '[data-pill]' }).map((p) => [p.textContent, p.getAttribute('data-pill')])).toEqual([
      ['Adopted rule', 'notice'],
      ['Act now', 'negative'],
      ['AI', 'brand'],
    ]);
    expect(within(row).getByText('Finansinspektionen, 15 Sept 2026')).toBeInTheDocument();
    expect(row).toHaveAttribute('href', '/watch/c-1');
  });

  it('marks a fact the agent suggested, and carries the AI label on an unconfirmed So what', () => {
    renderRow({ ...research, flags: [fact('ai', 'AI', true)] });
    expect(screen.getByText('Suggested by the agent')).toHaveAttribute('data-pill', 'information');
    expect(screen.getByText('Drafted by AI, not yet confirmed by a person')).toBeInTheDocument();
  });

  it('a wording the bank confirmed loses the AI label', () => {
    renderRow({ ...research, case: { ...research.case!, soWhatConfirmed: true } });
    expect(screen.queryByText('Drafted by AI, not yet confirmed by a person')).not.toBeInTheDocument();
    expect(screen.getByText('So what?')).toBeInTheDocument();
  });

  it('a row outside the footprint is dashed and says so', () => {
    renderRow(aiMapping);
    expect(screen.getByRole('link')).toHaveAttribute('data-outside-footprint', '');
    expect(screen.getByText('Outside our scope')).toBeInTheDocument();
  });

  it('the foot reads status, key date, days left and scope', () => {
    expect(footMeta(research, t, ctx, TODAY)).toEqual(['Needs triage', 'In force 1 Oct 2026', 'in 12 days', 'ISK']);
    expect(footMeta(aiMapping, t, ctx, TODAY)).toEqual(['Report date Date not set', 'ISK', 'Outside our scope']);
  });

  it('a row from a market we watch names the market as text in place of the outside note', () => {
    const danish = { ...aiMapping, market: { key: 'dk', kind: null, label: 'Denmark' } };
    expect(footMeta(danish, t, ctx, TODAY)).toEqual(['Report date Date not set', 'ISK', 'Market we watch: Denmark']);
  });

  it('a change with no So what shows none', () => {
    renderRow({ ...research, case: { ...research.case!, soWhatText: null } });
    expect(screen.queryByText('So what?')).not.toBeInTheDocument();
  });
});

describe('the watch feed screen', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
    nav.search = '';
    nav.replace.mockReset();
  });

  it('reads the triage tab by default, and its count is the feed’s own total rather than a second read', async () => {
    const sent = serve([research], 1);
    renderScreen();
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Needs triage (1)' })).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: 'Needs triage (1)' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'In progress' })).toBeInTheDocument();
    const feedReads = sent.filter((s) => s.path === '/api/v1/changes');
    expect(feedReads).toHaveLength(1);
    expect(feedReads[0]?.params).toMatchObject({ tab: 'new', limit: 20 });
  });

  it('on another tab the triage count is one small read of the same route', async () => {
    nav.search = 'tab=closed';
    const sent = serve([], 0, 4);
    renderScreen();
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Needs triage (4)' })).toBeInTheDocument());
    expect(sent.filter((s) => (s.params as { limit?: number }).limit === 1)).toHaveLength(1);
  });

  it('shows the rows and how many of the total are on screen', async () => {
    serve([research, aiMapping], 2);
    renderScreen();
    await waitFor(() => expect(screen.getByText('Showing 2 of 2')).toBeInTheDocument());
    expect(screen.getAllByRole('link')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument();
  });

  it('offers another page only while one is left, and appends it', async () => {
    const rows = Array.from({ length: 20 }, (_, i) => ({ ...research, id: `c-${i}`, stableKey: `chg-${i}` }));
    installAdapter((sent, index) => {
      const params = sent.params as { limit?: number; offset?: number };
      if (params.limit === 1) return { status: 200, data: { items: [], total: 21 } };
      return { status: 200, data: { items: index === 0 || params.offset === 0 ? rows : [aiMapping], total: 21 } };
    });
    renderScreen();
    const more = await screen.findByRole('button', { name: 'Show more' });
    fireEvent.click(more);
    await waitFor(() => expect(screen.getByText('Showing 21 of 21')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument();
  });

  it('an empty triage tab points at the scope nobody looked outside of', async () => {
    serve([], 0);
    renderScreen();
    await waitFor(() => expect(screen.getByText('Nothing needs triage')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: 'Look outside our scope' })).toHaveAttribute('href', '/watch?scope=all');
  });

  it('an empty narrowed feed offers to clear the filters', async () => {
    nav.search = 'scope=all';
    serve([], 0);
    renderScreen();
    await waitFor(() => expect(screen.getByText('Nothing matches these filters')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: 'Clear filters' })).toHaveAttribute('href', '/watch');
  });

  it('a phrase someone typed is sent on asking and never written into the address', async () => {
    const sent = serve([], 0);
    renderScreen();
    const box = await screen.findByRole('searchbox', { name: 'Search these changes' });
    fireEvent.change(box, { target: { value: 'research' } });
    expect(nav.replace).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(sent.some((s) => (s.params as { q?: string }).q === 'research')).toBe(true));
    expect(nav.replace).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('Nothing matches these filters')).toBeInTheDocument());
  });

  it('an empty tab other than triage says so in its own words', async () => {
    nav.search = 'tab=closed';
    serve([], 0);
    renderScreen();
    await waitFor(() => expect(screen.getByText('Nothing in this tab')).toBeInTheDocument());
  });

  it('a failed read offers to try again', async () => {
    installAdapter(() => ({ status: 500 }));
    renderScreen();
    await waitFor(() => expect(screen.getByText('Could not load the feed')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('a server 403 renders the Restricted screen with what the server said', async () => {
    installAdapter(() => ({ status: 403, data: { detail: 'You need the watch grant.', code: 'forbidden', requiredPermission: 'watch.read' } }));
    renderScreen();
    await waitFor(() => expect(screen.getByText('You need the watch grant.')).toBeInTheDocument());
    expect(screen.getByText('Needs watch read')).toBeInTheDocument();
  });

  it('choosing a tab and a filter rewrites the URL with keys', async () => {
    serve([research], 1);
    renderScreen();
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Needs triage (1)' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Closed' }));
    expect(nav.replace).toHaveBeenCalledWith('/watch?tab=closed');
    fireEvent.click(screen.getByRole('button', { name: 'Show outside our scope' }));
    expect(nav.replace).toHaveBeenCalledWith('/watch?scope=all');
  });

  it('the Coverage tab reads the source log instead of the feed', async () => {
    nav.search = 'tab=coverage';
    const sent = installAdapter((request) => ({ status: 200, data: request.path === '/api/v1/sources/coverage' ? [] : { items: [], total: 0 } }));
    renderScreen();
    await waitFor(() => expect(screen.getByText('Nothing checked yet')).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: 'Coverage' })).toHaveAttribute('aria-selected', 'true');
    // The feed read is not made at all while the tab beside it is open.
    expect(sent.filter((s) => s.path === '/api/v1/changes')).toHaveLength(0);
    expect(screen.queryByRole('group', { name: 'Scope' })).not.toBeInTheDocument();
  });

  it('the footprint filter holds exactly one value, so no contradictory pair can be built', async () => {
    nav.search = 'scope=watched';
    serve([], 0);
    renderScreen();
    const scope = await screen.findByRole('group', { name: 'Scope' });
    const pressed = within(scope)
      .getAllByRole('button')
      .filter((button) => button.getAttribute('aria-pressed') === 'true');
    expect(pressed.map((button) => button.textContent)).toEqual(['Markets we watch']);
  });
});
