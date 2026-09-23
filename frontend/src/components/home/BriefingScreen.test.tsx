import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';

import type { Briefing } from '@/features/home/types';
import { BriefingScreen } from './BriefingScreen';

// /briefing and /briefing/[weekStart] (design/screens/tenant-briefing.html):
// the running week live, a past week frozen with its own banner, "Also this
// week" beside "Coming up", and the states the design card names.

const CURRENT_PATH = '/api/v1/briefings/current';
const PAST_PATH = '/api/v1/briefings/2026-09-14';

vi.mock('next/navigation', () => ({ usePathname: () => '/briefing' }));

const fact = (key: string, label: string) => ({ ref: { key, kind: null, label }, confidence: null, suggested: false });

const lead: Briefing['items'][number] = {
  id: 'c-1',
  stableKey: 'chg-fi-2026-research-payments',
  title: 'FI adopts amended rules on paying for investment research',
  status: 'active',
  authorityId: 'a-1',
  authorityLabel: 'Finansinspektionen',
  changeType: fact('adopted', 'Adopted rule'),
  flags: [],
  terms: [],
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
    soWhatConfirmed: true,
    soWhatConfirmedAt: '2026-09-17T09:00:00Z',
    soWhatConfirmedByName: 'Sara Lind',
    soWhatText: 'Confirm the annual assessment criteria before the rules take effect.',
    urgency: { key: 'act_now', kind: null, label: 'Act now' },
    urgencyConfirmed: true,
  },
} as Briefing['items'][number];

const second: Briefing['items'][number] = { ...lead, id: 'c-2', stableKey: 'chg-fi-2026-ai-mapping', title: 'FI starts mapping how financial firms use AI', case: null };

const running: Briefing = { weekStart: '2026-09-14', weekEnd: '2026-09-20', lead, items: [lead, second], comingUp: [], emailSentAt: null };
const sent: Briefing = { ...running, emailSentAt: '2026-09-21T05:00:00Z' };

function shell(children: ReactNode): ReactNode {
  const { wrapper: Query } = queryWrapper();
  return (
    <Query>
      <LocaleProvider locale="en">{children}</LocaleProvider>
    </Query>
  );
}

function serve(data: Briefing, path = CURRENT_PATH): Sent[] {
  return installAdapter((s) => (s.path === path ? { status: 200, data } : { status: 403, data: {} }));
}

beforeEach(() => resetApiForTests());

describe('BriefingScreen', () => {
  it('the running week shows the lead feature, Also this week and no snapshot banner', async () => {
    serve(running);
    render(shell(<BriefingScreen />));

    expect(await screen.findByRole('heading', { level: 1, name: 'This week in brief' })).toBeInTheDocument();
    expect(screen.getByText('Week 38, 14 Sept 2026 to 20 Sept 2026')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'FI adopts amended rules on paying for investment research' })).toBeInTheDocument();
    expect(screen.getByText('FI starts mapping how financial firms use AI')).toBeInTheDocument();
    expect(screen.queryByText(/Sent /)).not.toBeInTheDocument();
  });

  it('a past week shows the frozen-snapshot banner with its send date', async () => {
    serve(sent, PAST_PATH);
    render(shell(<BriefingScreen weekStart="2026-09-14" />));

    expect(await screen.findByText(/^Sent /)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'See this week' })).toHaveAttribute('href', '/briefing');
  });

  it('a quiet week gets the empty state', async () => {
    serve({ ...running, lead: null, items: [] });
    render(shell(<BriefingScreen />));

    expect(await screen.findByText('Nothing new matches our scope this week')).toBeInTheDocument();
  });

  it('a week this bank was never sent answers not found', async () => {
    installAdapter(() => ({ status: 404, data: { code: 'not_found', detail: '' } }));
    render(shell(<BriefingScreen weekStart="2026-01-05" />));

    expect(await screen.findByRole('heading', { level: 1, name: 'Not found' })).toBeInTheDocument();
    expect(screen.getByText('This bank was never sent a briefing for that week.')).toBeInTheDocument();
  });
});
