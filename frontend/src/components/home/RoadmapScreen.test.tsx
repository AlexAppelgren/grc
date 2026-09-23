import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';

import type { Roadmap } from '@/features/home/types';
import { RoadmapScreen } from './RoadmapScreen';

// /roadmap (design/screens/tenant-roadmap.html): the quarter roster in the
// API's own order, the chips storing `kind` as a key in the URL, a card
// expanding in place to the pill, the date and the days left, and the
// states the design card names.

const nav = { search: '', replace: vi.fn() };

vi.mock('next/navigation', () => ({
  usePathname: () => '/roadmap',
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const ROADMAP_PATH = '/api/v1/roadmap';

const soon: Roadmap['items'][number] = {
  id: 'change_date:c-1',
  kind: 'regulatory',
  itemType: 'change_date',
  date: '2026-10-01',
  quarter: '2026-Q4',
  label: 'In force',
  title: 'FI adopts amended rules on paying for investment research',
  status: 'new',
  urgency: { key: 'act_now', kind: null, label: 'Act now' },
  sourceLabel: 'Finansinspektionen',
  changeId: 'c-1',
  obligations: [],
};

const later: Roadmap['items'][number] = {
  ...soon,
  id: 'change_date:c-2',
  date: '2027-01-19',
  quarter: '2027-Q1',
  label: 'Applies',
  title: 'Amended reporting of securities financing transactions',
  urgency: { key: 'six_months_plus', kind: null, label: 'Six months plus' },
  changeId: 'c-2',
};

const roadmap: Roadmap = { items: [soon, later], quarters: ['2026-Q4', '2027-Q1'] };

function shell(children: ReactNode): ReactNode {
  const { wrapper: Query } = queryWrapper();
  return (
    <Query>
      <LocaleProvider locale="en">{children}</LocaleProvider>
    </Query>
  );
}

function serve(data: Roadmap): Sent[] {
  return installAdapter((sent) => (sent.path === ROADMAP_PATH ? { status: 200, data } : { status: 403, data: {} }));
}

beforeEach(() => {
  resetApiForTests();
  nav.search = '';
  nav.replace.mockClear();
});

describe('RoadmapScreen', () => {
  it('renders the quarter roster in the API order, and a card expands in place without navigating', async () => {
    serve(roadmap);
    render(shell(<RoadmapScreen />));

    expect(await screen.findByText('Q4 2026')).toBeInTheDocument();
    expect(screen.getByText('Q1 2027')).toBeInTheDocument();
    expect(screen.getByText('FI adopts amended rules on paying for investment research')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open change' })).not.toBeInTheDocument();

    screen.getByRole('button', { name: /1 Oct 2026/ }).click();
    expect(await screen.findByRole('link', { name: 'Open change' })).toHaveAttribute('href', '/watch/c-1');
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it('a chip stores the kind as a key in the URL', async () => {
    serve(roadmap);
    render(shell(<RoadmapScreen />));
    await screen.findByText('Q4 2026');

    screen.getByRole('button', { name: 'Our deadlines' }).click();
    expect(nav.replace).toHaveBeenCalledWith('/roadmap?kind=internal');
  });

  it('the internal chip names where our own deadlines come from when it is empty', async () => {
    nav.search = 'kind=internal';
    serve({ items: [], quarters: [] });
    render(shell(<RoadmapScreen />));

    expect(await screen.findByText('No deadlines of our own yet')).toBeInTheDocument();
    // When they appear, never which part of the product is still to be built.
    expect(screen.getByText('Review dates, gap targets, assessment deadlines and action due dates appear here once they are set.')).toBeInTheDocument();
  });

  it('links from its head to the calendar feeds of the person reading it', async () => {
    serve(roadmap);
    render(shell(<RoadmapScreen />));
    await screen.findByText('Q4 2026');

    expect(screen.getByRole('link', { name: 'Subscribe to calendar feed' })).toHaveAttribute('href', '/me/calendar-feeds');
  });

  it('renders error and denied states', async () => {
    installAdapter(() => ({ status: 500, data: {} }));
    render(shell(<RoadmapScreen />));
    expect(await screen.findByText('Could not load the roadmap')).toBeInTheDocument();

    installAdapter(() => ({ status: 403, data: { code: 'forbidden', detail: '', requiredPermission: 'roadmap.read' } }));
    render(shell(<RoadmapScreen />));
    expect(await screen.findByText('This page is not available to you')).toBeInTheDocument();
  });
});
