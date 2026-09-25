import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import PrivateProposalPage from '@/app/(tenant)/private-records/[proposalId]/page';
import PrivateRecordsPage from '@/app/(tenant)/private-records/page';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { setStepUpHandler, tokenStore } from '@/shared/utils/api-client';

import { PrivateProposalScreen } from './PrivateProposalScreen';
import { PrivateRecordsScreen } from './PrivateRecordsScreen';
import type { PrivateProposalRow } from './types';

// The bank's own queue (design/screens/tenant-private-records.html; OWN-03, PRO-03,
// INV-07): the list, the detail with the agent's draft beside its sources, approve behind
// the passkey step-up, reject with a reason, the four-eyes refusal as a state, and the
// denied and not-found states.

const QUEUE = '/api/v1/private-proposals';
const RIKSDAGEN = 'https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/lag-2010751-om-betaltjanster_sfs-2010-751/';

const officer = {
  user: { id: 'u1', email: 'officer@bank.test', name: 'Maria Ek', locale: 'en' },
  tenant: { id: 't1', name: 'Nordbank AB', slug: 'nordbank', timezone: 'Europe/Stockholm' },
  roles: [],
  permissions: ['private_records.approve'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

function row(overrides: Partial<PrivateProposalRow> = {}): PrivateProposalRow {
  return {
    id: 'p-1',
    kind: 'new_obligation',
    status: 'open',
    title: 'Add obligation: give the payer the prescribed information before a single payment',
    origin: 'agent',
    isMine: false,
    payload: {
      key: 'obl-own-psd-pre-payment-info',
      instrument: 'sfs-2010-751',
      titles: { sv: 'Ge betalaren informationen före en enstaka betalning' },
      originalLanguage: 'sv',
      refLabel: '4 kap.',
      dutyType: 'disclosure',
    },
    fieldSources: { 'titles.sv': RIKSDAGEN, dutyType: RIKSDAGEN },
    sourceUrl: RIKSDAGEN,
    createdAt: '2026-09-25T04:04:00Z',
    ...overrides,
  };
}

function serve(items: PrivateProposalRow[], extra: (sent: Sent) => Answer | undefined = () => undefined): Sent[] {
  return installAdapter((sent) => {
    const answer = extra(sent);
    if (answer !== undefined) return answer;
    if (sent.path === '/api/v1/me') return { status: 200, data: officer };
    if (sent.path === QUEUE) return { status: 200, data: { items, total: items.length } };
    if (sent.path === '/api/v1/vocab/rejection_reason') return { status: 200, data: [{ key: 'duplicate', kind: null, label: 'Duplicate', extra: {} }] };
    return { status: 404, data: { code: 'not_found', detail: 'Not in this test.' } };
  });
}

function renderIn(node: ReactNode, permissions: string[] = ['private_records.approve']) {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>{node}</PermissionsProvider>
      </LocaleProvider>
    </Query>,
  );
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
});

describe('the queue', () => {
  it('lists each proposal with its pills, the proposer, the time and the source host, linking to its page', async () => {
    serve([row(), row({ id: 'p-2', origin: 'user', isMine: true, kind: 'new_instrument', title: 'Add instrument: Lag (2010:751) om betaltjänster' })]);
    renderIn(<PrivateRecordsScreen />);
    await screen.findByRole('heading', { level: 1, name: 'Our own records' });

    const rows = await waitFor(() => {
      const found = document.querySelectorAll<HTMLElement>('[data-private-proposals] [data-private-proposal-id]');
      expect(found).toHaveLength(2);
      return [...found];
    });
    const [agent, mine] = rows as [HTMLElement, HTMLElement];
    expect(agent).toHaveAttribute('href', '/private-records/p-1');
    expect([...agent.querySelectorAll('[data-pill]')].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['New obligation', 'notice'],
      ['Waiting', 'warning'],
      ['Proposed by our agent', 'brand'],
    ]);
    expect(within(agent).getByText('Source: riksdagen.se')).toBeInTheDocument();
    expect([...mine.querySelectorAll('[data-pill]')].map((pill) => pill.textContent)).toEqual(['New instrument', 'Waiting']);
    expect(within(mine).getByText('Proposed by you')).toBeInTheDocument();
  });

  it('says nothing is waiting, and points at the regulatory scope', async () => {
    serve([]);
    renderIn(<PrivateRecordsScreen />);
    expect(await screen.findByRole('heading', { name: 'Nothing waiting' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'See the regulatory scope' })).toHaveAttribute('href', '/admin/footprint');
  });

  it('pages by the route\'s own total', async () => {
    const sent = installAdapter((s) => {
      if (s.path === '/api/v1/me') return { status: 200, data: officer };
      const offset = Number((s.params as { offset?: string } | null)?.offset ?? 0);
      return { status: 200, data: { items: [row({ id: `p-${offset}` })], total: 25 } };
    });
    renderIn(<PrivateRecordsScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Next' }));
    await waitFor(() => expect(document.querySelector('[data-private-proposal-id="p-20"]')).not.toBeNull());
    expect(sent.filter((s) => s.path === QUEUE).map((s) => s.params)).toEqual([{ limit: '20' }, { limit: '20', offset: '20' }]);
  });

  it('offers a retry when the queue cannot be read', async () => {
    serve([], (s) => (s.path === QUEUE ? { status: 501, data: { code: 'not_built', detail: 'Not built yet.' } } : undefined));
    renderIn(<PrivateRecordsScreen />);
    expect(await screen.findByRole('heading', { name: 'Could not load our own records' })).toBeInTheDocument();
  });

  it('is denied without private_records.approve, at the client gate and at the server alike', async () => {
    serve([]);
    renderIn(<PrivateRecordsPage />, ['library.read']);
    expect(screen.getByRole('alert')).toHaveTextContent('Needs private records approve');

    resetApiForTests();
    tokenStore.set('tok');
    serve([], (s) => (s.path === QUEUE ? { status: 403, data: { code: 'permission_denied', detail: '', requiredPermission: 'private_records.approve' } } : undefined));
    renderIn(<PrivateRecordsScreen />);
    expect(await screen.findByText('Needs private records approve')).toBeInTheDocument();
  });
});

describe('a proposal', () => {
  it('shows the agent\'s draft under its label, each field beside its numbered source', async () => {
    serve([row()]);
    renderIn(<PrivateProposalScreen proposalId="p-1" />);
    await screen.findByRole('heading', { level: 1, name: row().title });

    expect(document.querySelector('[data-private-drafted]')).toHaveTextContent('Drafted by our agent');
    const sources = document.querySelector('[data-private-sources]') as HTMLElement;
    expect(within(sources).getByRole('link', { name: 'riksdagen.se' })).toHaveAttribute('href', RIKSDAGEN);
    const title = document.querySelector('[data-private-adds] [data-field="titles.sv"]') as HTMLElement;
    expect(title).toHaveTextContent('Title (Swedish)');
    expect(title).toHaveTextContent('Source 1');
    expect(within(title).getByText('Ge betalaren informationen före en enstaka betalning')).toHaveAttribute('lang', 'sv');
  });

  it('approves after the confirmation and the passkey, and says it is in our inventory as Private to us', async () => {
    let asked = 0;
    const sent = serve([row()], (s) => {
      if (s.path !== `${QUEUE}/p-1/approve`) return undefined;
      asked += 1;
      // The route asks for a fresh passkey first; the client runs it and retries once.
      return asked === 1 ? { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } } : { status: 200, data: row({ status: 'approved' }) };
    });
    let steppedUp = 0;
    setStepUpHandler(async () => {
      steppedUp += 1;
      return true;
    });
    renderIn(<PrivateProposalScreen proposalId="p-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('It goes into our inventory as Private to us');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve with passkey' }));

    expect(await screen.findByText('Approved. It is in our inventory as Private to us.')).toBeInTheDocument();
    expect(document.querySelector('[data-private-drafted]')).toBeNull();
    expect(steppedUp).toBe(1);
    expect(sent.filter((s) => s.path === `${QUEUE}/p-1/approve`).map((s) => s.body)).toEqual([{ note: '' }, { note: '' }]);
  });

  it('rejects only with a reason and a note, and sends the reason\'s key', async () => {
    const sent = serve([row()], (s) => (s.path === `${QUEUE}/p-1/reject` ? { status: 200, data: row({ status: 'rejected' }) } : undefined));
    renderIn(<PrivateProposalScreen proposalId="p-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject' }));
    expect(within(dialog).getByText('Give a reason and say what is wrong.')).toBeInTheDocument();
    expect(sent.some((s) => s.path.endsWith('/reject'))).toBe(false);

    await within(dialog).findByRole('option', { name: 'Duplicate' });
    fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'duplicate' } });
    fireEvent.change(within(dialog).getByLabelText('What is wrong'), { target: { value: ' We already hold this duty. ' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject' }));

    expect(await screen.findByText('Rejected.')).toBeInTheDocument();
    expect(sent.filter((s) => s.path.endsWith('/reject')).map((s) => s.body)).toEqual([{ rejectionCode: 'duplicate', note: 'We already hold this duty.' }]);
  });

  it('offers its own proposer no decision, only the four-eyes notice', async () => {
    serve([row({ origin: 'user', isMine: true })]);
    renderIn(<PrivateProposalScreen proposalId="p-1" />);
    expect(await screen.findByText('You proposed this, so someone else has to approve it.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
    expect(document.querySelector('[data-private-drafted]')).toBeNull();
  });

  it('reads the server\'s four-eyes refusal and a decision that came second as the same states', async () => {
    let answer = { status: 409, data: { code: 'four_eyes_violation', detail: 'no' } };
    serve([row()], (s) => (s.path === `${QUEUE}/p-1/approve` ? answer : undefined));
    renderIn(<PrivateProposalScreen proposalId="p-1" />);
    const approve = async () => {
      fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
      fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Approve with passkey' }));
    };
    await approve();
    expect(await screen.findByText('You proposed this, so someone else has to approve it.')).toHaveAttribute('data-problem-code', 'four_eyes_violation');

    answer = { status: 409, data: { code: 'invalid_transition', detail: 'no' } };
    await approve();
    expect(await screen.findByText('Someone else decided this first.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload to see the decision' })).toBeInTheDocument();
  });

  it('renders Not found for a proposal the queue does not hold, such as another bank\'s', async () => {
    serve([row({ id: 'p-9' })]);
    renderIn(await PrivateProposalPage({ params: Promise.resolve({ proposalId: 'p-1' }) }));
    expect(await screen.findByText('There is nothing at this address in your organisation.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Our own records' })).toHaveAttribute('href', '/private-records');
  });
});
