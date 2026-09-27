import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import type { ProposalDetail } from '@/features/proposals/types';
import { ProposalDetailScreen } from './ProposalDetailScreen';

// /console/queue/[proposalId]: the decision panel names who decided. An agent
// is named as an agent and its approval reads as machine-confirmed, its note as
// the agent's, and an agent's correction never sits in a person's slot; a
// person is named by name; and a decided row naming nobody never shows an
// empty name. Whether the reader filed it is the server's isMine.

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

const AGENT = { key: 'library-confirmer', version: 1 };
const PERSON = { id: 'u20', name: 'Kari Nygaard' };
const DECIDED_AT = '2026-09-17T10:14:00Z';

function detail(overrides: Partial<ProposalDetail>): ProposalDetail {
  return {
    id: 'p-1',
    kind: 'new_obligation_version',
    status: 'open',
    title: 'Add version 2 of the research payment obligation',
    targetType: 'obligation',
    targetId: 'obl-1',
    changeId: null,
    payload: { summaries: { sv: 'Investeringsanalys.' }, originalLanguage: 'sv' },
    fieldSources: {},
    scopeSuggestion: [],
    sourceLabel: '',
    sourceUrl: '',
    riskFlags: [],
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
    isBatch: false,
    rowCount: 0,
    createdAt: '2026-09-16T07:12:00Z',
    target: null,
    isMine: false,
    language: 'sv',
    currentSummary: null,
    proposedText: '',
    diff: [],
    sources: [],
    scopeBefore: [],
    scopeAfter: null,
    rejectionReason: null,
    appliedVersion: null,
    ...overrides,
  };
}

function renderWith(row: ProposalDetail): void {
  installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: editor };
    if (sent.path === `/api/v1/proposals/${row.id}`) return { status: 200, data: row };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <ProposalDetailScreen proposalId={row.id} />
      </LocaleProvider>
    </Query>,
  );
}

async function decision(marker: 'applied' | 'rejected'): Promise<HTMLElement> {
  await screen.findByRole('heading', { level: 1 });
  const panel = document.querySelector<HTMLElement>(`[data-proposal-${marker}]`);
  if (panel === null) throw new Error(`no ${marker} panel`);
  return panel;
}

describe('the decision panel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads an agent\'s approval as machine-confirmed, naming the agent, and labels its note as the agent\'s', async () => {
    renderWith(detail({ status: 'approved', appliedAt: DECIDED_AT, reviewedAt: DECIDED_AT, reviewedByAgent: AGENT, reviewNote: 'Matches the adopted text.' }));
    const panel = await decision('applied');
    expect(panel).toHaveTextContent(/^Applied .+ by the agent library-confirmer, machine-confirmed\./);
    expect(panel).toHaveTextContent("The agent's note: Matches the adopted text.");
    expect(panel).not.toHaveTextContent('Note to the proposer');
  });

  it('names the agent that corrected the payload as an agent, on a line of its own', async () => {
    renderWith(detail({ status: 'approved', appliedAt: DECIDED_AT, reviewedAt: DECIDED_AT, reviewedByAgent: AGENT, correctedByAgent: AGENT }));
    const panel = await decision('applied');
    expect(panel.querySelector('[data-proposal-corrected-by-agent]')).toHaveTextContent('The agent library-confirmer corrected the proposal before applying it.');
  });

  it('names the agent that rejected it, and labels its note as the agent\'s', async () => {
    renderWith(detail({ status: 'rejected', reviewedAt: DECIDED_AT, reviewedByAgent: AGENT, rejectionCode: 'bad_source', reviewNote: 'The source is the consultation draft.' }));
    const panel = await decision('rejected');
    expect(panel).toHaveTextContent(/^Rejected .+ by the agent library-confirmer\./);
    expect(panel).toHaveTextContent("The agent's note: The source is the consultation draft.");
  });

  it('names a person who decided it, with their note to the proposer, and no agent line', async () => {
    renderWith(detail({ status: 'approved', appliedAt: DECIDED_AT, reviewedAt: DECIDED_AT, reviewedBy: PERSON, correctedBy: PERSON, reviewNote: 'Checked against the board decision.' }));
    const panel = await decision('applied');
    expect(panel).toHaveTextContent(/^Applied .+ by Kari Nygaard\./);
    expect(panel).toHaveTextContent('Note to the proposer: Checked against the board decision.');
    expect(panel).not.toHaveTextContent('agent');
    expect(panel.querySelector('[data-proposal-corrected-by-agent]')).toBeNull();
  });

  it('never shows an empty name when a decided proposal names nobody', async () => {
    renderWith(detail({ status: 'approved', appliedAt: DECIDED_AT, reviewedAt: DECIDED_AT }));
    const panel = await decision('applied');
    expect(panel).toHaveTextContent(/^Applied [^.]+\.$/);
    expect(panel).not.toHaveTextContent(/ by \./);
    expect(panel).not.toHaveTextContent(/ by $/);
  });

  it('shows the four-eyes notice, and no Approve, when the server says the reader filed it', async () => {
    renderWith(detail({ isMine: true }));
    expect(await screen.findByText('Someone else has to approve it.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve and apply' })).toBeNull();
  });

  it('warns a person when the screen flagged a text, and still lets them decide', async () => {
    renderWith(detail({ riskFlags: ['embedded_instructions'] }));
    expect(await screen.findByText(/reads like an instruction to an AI/)).toBeInTheDocument();
    expect(screen.getByText('Flagged')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve and apply' })).toBeInTheDocument();
  });

  it('shows no warning for a proposal the screen found nothing in', async () => {
    renderWith(detail({ riskFlags: [] }));
    await screen.findByText('Add version 2 of the research payment obligation');
    expect(screen.queryByText(/reads like an instruction to an AI/)).toBeNull();
  });
});
