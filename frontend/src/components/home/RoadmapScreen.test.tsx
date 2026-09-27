import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';

import type { Roadmap } from '@/features/home/types';
import { RoadmapScreen } from './RoadmapScreen';

// /roadmap (design/screens/tenant-roadmap.html): the quarter roster in the
// API's own order, the chips storing `kind` as a key in the URL, a card
// expanding in place to the pill, the date and the days left, our own
// deadlines with what produced them, their owner and their record, and the
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
  datePrecision: 'day',
  quarter: '2026-Q4',
  label: 'In force',
  title: 'FI adopts amended rules on paying for investment research',
  status: 'new',
  urgency: { key: 'act_now', kind: null, label: 'Act now' },
  sourceLabel: 'Finansinspektionen',
  changeId: 'c-1',
  owner: null,
  subject: null,
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

const internal = { label: null, status: null, urgency: null, sourceLabel: null, changeId: null, obligations: [] };
const review: Roadmap['items'][number] = {
  ...internal,
  id: 'review_due:r-1',
  kind: 'internal',
  itemType: 'review_due',
  date: '2026-11-02',
  datePrecision: 'day',
  quarter: '2026-Q4',
  title: 'Pay for third-party research only under the permitted models',
  owner: { person: { id: 'u-1', name: 'Johan Berg' }, team: { key: 'retail_compliance', kind: null, label: 'Retail compliance' } },
  subject: { obligationId: 'o-1', gapId: null, licenceId: null, entity: null },
};
const audit: Roadmap['items'][number] = {
  ...internal,
  id: 'certificate_audit:l-1',
  kind: 'internal',
  itemType: 'certificate_audit',
  date: '2027-03-15',
  datePrecision: 'day',
  quarter: '2027-Q1',
  title: 'ISO/IEC 27001',
  owner: { person: { id: 'u-2', name: 'Sara Lind' }, team: null },
  subject: { obligationId: null, gapId: null, licenceId: 'l-1', entity: { id: 'e-1', name: 'Example Bank AB' } },
};

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

  it('prints a quarter-precision date as its quarter, never as the day it is stored on, and counts no days to it', async () => {
    const quarterly: Roadmap['items'][number] = { ...later, datePrecision: 'quarter' };
    serve({ items: [soon, quarterly], quarters: ['2026-Q4', '2027-Q1'] });
    render(shell(<RoadmapScreen />));
    await screen.findByRole('heading', { name: 'Q1 2027' });

    expect(screen.queryByText('19 Jan 2027')).not.toBeInTheDocument();
    const card = screen.getByRole('button', { name: /Amended reporting of securities financing transactions/ });
    expect(card).toHaveTextContent('Q1 2027');
    card.click();
    const detail = await screen.findByRole('heading', { level: 2, name: 'Amended reporting of securities financing transactions' });
    const meta = detail.previousElementSibling as HTMLElement;
    expect(meta).toHaveTextContent('Q1 2027');
    expect(meta).not.toHaveTextContent(/\bin \d+ days?\b/);
  });

  it('a date stated to the day keeps its day and the days left to it', async () => {
    vi.useFakeTimers({ now: new Date('2026-09-21T09:00:00Z'), toFake: ['Date'] });
    try {
      serve(roadmap);
      render(shell(<RoadmapScreen />));
      (await screen.findByRole('button', { name: /1 Oct 2026/ })).click();
      expect(await screen.findByText('in 10 days')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('our own deadline reads Our deadline in the brand tone and names what it is, its owner and its record', async () => {
    serve({ items: [review, audit], quarters: ['2026-Q4', '2027-Q1'] });
    render(shell(<RoadmapScreen />));

    const card = await screen.findByRole('button', { name: /Pay for third-party research/ });
    expect(card).toHaveTextContent('Our deadline · Next review · Johan Berg, Retail compliance');
    card.click();
    const detail = (await screen.findByRole('heading', { level: 2, name: 'Pay for third-party research only under the permitted models' })).parentElement as HTMLElement;
    expect(detail.querySelector('[data-pill="brand"]')).toHaveTextContent('Our deadline');
    expect(detail).toHaveTextContent('WhatNext review');
    expect(detail).toHaveTextContent('OwnerJohan Berg, Retail compliance');
    expect(screen.getByRole('link', { name: 'Open obligation' })).toHaveAttribute('href', '/inventory/obligations/o-1');
    expect(screen.queryByRole('link', { name: 'Open change' })).not.toBeInTheDocument();
  });

  it("a certificate's audit names the legal entity it belongs to and links nowhere", async () => {
    serve({ items: [review, audit], quarters: ['2026-Q4', '2027-Q1'] });
    render(shell(<RoadmapScreen />));

    (await screen.findByRole('button', { name: /ISO\/IEC 27001/ })).click();
    const detail = (await screen.findByRole('heading', { level: 2, name: 'ISO/IEC 27001' })).parentElement as HTMLElement;
    expect(detail).toHaveTextContent('WhatCertificate audit');
    expect(detail).toHaveTextContent('OwnerSara Lind');
    expect(detail).toHaveTextContent('Legal entityExample Bank AB');
    expect(screen.queryByRole('link', { name: 'Open obligation' })).not.toBeInTheDocument();
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
    expect(
      screen.getByText('Review dates, gap targets, certificate expiries and audits, assessment deadlines and action due dates appear here once they are set.'),
    ).toBeInTheDocument();
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
