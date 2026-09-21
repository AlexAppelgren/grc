import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import ConsoleChangeFactsPage from '@/app/(console)/console/change-facts/page';
import { ChangeFactsScreen } from '@/components/console/ChangeFactsScreen';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// The console's Change facts queue (WAT-03, WAT-04, ADM-02): the four states,
// the two filters the route answers, paging, and the fence that matters here —
// a console row is the shared library and holds nothing of a bank's.

const ME_PATH = '/api/v1/me';
const CHANGES_PATH = '/api/v1/console/changes';
const AUTHORITIES_PATH = '/api/v1/authorities';

const AUTHORITIES = [
  { id: 'a1', key: 'fi-se', shortName: 'FI', name: 'Finansinspektionen', jurisdiction: { key: 'se', kind: null, label: 'Sweden' }, url: 'https://www.fi.se/' },
  { id: 'a2', key: 'esma', shortName: 'ESMA', name: 'European Securities and Markets Authority', jurisdiction: { key: 'eu', kind: null, label: 'EU' }, url: 'https://www.esma.europa.eu/' },
];

const fact = (key: string, label: string, confidence: number | null, suggested: boolean) => ({ ref: { key, kind: null, label }, confidence, suggested });

const waiting = {
  id: 'c1',
  stableKey: 'fi-2026-research',
  title: 'FI adopts amended rules on paying for investment research',
  changeType: fact('adopted', 'Adopted', null, true),
  authorityLabel: 'Finansinspektionen',
  authorityId: 'a1',
  publishedOn: '2026-09-15',
  publishedPrecision: 'day',
  status: 'active',
  flags: [fact('advice_perimeter', 'Advice perimeter', 0.64, true)],
  terms: [fact('securities', 'Securities', 0.81, true)],
  obligations: [],
  unconfirmedCount: 3,
  firstSeenAt: '2026-09-16T06:02:00Z',
};

const settled = {
  ...waiting,
  id: 'c2',
  stableKey: 'eu-amlr',
  title: 'AMLR applies from 10 July 2027',
  changeType: fact('in_force', 'In force', null, false),
  authorityLabel: 'EUR-Lex',
  authorityId: 'a2',
  publishedOn: null,
  publishedPrecision: null,
  flags: [],
  terms: [],
  unconfirmedCount: 0,
};

const editor = {
  user: { id: 'u10', email: 'editor@bleqq.test', name: 'Ida Holm', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['proposals.review', 'library_vocab.manage', 'sources.manage', 'eval.manage'],
  platformRoles: [{ key: 'library_editor', kind: null, label: 'Library editor' }],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

/** The server: the session, the two reads the screen makes, and nothing else. */
function server(changes: Answer, extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: editor };
    if (sent.path === AUTHORITIES_PATH) return { status: 200, data: AUTHORITIES };
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === CHANGES_PATH && sent.method === 'get') return changes;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const queryOf = (sent: Sent[]) => sent.filter((s) => s.path === CHANGES_PATH).map((s) => s.params);

describe('console change facts queue', () => {
  beforeEach(() => {
    resetApiForTests();
  });

  it('shows what is waiting, with the facts an agent put forward and how many are unconfirmed', async () => {
    server({ status: 200, data: { items: [waiting, settled], total: 2 } });
    renderIn(<ChangeFactsScreen />);

    const row = await screen.findByText(waiting.title);
    const card = row.closest('[data-change-id]') as HTMLElement;
    expect(within(card).getByText('Adopted')).toBeInTheDocument();
    expect(within(card).getByText('Advice perimeter')).toBeInTheDocument();
    expect(within(card).getByText('Securities')).toBeInTheDocument();
    expect(within(card).getByText('Suggested by the agent')).toBeInTheDocument();
    expect(within(card).getByText('3 facts to confirm')).toBeInTheDocument();
    expect(within(card).getByText('Finansinspektionen · Published 15 Sept 2026')).toBeInTheDocument();
    expect(row.closest('a')).toHaveAttribute('href', '/console/change-facts/c1');

    // A change with nothing left to settle reads as settled, and an authority
    // that states no date shows the authority alone.
    const other = screen.getByText(settled.title).closest('[data-change-id]') as HTMLElement;
    expect(within(other).getByText('Confirmed')).toBeInTheDocument();
    expect(within(other).queryByText('Suggested by the agent')).toBeNull();
    expect(within(other).getByText('EUR-Lex')).toBeInTheDocument();
  });

  it('asks the server for each filter, so nothing is filtered in the browser', async () => {
    const sent = server({ status: 200, data: { items: [waiting], total: 1 } });
    renderIn(<ChangeFactsScreen />);
    await screen.findByText(waiting.title);
    expect(queryOf(sent)).toEqual([{ confirmed: 'false', limit: 20, offset: 0 }]);

    fireEvent.change(await screen.findByLabelText('Authority'), { target: { value: 'a2' } });
    await waitFor(() => expect(queryOf(sent)).toHaveLength(2));
    expect(queryOf(sent)[1]).toEqual({ confirmed: 'false', authorityId: 'a2', limit: 20, offset: 0 });

    fireEvent.click(screen.getByRole('button', { name: 'Only unconfirmed' }));
    await waitFor(() => expect(queryOf(sent)).toHaveLength(3));
    expect(queryOf(sent)[2]).toEqual({ confirmed: 'all', authorityId: 'a2', limit: 20, offset: 0 });
  });

  it('pages with the server and starts again at the first page when a filter moves', async () => {
    const sent = server({ status: 200, data: { items: [waiting], total: 41 } });
    renderIn(<ChangeFactsScreen />);
    await screen.findByText(waiting.title);
    expect(screen.getByText('1 to 1 of 41')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Newer' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Older' }));
    await waitFor(() => expect(queryOf(sent)).toHaveLength(2));
    expect(queryOf(sent)[1]).toMatchObject({ offset: 20 });

    fireEvent.change(screen.getByLabelText('Authority'), { target: { value: 'a1' } });
    await waitFor(() => expect(queryOf(sent)).toHaveLength(3));
    expect(queryOf(sent)[2]).toMatchObject({ offset: 0 });
  });

  it('reads the library alone: no bank is asked for, and no row carries a case or a problem report', async () => {
    const sent = server({ status: 200, data: { items: [waiting], total: 1 } });
    const { container } = renderIn(<ChangeFactsScreen />);
    await screen.findByText(waiting.title);

    // The console holds no tenant, so the tenant feed, a case and the
    // problem-report surface are not merely hidden here — they are never asked
    // for (NFR-01, and Alex's item 3: a bank's report stays inside the bank).
    const paths = [...new Set(sent.map((s) => s.path))].sort();
    expect(paths).toEqual([AUTHORITIES_PATH, CHANGES_PATH, ME_PATH, REFRESH_PATH].sort());
    expect(sent.every((s) => s.method === 'get' || s.path === REFRESH_PATH)).toBe(true);
    expect(container.textContent).not.toMatch(/case|footprint|report|owner|assigned/i);
  });

  it('says the queue is clear when nothing is waiting, and points at the coverage log', async () => {
    server({ status: 200, data: { items: [], total: 0 } });
    renderIn(<ChangeFactsScreen />);
    expect(await screen.findByText('No change facts waiting')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'See the coverage log' })).toHaveAttribute('href', '/console/sources');
  });

  it('offers a retry when the queue could not be read', async () => {
    const sent = server({ status: 500, data: { code: 'server_error', detail: 'no' } });
    renderIn(<ChangeFactsScreen />);
    expect(await screen.findByText('Could not load the change facts')).toBeInTheDocument();
    const before = queryOf(sent).length;
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(queryOf(sent).length).toBeGreaterThan(before));
  });

  it('is loading before the first page arrives', () => {
    server({ status: 200, data: { items: [], total: 0 } });
    const { container } = renderIn(<ChangeFactsScreen />);
    expect(container.querySelector('[data-loading-state]')).not.toBeNull();
  });

  it('shows the Restricted screen, naming the grant, to a console session without proposals.review', async () => {
    server({ status: 200, data: { items: [], total: 0 } });
    renderIn(
      <PermissionsProvider permissions={['tenants.manage', 'agent_definitions.manage']}>
        <ConsoleChangeFactsPage />
      </PermissionsProvider>,
    );
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByRole('heading', { name: 'This page is not available to you' })).toBeInTheDocument();
    expect(alert).toHaveTextContent('Needs proposals review');
  });
});
