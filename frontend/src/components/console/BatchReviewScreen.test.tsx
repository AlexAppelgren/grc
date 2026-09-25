import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { setStepUpHandler, tokenStore } from '@/shared/utils/api-client';

import type { ProposalBatch, ProposalBatchRow } from '@/features/proposals/types';
import { BatchReviewScreen } from './BatchReviewScreen';

// /console/queue/batches/[batchId] (design/screens/console-queue-batch.html; PRO-04):
// rows decided as drafts, undoable, a rejection only with a reason from the list; the
// drafts and the rest sent in one decision that asks for a passkey; the four-eyes and
// stale refusals rendered from their codes; the result with its counts. The server is
// the enforcer: whoever filed the batch sees the notice and no decision.

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

const BATCH = '/api/v1/proposal-batches/b-1';
const DECIDE = `${BATCH}/decide`;
const DECIDED_AT = '2026-09-25T09:40:00Z';

const reasons = [
  { key: 'wrong_scope', label: 'Wrong scope', kind: null, active: true, extra: {} },
  { key: 'bad_source', label: 'Bad source', kind: null, active: true, extra: {} },
];

const terms = [
  { id: 't-1', key: 'client_money', label: 'Client money', dimension: 'service_type' },
  { id: 't-2', key: 'safeguarding', label: 'Safeguarding', dimension: 'service_type' },
];

function row(id: string, title: string, overrides: Partial<ProposalBatchRow> = {}): ProposalBatchRow {
  return {
    id,
    subjectType: 'obligation',
    subjectId: `obl-${id}`,
    target: { id: `obl-${id}`, title, referenceLabel: '8 kap. 1 §', instrumentShortName: 'MiFID II' },
    before: { terms: ['service_type:safeguarding'] },
    after: { terms: ['service_type:client_money', 'service_type:safeguarding'] },
    source: 'https://www.fi.se/guidance',
    stale: false,
    decision: 'pending',
    rejectionCode: '',
    decidedBy: null,
    decidedAt: null,
    ...overrides,
  };
}

function batch(overrides: Partial<ProposalBatch> = {}): ProposalBatch {
  return {
    id: 'b-1',
    kind: 'obligation_scope',
    status: 'open',
    title: 'Add the term Client money to 2 obligations',
    targetType: '',
    targetId: null,
    changeId: null,
    payload: {},
    fieldSources: {},
    scopeSuggestion: [],
    sourceLabel: 'FIN-FSA, Guidance 4/2026',
    sourceUrl: 'https://www.finanssivalvonta.fi/guidance',
    riskFlags: [],
    effectiveFrom: null,
    origin: 'user',
    agentRunId: null,
    model: '',
    proposedBy: { id: 'u20', name: 'Maria Ek' },
    proposedByAgent: null,
    fromOrganisation: false,
    reviewedBy: null,
    reviewedByAgent: null,
    correctedBy: null,
    correctedByAgent: null,
    reviewedAt: null,
    rejectionCode: '',
    reviewNote: '',
    appliedAt: null,
    isBatch: true,
    rowCount: 2,
    createdAt: '2026-09-24T12:10:00Z',
    rows: [row('r-1', 'Keep client money in a segregated account'), row('r-2', 'Hold own funds against operational risk')],
    ...overrides,
  };
}

type Answer = { status: number; data?: unknown };

/** The server: the session, the batch, the reason list and the terms, and `decide` for the decision. */
function serve(current: ProposalBatch, decide: (body: unknown, count: number) => Answer = () => ({ status: 200, data: current })): Sent[] {
  let decisions = 0;
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: editor };
    if (sent.path === BATCH) return { status: 200, data: current };
    if (sent.path === '/api/v1/vocab/rejection_reason') return { status: 200, data: reasons };
    if (sent.path === '/api/v1/taxonomy/terms') return { status: 200, data: { items: terms, total: terms.length } };
    if (sent.path === DECIDE) {
      decisions += 1;
      return decide(sent.body, decisions);
    }
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

const decisionsSent = (sent: Sent[]) => sent.filter((s) => s.path === DECIDE).map((s) => s.body);

function renderScreen(): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <BatchReviewScreen batchId="b-1" />
      </LocaleProvider>
    </Query>,
  );
}

function card(id: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(`[data-batch-row="${id}"]`);
  if (element === null) throw new Error(`no row ${id}`);
  return element;
}

describe('the batch review', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
    setStepUpHandler(() => Promise.resolve(true));
  });

  it('shows what was asked, by whom, and every row before and after, by the terms\' labels', async () => {
    serve(batch());
    renderScreen();
    expect(await screen.findByRole('heading', { level: 1, name: 'Add the term Client money to 2 obligations' })).toBeInTheDocument();
    expect(screen.getByText('Re-tag')).toBeInTheDocument();
    expect(screen.getByText(/^Maria Ek, /)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'FIN-FSA, Guidance 4/2026' })).toHaveAttribute('href', 'https://www.finanssivalvonta.fi/guidance');
    expect(screen.getByText('2 obligations')).toBeInTheDocument();
    const first = card('r-1');
    expect(within(first).getByText('Keep client money in a segregated account')).toBeInTheDocument();
    expect(within(first).getByText('MiFID II')).toBeInTheDocument();
    expect(within(first).getByText('Added when approved')).toBeInTheDocument();
    await waitFor(() => expect(within(first).getAllByText('Client money')).toHaveLength(1));
    expect(within(first).getAllByText('Safeguarding')).toHaveLength(2);
  });

  it('decides a row as a draft that can be undone, and a rejection only with a reason', async () => {
    serve(batch());
    renderScreen();
    await screen.findByRole('heading', { level: 1 });
    fireEvent.click(within(card('r-1')).getByRole('button', { name: 'Approve' }));
    expect(within(card('r-1')).getByText('Approved')).toBeInTheDocument();
    expect(screen.getByText('1 approved')).toBeInTheDocument();
    fireEvent.click(within(card('r-1')).getByRole('button', { name: 'Undo' }));
    expect(within(card('r-1')).getByText('Added when approved')).toBeInTheDocument();

    fireEvent.click(within(card('r-2')).getByRole('button', { name: 'Reject' }));
    fireEvent.click(within(card('r-2')).getByRole('button', { name: 'Reject the row' }));
    expect(within(card('r-2')).getByRole('alert')).toHaveTextContent('Choose why this row is rejected.');
    await waitFor(() => expect(within(card('r-2')).getAllByRole('option')).toHaveLength(3));
    fireEvent.change(within(card('r-2')).getByLabelText('Reason'), { target: { value: 'wrong_scope' } });
    fireEvent.click(within(card('r-2')).getByRole('button', { name: 'Reject the row' }));
    expect(within(card('r-2')).getByText('Rejected')).toBeInTheDocument();
    expect(within(card('r-2')).getByText('Wrong scope')).toBeInTheDocument();
    expect(screen.getByText('1 rejected')).toBeInTheDocument();
    expect(screen.getByText('1 not decided')).toBeInTheDocument();
  });

  it('sends the drafts and approves the rest in one call behind the passkey, then shows the result', async () => {
    const decided = batch({
      status: 'approved',
      rows: [
        row('r-1', 'Keep client money in a segregated account', { decision: 'approved', decidedBy: { id: 'u10', name: 'Ida Holm' }, decidedAt: DECIDED_AT }),
        row('r-2', 'Hold own funds against operational risk', { decision: 'rejected', rejectionCode: 'wrong_scope', decidedBy: { id: 'u10', name: 'Ida Holm' }, decidedAt: DECIDED_AT }),
      ],
    });
    const prompts: number[] = [];
    setStepUpHandler(() => {
      prompts.push(1);
      return Promise.resolve(true);
    });
    const sent = serve(batch(), (_, count) => (count === 1 ? { status: 403, data: { code: 'step_up_required', detail: 'Confirm with your passkey.' } } : { status: 200, data: decided }));
    renderScreen();
    await screen.findByRole('heading', { level: 1 });
    fireEvent.click(within(card('r-2')).getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(within(card('r-2')).getAllByRole('option')).toHaveLength(3));
    fireEvent.change(within(card('r-2')).getByLabelText('Reason'), { target: { value: 'wrong_scope' } });
    fireEvent.click(within(card('r-2')).getByRole('button', { name: 'Reject the row' }));
    expect(screen.getByText('Approving asks for your passkey.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve the rest' }));

    const result = await screen.findByRole('heading', { name: '1 changed, 1 did not' });
    expect(result.closest('[data-batch-result]')).toHaveTextContent(/Decided by Ida Holm, .+\. Each bank sees the change under Library updates\./);
    expect(prompts).toHaveLength(1);
    const body = { rows: [{ rowId: 'r-2', decision: 'rejected', rejectionCode: 'wrong_scope' }], rest: 'approved', restRejectionCode: '', note: '' };
    expect(decisionsSent(sent)).toEqual([body, body]);
    expect(screen.queryByRole('button', { name: 'Approve the rest' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
  });

  it('rejects every row with one reason from the list, and changes nothing without one', async () => {
    const sent = serve(batch(), () => ({ status: 200, data: batch({ status: 'rejected', rows: [row('r-1', 'A', { decision: 'rejected', rejectionCode: 'bad_source', decidedAt: DECIDED_AT }), row('r-2', 'B', { decision: 'rejected', rejectionCode: 'bad_source', decidedAt: DECIDED_AT })] }) }));
    renderScreen();
    await screen.findByRole('heading', { level: 1 });
    fireEvent.click(screen.getByRole('button', { name: 'Reject all' }));
    const dialog = await screen.findByRole('dialog', { name: 'Reject all 2 rows?' });
    const submit = within(dialog).getByRole('button', { name: 'Reject all' });
    expect(submit).toBeDisabled();
    await waitFor(() => expect(within(dialog).getAllByRole('option')).toHaveLength(3));
    fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'bad_source' } });
    fireEvent.click(submit);
    expect(await screen.findByRole('heading', { name: '0 changed, 2 did not' })).toBeInTheDocument();
    expect(decisionsSent(sent)).toEqual([{ rows: [], rest: 'rejected', restRejectionCode: 'bad_source', note: '' }]);
  });

  it('renders the four-eyes refusal from its code, in place', async () => {
    serve(batch(), () => ({ status: 409, data: { code: 'four_eyes_violation', detail: 'server words' } }));
    renderScreen();
    await screen.findByRole('heading', { level: 1 });
    fireEvent.click(screen.getByRole('button', { name: 'Approve the rest' }));
    const alert = await screen.findByText('Deciding a batch you asked for is not allowed.');
    expect(alert).toHaveAttribute('data-problem-code', 'four_eyes_violation');
    expect(card('r-1')).toBeInTheDocument();
  });

  it('offers only Reject on a stale row, holds Approve the rest until it is decided, and renders stale_write from its code', async () => {
    serve(batch({ rows: [row('r-1', 'Changed since', { stale: true }), row('r-2', 'Still current')] }), () => ({ status: 409, data: { code: 'stale_write', detail: 'server words' } }));
    renderScreen();
    await screen.findByRole('heading', { level: 1 });
    expect(within(card('r-1')).getByText('Changed since it was asked')).toBeInTheDocument();
    expect(within(card('r-1')).queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Approve the rest' })).toBeDisabled();

    fireEvent.click(within(card('r-1')).getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(within(card('r-1')).getAllByRole('option')).toHaveLength(3));
    fireEvent.change(within(card('r-1')).getByLabelText('Reason'), { target: { value: 'wrong_scope' } });
    fireEvent.click(within(card('r-1')).getByRole('button', { name: 'Reject the row' }));
    fireEvent.click(screen.getByRole('button', { name: 'Approve the rest' }));
    const alert = await screen.findByText('An obligation changed since this batch was asked for. Reject its row, or ask for the re-tag again.', { selector: '[data-problem-code]' });
    expect(alert).toHaveAttribute('data-problem-code', 'stale_write');
  });

  it('shows whoever filed the batch the four-eyes notice and no decision', async () => {
    serve(batch({ proposedBy: { id: 'u10', name: 'Ida Holm' } }));
    renderScreen();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('alert')).toHaveTextContent('You asked for this re-tag. A second library editor has to decide it.');
    expect(screen.getByText('Yours')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Approve the rest' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject all' })).toBeNull();
  });

  it('answers a batch that does not exist with the not-found screen, and a refusal with the restricted one', async () => {
    installAdapter((sent) => (sent.path === '/api/v1/me' ? { status: 200, data: editor } : { status: 404, data: { code: 'not_found', detail: 'Not found.' } }));
    renderScreen();
    expect(await screen.findByText('This batch does not exist, or it is not a batch.')).toBeInTheDocument();
  });

  it('renders the server\'s structured 403 as the restricted screen', async () => {
    installAdapter((sent) =>
      sent.path === '/api/v1/me' ? { status: 200, data: editor } : { status: 403, data: { code: 'permission_denied', detail: 'You do not have access to this.', requiredPermission: 'proposals.review' } },
    );
    renderScreen();
    expect(await screen.findByRole('heading', { name: 'This page is not available to you' })).toBeInTheDocument();
  });
});
