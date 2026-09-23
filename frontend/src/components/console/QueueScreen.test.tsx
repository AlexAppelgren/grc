import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import type { ProposalQueueRow } from '@/features/proposals/types';
import { QUEUE_PAGE, QueueScreen, offsetFrom, searchOf } from './QueueScreen';

// /console/queue (design/screens/console-queue.html): each row reads the
// server's own isMine, fromOrganisation and target, never a guess of the
// browser's; each tab asks for its own order; the queue pages by the route's
// limit, offset and total.

const nav = { search: '', replace: vi.fn() };

vi.mock('next/navigation', () => ({
  usePathname: () => '/console/queue',
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const PROPOSALS = '/api/v1/proposals';

const editor = {
  user: { id: 'u10', email: 'editor@bleqq.test', name: 'Ida Holm', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['proposals.review'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

function proposal(overrides: Partial<ProposalQueueRow>): ProposalQueueRow {
  return {
    id: 'p-1',
    kind: 'new_obligation_version',
    status: 'open',
    title: 'Add version 2 of the research payment obligation',
    targetType: 'obligation',
    targetId: 'obl-1',
    changeId: null,
    payload: {},
    fieldSources: {},
    scopeSuggestion: [],
    sourceLabel: '',
    sourceUrl: '',
    effectiveFrom: null,
    origin: 'agent',
    agentRunId: 'run-1',
    model: 'agent pipeline 0.4',
    proposedBy: null,
    proposedByAgent: { key: 'watch-sweeper', version: 1 },
    fromOrganisation: false,
    reviewedBy: null,
    reviewedByAgent: null,
    correctedBy: null,
    correctedByAgent: null,
    reviewedAt: null,
    rejectionCode: '',
    reviewNote: '',
    appliedAt: null,
    createdAt: '2026-09-16T07:12:00Z',
    target: null,
    isMine: false,
    ...overrides,
  };
}

/** The server: the session and the queue read, answering `rows` and `total` for every page. */
function serve(rows: ProposalQueueRow[], total = rows.length): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: editor };
    if (sent.path === PROPOSALS) return { status: 200, data: { items: rows, total } };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

const queueReads = (sent: Sent[]) => sent.filter((s) => s.path === PROPOSALS).map((s) => s.params as Record<string, string>);

function renderScreen(): void {
  const { wrapper: Query } = queryWrapper();
  const shell = (children: ReactNode) => (
    <Query>
      <LocaleProvider locale="en">{children}</LocaleProvider>
    </Query>
  );
  render(shell(<QueueScreen />));
}

describe('the console queue', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
    nav.search = '';
    nav.replace.mockReset();
  });

  it('marks "Yours" by the server\'s isMine, whoever the row names as proposer', async () => {
    serve([
      proposal({ id: 'p-mine', title: 'Mine by the server', isMine: true }),
      proposal({ id: 'p-named', title: 'Named but not mine', isMine: false, origin: 'user', proposedBy: { id: 'u10', name: 'Ida Holm' } }),
    ]);
    renderScreen();
    const mine = await screen.findByRole('link', { name: /Mine by the server/ });
    expect(within(mine).getByText('Yours')).toBeInTheDocument();
    expect(within(screen.getByRole('link', { name: /Named but not mine/ })).queryByText('Yours')).toBeNull();
  });

  it('names a bank\'s proposal by the organisation phrase when the server says fromOrganisation, agent run or not', async () => {
    serve([proposal({ id: 'p-bank', title: 'From a bank', fromOrganisation: true, agentRunId: 'run-9', model: 'bank agent 1.0' })]);
    renderScreen();
    const row = await screen.findByRole('link', { name: /From a bank/ });
    expect(within(row).getByText('A member of an organisation')).toBeInTheDocument();
    expect(within(row).queryByText('bank agent 1.0')).toBeNull();
  });

  it('names the record a row changes by the server\'s target, and none for a vocabulary change', async () => {
    serve([
      proposal({ id: 'p-t', title: 'With a target', target: { id: 'obl-1', title: 'Pay for research only under the permitted models', referenceLabel: 'Third-party payments', instrumentShortName: 'FFFS 2017:2' } }),
      proposal({ id: 'p-v', title: 'A vocabulary change', kind: 'vocabulary_create', target: null }),
    ]);
    renderScreen();
    const row = await screen.findByRole('link', { name: /With a target/ });
    expect(within(row).getByText('Pay for research only under the permitted models · FFFS 2017:2')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /A vocabulary change/ }).querySelector('[data-proposal-target]')).toBeNull();
  });

  it('reads Waiting oldest first and the decided tabs newest first', async () => {
    const sent = serve([proposal({})]);
    renderScreen();
    await screen.findByRole('link', { name: /Add version 2/ });
    expect(queueReads(sent)[0]).toMatchObject({ status: 'open', order: 'oldest', limit: String(QUEUE_PAGE) });

    for (const [tab, status] of [
      ['approved', 'approved'],
      ['rejected', 'rejected'],
    ] as const) {
      nav.search = `tab=${tab}`;
      const decided = serve([proposal({ status })]);
      renderScreen();
      await waitFor(() => expect(queueReads(decided).length).toBeGreaterThan(0));
      expect(queueReads(decided)[0]).toMatchObject({ status, order: 'newest' });
    }
  });

  it('pages by the route\'s total, saying which order it reads in, and moves by a whole page', async () => {
    nav.search = 'tab=approved&offset=100';
    const sent = serve([proposal({ status: 'approved' })], QUEUE_PAGE * 2 + 1);
    renderScreen();
    await screen.findByText(`101 to 101 of ${QUEUE_PAGE * 2 + 1}, newest first.`);
    expect(queueReads(sent)[0]).toMatchObject({ offset: '100' });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(nav.replace).toHaveBeenLastCalledWith('/console/queue?tab=approved&offset=200');
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    expect(nav.replace).toHaveBeenLastCalledWith('/console/queue?tab=approved');
  });

  it('shows no paging when one page holds the whole tab, and says oldest first on Waiting', async () => {
    serve([proposal({})], 1);
    renderScreen();
    await screen.findByRole('link', { name: /Add version 2/ });
    expect(document.querySelector('[data-queue-paging]')).toBeNull();

    serve([proposal({})], QUEUE_PAGE + 1);
    renderScreen();
    expect(await screen.findByText(`1 to 1 of ${QUEUE_PAGE + 1}, oldest first.`)).toBeInTheDocument();
  });

  it('starts again at the first page when the tab changes', async () => {
    nav.search = 'offset=100';
    serve([proposal({})], QUEUE_PAGE + 1);
    renderScreen();
    await screen.findByRole('link', { name: /Add version 2/ });
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    expect(nav.replace).toHaveBeenLastCalledWith('/console/queue?tab=approved');
  });
});

describe('the queue address', () => {
  it('reads the offset as a whole page, and ignores one that is not', () => {
    expect(offsetFrom(new URLSearchParams('offset=200'))).toBe(200);
    expect(offsetFrom(new URLSearchParams('offset=150'))).toBe(100);
    expect(offsetFrom(new URLSearchParams('offset=-100'))).toBe(0);
    expect(offsetFrom(new URLSearchParams('offset=abc'))).toBe(0);
    expect(offsetFrom(new URLSearchParams(''))).toBe(0);
  });

  it('writes the offset only past the first page', () => {
    expect(searchOf({ kind: '', origin: '', notMine: false }, 'rejected', 100)).toBe('tab=rejected&offset=100');
    expect(searchOf({ kind: '', origin: '', notMine: false }, 'waiting', 0)).toBe('');
  });
});
