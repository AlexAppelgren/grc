import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Home } from '@/features/home/types';
import type { Me } from '@/features/identity/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { TodayScreen } from './TodayScreen';

// / (design/screens/tenant-today.html): "Coming up" in the roadmap's own
// order, the lead card with its brand pill and confirmed "So what?",
// "Decide now" reading GET /me's counts with a permission-gated line, the
// source foot, and the states the design card names.

const ME_PATH = '/api/v1/me';
const HOME_PATH = '/api/v1/home';

const me: Me = {
  user: { id: 'u1', email: 'sara@example.test', name: 'Sara Lindqvist', locale: 'en' },
  tenant: { id: 't1', name: 'Example Bank AB', slug: 'example-bank', timezone: 'Europe/Stockholm' },
  roles: [{ key: 'compliance_officer', kind: null, label: 'Compliance officer' }],
  permissions: ['watch.read', 'roadmap.read', 'cases.triage', 'proposals.create'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
  counts: { triage: 3, proposals: 2, assignedToMe: 1 },
  lastVisitAt: null,
};

const fact = (key: string, label: string) => ({ ref: { key, kind: null, label }, confidence: null, suggested: false });

const lead: Home['lead'] = {
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
} as Home['lead'];

const home: Home = {
  date: '2026-09-21',
  comingUp: [
    {
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
    },
  ],
  roadmapCount: 1,
  lead,
  sources: { checked: 1, total: 2, failed: [{ lastCheckedAt: '2026-09-16T06:02:00Z', lastError: '502', lastStatus: 'failed', overdue: false, source: { id: 's-1', name: 'EBA news feed', kind: { key: 'authority_site', kind: null, label: 'Authority site' }, authority: null, checkFrequency: 'weekly', active: true } as never }] },
};

function shell(children: ReactNode, permissions: readonly string[] = me.permissions): ReactNode {
  const { wrapper: Query } = queryWrapper();
  return (
    <Query>
      <PermissionsProvider permissions={permissions}>
        <LocaleProvider locale="en">{children}</LocaleProvider>
      </PermissionsProvider>
    </Query>
  );
}

function serve(homeAnswer: { status: number; data?: unknown }, meAnswer: { status: number; data?: unknown } = { status: 200, data: me }): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === ME_PATH) return meAnswer;
    if (sent.path === HOME_PATH) return homeAnswer;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('TodayScreen', () => {
  it('shows the lead card with the brand pill and the confirmed So what, and Coming up in the roadmap order', async () => {
    serve({ status: 200, data: home });
    render(shell(<TodayScreen />));

    expect(await screen.findByRole('heading', { level: 1, name: 'What is coming, and where we stand' })).toBeInTheDocument();
    expect(screen.getByText('Lead', { exact: true })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'FI adopts amended rules on paying for investment research' })).toBeInTheDocument();
    expect(screen.getByText('Confirm the annual assessment criteria before the rules take effect.')).toBeInTheDocument();
    expect(screen.queryByText('Drafted by AI, not yet confirmed by a person')).not.toBeInTheDocument();
    expect(screen.getByText('1 dated item ahead')).toBeInTheDocument();
  });

  it('reads Decide now from GET /me, and hides a line the permission list does not unlock', async () => {
    serve({ status: 200, data: home }, { status: 200, data: { ...me, permissions: ['watch.read', 'roadmap.read'] } });
    render(shell(<TodayScreen />, ['watch.read', 'roadmap.read']));

    expect(await screen.findByText('1 case assigned to you.')).toBeInTheDocument();
    expect(screen.queryByText(/needs triage/)).not.toBeInTheDocument();
    expect(screen.queryByText(/pending review/)).not.toBeInTheDocument();
  });

  it('hides the source foot when the reader has no watch.read (null, not zeros)', async () => {
    serve({ status: 200, data: { ...home, lead: null, sources: null } });
    render(shell(<TodayScreen />));

    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());
    expect(screen.queryByText(/Sources:/)).not.toBeInTheDocument();
    expect(screen.queryByText('Lead', { exact: true })).not.toBeInTheDocument();
  });

  it('a quiet tenant (nothing dated, no lead, no sources, nothing to decide) gets the empty state, not a blank page', async () => {
    const quiet: Home = { date: '2026-09-21', comingUp: [], roadmapCount: 0, lead: null, sources: null };
    const quietMe: Me = { ...me, counts: { triage: 0, proposals: 0, assignedToMe: 0 } };
    serve({ status: 200, data: quiet }, { status: 200, data: quietMe });
    render(shell(<TodayScreen />));

    expect(await screen.findByText('Nothing to show yet')).toBeInTheDocument();
  });

  // The empty state's way to the regulatory scope shows only to a holder of a
  // permission that opens it: anyone else would land on the restricted page.
  it.each([['footprint.request'], ['footprint.approve']])('offers a holder of %s the way to the regulatory scope from the empty state', async (permission) => {
    const quiet: Home = { date: '2026-09-21', comingUp: [], roadmapCount: 0, lead: null, sources: null };
    const quietMe: Me = { ...me, counts: { triage: 0, proposals: 0, assignedToMe: 0 } };
    serve({ status: 200, data: quiet }, { status: 200, data: quietMe });
    render(shell(<TodayScreen />, ['watch.read', permission]));

    expect(await screen.findByText('Nothing to show yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Set the regulatory scope under Admin' })).toHaveAttribute('href', '/admin/footprint');
  });

  it('leaves the link out of the empty state for a member who cannot open the regulatory scope', async () => {
    const quiet: Home = { date: '2026-09-21', comingUp: [], roadmapCount: 0, lead: null, sources: null };
    const quietMe: Me = { ...me, counts: { triage: 0, proposals: 0, assignedToMe: 0 } };
    serve({ status: 200, data: quiet }, { status: 200, data: quietMe });
    render(shell(<TodayScreen />, ['watch.read', 'roadmap.read', 'audit.read']));

    expect(await screen.findByText('Nothing to show yet')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Set the regulatory scope under Admin' })).toBeNull();
  });

  it('open decisions keep the page off the empty state even when nothing is dated', async () => {
    const quiet: Home = { date: '2026-09-21', comingUp: [], roadmapCount: 0, lead: null, sources: null };
    serve({ status: 200, data: quiet });
    render(shell(<TodayScreen />));

    expect(await screen.findByText('1 case assigned to you.')).toBeInTheDocument();
    expect(screen.queryByText('Nothing to show yet')).not.toBeInTheDocument();
  });

  it('renders the error state and retries', async () => {
    let calls = 0;
    installAdapter((sent) => {
      if (sent.path === ME_PATH) return { status: 200, data: me };
      if (sent.path === HOME_PATH) {
        calls += 1;
        return calls === 1 ? { status: 500, data: {} } : { status: 200, data: home };
      }
      return { status: 403, data: {} };
    });
    render(shell(<TodayScreen />));

    expect(await screen.findByText('Could not load Today')).toBeInTheDocument();
    screen.getByRole('button', { name: 'Try again' }).click();
    expect(await screen.findByRole('heading', { name: 'FI adopts amended rules on paying for investment research' })).toBeInTheDocument();
  });
});
