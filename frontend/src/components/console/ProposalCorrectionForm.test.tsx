import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import type { ProposalRow } from '@/features/proposals/types';
import { ProposalCorrectionForm } from './ProposalCorrectionForm';

// "Correct before approving": a value the reviewer changes names the source
// they read it in, because the proposer's source vouches only for the value it
// came with (the server answers 422 source_missing otherwise). The form asks
// for that source only once something differs, and sends it for exactly the
// fields that changed.

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

const PROPOSED = { sv: 'Investeringsanalys får tas emot.', en: 'Research may be received.' };
const FRESH = 'https://www.fi.se/sv/publicerat/nyheter/2026/analysbetalningar/';

function row(): ProposalRow {
  return {
    id: 'p-1',
    kind: 'new_obligation_version',
    status: 'open',
    title: 'Add version 2 of the research payment obligation',
    targetType: 'obligation',
    targetId: 'obl-1',
    changeId: null,
    payload: { summaries: PROPOSED, originalLanguage: 'sv', effectiveFrom: '2026-10-01' },
    fieldSources: { 'summaries.sv': 'https://www.fi.se/', 'summaries.en': 'https://www.fi.se/', effectiveFrom: 'https://www.fi.se/' },
    scopeSuggestion: [],
    sourceLabel: '',
    sourceUrl: '',
    riskFlags: [],
    effectiveFrom: '2026-10-01',
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
    isMine: false,
  } as ProposalRow;
}

function renderForm(): Sent[] {
  const sent = installAdapter((request) => {
    if (request.path === '/api/v1/me') return { status: 200, data: editor };
    if (request.path === '/api/v1/proposals/p-1/approve') return { status: 200, data: { ...row(), status: 'approved' } };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <ProposalCorrectionForm proposal={row()} />
      </LocaleProvider>
    </Query>,
  );
  return sent;
}

function approvals(sent: Sent[]): Sent[] {
  return sent.filter((request) => request.path === '/api/v1/proposals/p-1/approve');
}

describe('correcting a proposal before approving it', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('asks for no source and sends none while nothing differs from the proposal', async () => {
    const sent = renderForm();
    expect(screen.queryByLabelText('Source of your correction')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Approve and apply' }));

    await waitFor(() => expect(approvals(sent)).toHaveLength(1));
    expect(approvals(sent)[0]?.body).not.toHaveProperty('fieldSources');
  });

  it('sends the fresh source for exactly the fields the reviewer changed', async () => {
    const sent = renderForm();
    fireEvent.change(screen.getByLabelText(/^Text \(English\)/), { target: { value: 'Research may be received only if paid for.' } });
    fireEvent.change(screen.getByLabelText('Source of your correction'), { target: { value: ` ${FRESH} ` } });

    fireEvent.click(screen.getByRole('button', { name: 'Approve and apply' }));

    await waitFor(() => expect(approvals(sent)).toHaveLength(1));
    expect(approvals(sent)[0]?.body).toMatchObject({
      payloadOverrides: { summaries: { sv: PROPOSED.sv, en: 'Research may be received only if paid for.' } },
      fieldSources: { 'summaries.en': FRESH },
    });
    expect(Object.keys((approvals(sent)[0]?.body as { fieldSources: object }).fieldSources)).toEqual(['summaries.en']);
  });
});
