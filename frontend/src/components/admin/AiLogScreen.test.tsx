import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AiLogScreen } from '@/components/admin/AiLogScreen';
import type { AiGeneration } from '@/features/governance/types';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// The AI log (AUD-02): each model call with its purpose, model, review state,
// sources and a reader's verdict; a row opens to what the model wrote with
// the AI label kept until a person confirmed it; filters by purpose, review
// state and one record picked from a row.

const approver = {
  user: { id: 'u1', email: 'maria@bank.example', name: 'Maria Ek', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['ai_log.read'],
  platformRoles: [],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

function row(overrides: Partial<AiGeneration>): AiGeneration {
  return {
    id: 'g0',
    purpose: 'answer',
    model: 'mock',
    modelVersion: '0',
    modelMetadataReportedByAgent: false,
    promptTemplate: '',
    promptHash: 'abc',
    subjectType: 'ai_generation',
    subjectId: 'g0',
    output: 'An answer.',
    citations: [],
    status: 'draft',
    reviewedBy: null,
    reviewedAt: null,
    feedback: '',
    feedbackNote: '',
    inputTokens: 1,
    outputTokens: 1,
    stopReason: 'end_turn',
    tenantScoped: true,
    createdAt: '2026-09-22T08:00:00Z',
    ...overrides,
  };
}

const answer = row({
  id: 'g1',
  subjectId: 'g1',
  output: 'Payments for research must come from a separate account. [1]',
  citations: [{ label: 'FFFS 2017:2, chapter 7', url: 'https://www.fi.se/fffs-2017-2' }],
  feedback: 'wrong',
  feedbackNote: 'It misses the exemption.',
});

const soWhat = row({
  id: 'g2',
  purpose: 'so_what',
  model: 'claude-opus-5',
  modelVersion: '2026-05-01',
  modelMetadataReportedByAgent: true,
  subjectType: 'regulatory_change',
  subjectId: 'c1',
  output: 'Teams that pay for research should confirm the criteria.',
  status: 'confirmed',
  reviewedBy: { id: 'u2', name: 'Anna Nilsson' },
  reviewedAt: '2026-09-22T09:12:00Z',
  tenantScoped: false,
});

function renderScreen(logAnswer: (sent: Sent) => Answer): Sent[] {
  const sent = installAdapter((s) => {
    if (s.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (s.path === '/api/v1/me') return { status: 200, data: approver };
    if (s.path === '/api/v1/ai-generations') return logAnswer(s);
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <AiLogScreen />
    </Query>,
  );
  return sent;
}

const logCalls = (sent: Sent[]) => sent.filter((s) => s.path === '/api/v1/ai-generations').map((s) => s.params);

describe('AI log', () => {
  beforeEach(() => {
    resetApiForTests();
  });

  it('lists each call with purpose, review state, verdict, model, subject and sources', async () => {
    renderScreen(() => ({ status: 200, data: { items: [answer, soWhat], total: 2 } }));
    const first = await screen.findByText('Marked wrong');
    const answerRow = first.closest('[data-ai-row]') as HTMLElement;
    expect(answerRow).toHaveAttribute('data-generation-id', 'g1');
    expect(within(answerRow).getByText('Ask answer')).toBeInTheDocument();
    expect(within(answerRow).getByText('Not yet reviewed')).toBeInTheDocument();
    expect(within(answerRow).getByText('mock 0')).toBeInTheDocument();
    expect(within(answerRow).getByText('1 source')).toBeInTheDocument();
    expect(answerRow.querySelector('time')).toHaveAttribute('dateTime', '2026-09-22T08:00:00Z');
    // An answer is its own subject: nothing to narrow to or open.
    expect(within(answerRow).queryByRole('button', { name: 'Only this record' })).toBeNull();

    const soWhatRow = document.querySelector('[data-generation-id="g2"]') as HTMLElement;
    expect(within(soWhatRow).getByText('So what?')).toBeInTheDocument();
    expect(within(soWhatRow).getByText('Confirmed')).toBeInTheDocument();
    expect(within(soWhatRow).getByText('claude-opus-5 2026-05-01')).toBeInTheDocument();
    expect(within(soWhatRow).getByText('Model as reported by the agent')).toBeInTheDocument();
    expect(within(soWhatRow).getByText('No sources')).toBeInTheDocument();
    expect(within(soWhatRow).getByRole('link', { name: 'Open the change' })).toHaveAttribute('href', '/watch/c1');
    expect(screen.getByText('1 to 2 of 2')).toBeInTheDocument();
  });

  it('opens a row to what the model wrote, its sources and the reason, labelled AI until confirmed', async () => {
    renderScreen(() => ({ status: 200, data: { items: [answer, soWhat], total: 2 } }));
    await screen.findByText('Marked wrong');
    const answerRow = document.querySelector('[data-generation-id="g1"]') as HTMLElement;
    expect(within(answerRow).queryByText(answer.output)).toBeNull();

    const toggle = within(answerRow).getByRole('button', { name: 'Show what it wrote' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(within(answerRow).getByRole('button', { name: 'Hide what it wrote' })).toHaveAttribute('aria-expanded', 'true');
    expect(within(answerRow).getByText('Written by AI. No person has confirmed it.')).toBeInTheDocument();
    expect(within(answerRow).getByText(answer.output)).toBeInTheDocument();
    const source = within(within(answerRow).getByRole('list', { name: 'Sources' })).getByRole('link', { name: 'FFFS 2017:2, chapter 7' });
    expect(source).toHaveAttribute('href', 'https://www.fi.se/fffs-2017-2');
    expect(source).toHaveAttribute('rel', 'noopener noreferrer');
    expect(within(answerRow).getByText('Reason given: It misses the exemption.')).toBeInTheDocument();

    const soWhatRow = document.querySelector('[data-generation-id="g2"]') as HTMLElement;
    fireEvent.click(within(soWhatRow).getByRole('button', { name: 'Show what it wrote' }));
    expect(within(soWhatRow).queryByText('Written by AI. No person has confirmed it.')).toBeNull();
    expect(within(soWhatRow).getByText(/^Confirmed by Anna Nilsson, /)).toBeInTheDocument();
  });

  it('keeps the AI label on a rewritten draft and names who rewrote it', async () => {
    const edited = row({ id: 'g3', purpose: 'so_what', subjectType: 'regulatory_change', subjectId: 'c2', status: 'edited', reviewedBy: { id: 'u2', name: 'Anna Nilsson' }, reviewedAt: '2026-09-22T09:12:00Z' });
    renderScreen(() => ({ status: 200, data: { items: [edited], total: 1 } }));
    fireEvent.click(await screen.findByRole('button', { name: 'Show what it wrote' }));
    expect(screen.getByText('Written by AI. No person has confirmed it.')).toBeInTheDocument();
    expect(screen.getByText(/^Rewritten by Anna Nilsson, .*The words below are the AI draft\.$/)).toBeInTheDocument();
  });

  it('filters by purpose, review state and one record, each from the first page', async () => {
    const sent = renderScreen(() => ({ status: 200, data: { items: [soWhat], total: 41 } }));
    await screen.findByText('So what?', { selector: '[data-ai-row] *' });
    fireEvent.click(screen.getByRole('button', { name: 'Older' }));
    await waitFor(() => expect(logCalls(sent).at(-1)).toEqual({ offset: 20, limit: 20 }));

    fireEvent.change(screen.getByLabelText('Purpose'), { target: { value: 'so_what' } });
    await waitFor(() => expect(logCalls(sent).at(-1)).toEqual({ purpose: 'so_what', offset: 0, limit: 20 }));
    fireEvent.change(screen.getByLabelText('Review'), { target: { value: 'confirmed' } });
    await waitFor(() => expect(logCalls(sent).at(-1)).toEqual({ purpose: 'so_what', status: 'confirmed', offset: 0, limit: 20 }));

    fireEvent.click(await screen.findByRole('button', { name: 'Only this record' }));
    await waitFor(() => expect(logCalls(sent).at(-1)).toEqual({ purpose: 'so_what', status: 'confirmed', subjectId: 'c1', offset: 0, limit: 20 }));
    const chip = screen.getByRole('button', { name: 'Record: regulatory change ✕' });

    fireEvent.click(chip);
    await waitFor(() => expect(logCalls(sent).at(-1)).toEqual({ purpose: 'so_what', status: 'confirmed', offset: 0, limit: 20 }));
    fireEvent.click(screen.getByRole('button', { name: 'Clear the filters' }));
    await waitFor(() => expect(logCalls(sent).at(-1)).toEqual({ offset: 0, limit: 20 }));
    expect(screen.queryByRole('button', { name: 'Clear the filters' })).toBeNull();
  });

  it('offers only the purposes a bank can see', async () => {
    renderScreen(() => ({ status: 200, data: { items: [], total: 0 } }));
    await screen.findByText('Nothing logged yet');
    const options = within(screen.getByLabelText('Purpose')).getAllByRole('option').map((o) => (o as HTMLOptionElement).value);
    expect(options).toEqual(['', 'so_what', 'change_summary', 'scope_suggestion', 'link_suggestion', 'translation', 'answer']);
    const states = within(screen.getByLabelText('Review')).getAllByRole('option').map((o) => (o as HTMLOptionElement).value);
    expect(states).toEqual(['', 'draft', 'confirmed', 'edited', 'rejected']);
  });

  it('says nothing is logged, and says so differently under a filter', async () => {
    renderScreen(() => ({ status: 200, data: { items: [], total: 0 } }));
    expect(await screen.findByText('Every model call appears here as it is made.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Review'), { target: { value: 'rejected' } });
    expect(await screen.findByText('No model call matches these filters.')).toBeInTheDocument();
  });

  it('shows the error state with a retry when the log does not answer', async () => {
    const sent = renderScreen((s) => (logCalls([s]).length > 0 ? { status: 500, data: { code: 'server_error', detail: 'Down.' } } : { status: 200 }));
    expect(await screen.findByText('Could not load the AI log')).toBeInTheDocument();
    const before = logCalls(sent).length;
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(logCalls(sent).length).toBe(before + 1));
  });

  it('names the missing grant when the server refuses the read', async () => {
    renderScreen(() => ({ status: 403, data: { code: 'permission_denied', detail: 'Missing permission.', requiredPermission: 'ai_log.read' } }));
    expect(await screen.findByText('This page is not available to you')).toBeInTheDocument();
    expect(screen.getByText(/ai log read/)).toBeInTheDocument();
  });
});
