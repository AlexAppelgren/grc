import { render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { ChangeRow } from '@/features/watch/api';
import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { ObligationRelatedChanges, presentOpenChanges } from './ObligationRelatedChanges';

// "Related changes" on design/screens/tenant-obligation.html: the reforms an
// agent read against this duty, in the order the read gave them, with the
// open-change count the route computed and never a count of the page.

const t = createT('en');

const fact = (key: string, label: string, suggested = false) => ({ ref: { key, kind: null, label }, confidence: 0.9, suggested });

const confirmedLink: ChangeRow = {
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
  case: null,
} as ChangeRow;

const suggestedLink: ChangeRow = {
  ...confirmedLink,
  id: 'c-2',
  stableKey: 'chg-eu-2026-costs',
  title: 'ESMA consults on costs and charges disclosure',
  changeType: fact('proposal', 'Proposal', true),
  suggestedUrgency: { key: 'monitor', kind: null, label: 'Monitor' },
  keyDate: null,
  keyDateLabel: null,
};

const SESSION = { user: { locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, enrolmentPending: false, permissions: ['watch.read'] };

function serve(answer: Answer): Sent[] {
  return installAdapter((sent) => (sent.path.includes('/changes') ? answer : { status: 200, data: SESSION }));
}

function shell(children: ReactNode): ReactNode {
  const { wrapper: Query } = queryWrapper();
  return (
    <Query>
      <LocaleProvider locale="en">{children}</LocaleProvider>
    </Query>
  );
}

function renderPanel(): void {
  render(shell(<ObligationRelatedChanges obligationId="o-1" />));
}

describe('the open-change count', () => {
  it('is a computed pill whose tone comes from its slot, and is absent at zero', () => {
    expect(presentOpenChanges(2, t).map((pill) => [pill.label, pill.tone])).toEqual([['2 open changes', 'notice']]);
    expect(presentOpenChanges(1, t)[0]!.label).toBe('1 open change');
    expect(presentOpenChanges(0, t)).toEqual([]);
  });
});

describe('the related changes panel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the route, keeps the order it was given, and shows the route’s own count', async () => {
    const sent = serve({ status: 200, data: { items: [confirmedLink, suggestedLink], total: 2, openCount: 2 } });
    renderPanel();

    await screen.findByRole('heading', { level: 2, name: 'Related changes' });
    const rows = await screen.findAllByRole('link');
    expect(rows.map((row) => row.getAttribute('href'))).toEqual(['/watch/c-1', '/watch/c-2']);
    // The count is the route's, over every linked change, never the page's.
    expect(screen.getByText('2 open changes')).toHaveAttribute('data-pill', 'notice');
    expect(sent.some((call) => call.path === '/api/v1/obligations/o-1/changes')).toBe(true);
  });

  it('each row carries its change type, its urgency, its key date and the suggestion marker', async () => {
    serve({ status: 200, data: { items: [confirmedLink, suggestedLink], total: 2, openCount: 1 } });
    renderPanel();

    const first = await screen.findByText(confirmedLink.title);
    const row = first.closest<HTMLElement>('[data-related-change]')!;
    expect(within(row).getAllByText(/./, { selector: '[data-pill]' }).map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['Adopted rule', 'notice'],
      ['Act now', 'negative'],
    ]);
    expect(within(row).getByText('In force 1 Oct 2026')).toBeInTheDocument();
    expect(within(row).getByText('Finansinspektionen')).toBeInTheDocument();

    const second = screen.getByText(suggestedLink.title).closest<HTMLElement>('[data-related-change]')!;
    expect(within(second).getByText('Suggested by the agent')).toHaveAttribute('data-pill', 'information');
    expect(within(second).getByText('Date not set')).toBeInTheDocument();
  });

  it('says how many of a longer list it is showing rather than implying the page is all of it', async () => {
    serve({ status: 200, data: { items: [confirmedLink], total: 24, openCount: 3 } });
    renderPanel();
    expect(await screen.findByText('Showing 1 of 24')).toBeInTheDocument();
  });

  it('an obligation no change touches says so, and carries no count', async () => {
    serve({ status: 200, data: { items: [], total: 0, openCount: 0 } });
    renderPanel();
    expect(await screen.findByText('No change affects this obligation')).toBeInTheDocument();
    expect(screen.queryByText(/open change/)).not.toBeInTheDocument();
  });

  it('a reader without the permission gets the Restricted screen from the code, not the detail', async () => {
    serve({ status: 403, data: { code: 'permission_denied', detail: 'You do not have access.', requiredPermission: 'watch.read' } });
    renderPanel();
    await waitFor(() => expect(screen.getByText(/watch\.read|Watch read|read watch/i)).toBeInTheDocument());
  });

  it('a read that fails offers the way to try again', async () => {
    serve({ status: 500, data: { code: 'server_error', detail: '' } });
    renderPanel();
    expect(await screen.findByText('Could not load the related changes')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('says it is loading before the read answers', () => {
    serve({ status: 200, data: { items: [], total: 0, openCount: 0 } });
    renderPanel();
    expect(screen.getByRole('status')).toHaveAttribute('data-loading-state');
  });
});
