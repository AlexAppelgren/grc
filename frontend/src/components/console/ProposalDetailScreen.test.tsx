import { render, screen, waitFor, within } from '@testing-library/react';
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
    instrumentShortName: '',
    ...overrides,
  };
}

// The reads a console session makes to label a new record's keys: two library lists, the
// jurisdictions and the terms of a dimension. Anything else is refused, as GET /authorities is.
const READS: Readonly<Record<string, unknown>> = {
  '/api/v1/vocab/instrument_level': { items: [{ key: 'eu_regulation', kind: null, label: 'EU regulation', labels: {}, usageNote: '', sortOrder: 0, active: true, isSystem: true, isDefault: false, usageCount: 0, extra: {} }], total: 1 },
  '/api/v1/vocab/duty_type': { items: [{ key: 'reporting', kind: null, label: 'Reporting', labels: {}, usageNote: '', sortOrder: 0, active: true, isSystem: true, isDefault: false, usageCount: 0, extra: {} }], total: 1 },
  '/api/v1/reference/jurisdictions': [{ key: 'eu', kind: 'supranational', label: 'European Union', parentKey: null }],
};

function renderWith(row: ProposalDetail): void {
  installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: editor };
    if (sent.path === `/api/v1/proposals/${row.id}`) return { status: 200, data: row };
    if (sent.path in READS) return { status: 200, data: READS[sent.path] };
    if (sent.path === '/api/v1/taxonomy/terms') {
      const dimension = (sent.params as { dimension?: string }).dimension;
      const items = dimension === 'regime' ? [{ id: 't1', key: 'securities', label: 'Securities', dimension: 'regime' }] : [{ id: 't2', key: 'pre_trade', label: 'Before the trade', dimension: 'lifecycle_stage' }];
      return { status: 200, data: { items, total: items.length } };
    }
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

  it('shows a new instrument\'s facts by their labels, the original title first, and plain Approve and Reject', async () => {
    renderWith(
      detail({
        kind: 'new_instrument',
        title: 'Add MAR managers\' transactions ITS',
        targetType: '',
        targetId: null,
        payload: {
          key: 'celex-32016r0523',
          titles: { sv: 'Kommissionens genomförandeförordning (EU) 2016/523', en: 'Commission Implementing Regulation (EU) 2016/523' },
          originalLanguage: 'en',
          isMachine: true,
          shortName: 'MAR managers\' transactions ITS',
          officialRef: 'Commission Implementing Regulation (EU) 2016/523',
          eliUri: 'https://data.europa.eu/eli/reg_impl/2016/523/oj',
          level: 'eu_regulation',
          jurisdiction: 'eu',
          authority: 'european-commission',
          regime: 'regime:securities',
          inForceFrom: '2016-04-06',
          inForceTo: '2030-01-01',
          inForceToPrecision: 'year',
          implementsNote: 'Article 19 of MAR',
        },
        fieldSources: { 'titles.en': 'https://eur-lex.europa.eu/eli/reg_impl/2016/523/oj', shortName: 'https://eur-lex.europa.eu/eli/reg_impl/2016/523/oj' },
      }),
    );
    const facts = await screen.findByRole('heading', { name: 'What it adds' });
    const panel = facts.closest('section') as HTMLElement;
    const fact = (field: string) => panel.querySelector(`[data-proposal-fact="${field}"]`);
    await waitFor(() => expect(fact('level')).toHaveTextContent('EU regulation'));
    await waitFor(() => expect(fact('jurisdiction')).toHaveTextContent('European Union'));
    await waitFor(() => expect(fact('regime')).toHaveTextContent('Securities'));
    const titles = within(fact('titles') as HTMLElement).getAllByText(/^(English|Swedish) \(/).map((node) => node.textContent);
    expect(titles).toEqual(['English (original)', 'Swedish (machine translation)']);
    expect(fact('shortName')).toHaveTextContent("MAR managers' transactions ITS");
    expect(within(fact('eliUri') as HTMLElement).getByRole('link')).toHaveAttribute('href', 'https://data.europa.eu/eli/reg_impl/2016/523/oj');
    expect(fact('binding')).toHaveTextContent('As its level sets it');
    expect(fact('authority')).toHaveTextContent('european-commission');
    expect(fact('inForceFrom')).toHaveTextContent('6 Apr 2016');
    expect(fact('inForceTo')).toHaveTextContent('2030');
    expect(fact('implementsNote')).toHaveTextContent('Article 19 of MAR');
    // The source panel names each field in words, never by its payload name.
    const sources = within(screen.getByRole('heading', { name: 'Source' }).closest('section') as HTMLElement);
    expect(sources.getAllByRole('term').map((term) => term.textContent)).toEqual(['Title (English)', 'Short name']);
    expect(screen.getByRole('button', { name: 'Approve and apply' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
    expect(document.querySelector('[data-proposal-correction]')).toBeNull();
  });

  it('shows a new obligation under its instrument\'s short name and key, with its texts, duty type and scope by label', async () => {
    renderWith(
      detail({
        kind: 'new_obligation',
        title: 'Add the duty: Hold a qualifying borrow agreement',
        targetType: '',
        targetId: null,
        instrumentShortName: 'SSR ITS 827/2012',
        payload: {
          key: 'obl-eu-ssr-its-locate-arrangements',
          instrument: 'celex-32012r0827',
          titles: { en: 'Hold a qualifying borrow agreement or locate confirmation before every short sale' },
          summaries: { en: 'Before short selling a share, a firm holds one of the listed arrangements.' },
          originalLanguage: 'en',
          refLabel: 'Art. 5-7',
          dutyType: 'reporting',
          effectiveFrom: '2012-11-01',
          terms: ['lifecycle_stage:pre_trade'],
        },
      }),
    );
    const panel = (await screen.findByRole('heading', { name: 'What it adds' })).closest('section') as HTMLElement;
    const fact = (field: string) => panel.querySelector(`[data-proposal-fact="${field}"]`);
    expect(fact('instrument')).toHaveTextContent('SSR ITS 827/2012celex-32012r0827');
    expect(fact('titles')).toHaveTextContent('English (original)Hold a qualifying borrow agreement');
    expect(fact('summaries')).toHaveTextContent('Before short selling a share');
    expect(fact('refLabel')).toHaveTextContent('Art. 5-7');
    expect(fact('effectiveFrom')).toHaveTextContent('1 Nov 2012');
    await waitFor(() => expect(fact('dutyType')).toHaveTextContent('Reporting'));
    await waitFor(() => expect(fact('terms')).toHaveTextContent('Before the trade'));
  });

  it('names an obligation\'s instrument by its key alone, and says so, when the library does not hold it', async () => {
    renderWith(
      detail({
        kind: 'new_obligation',
        targetType: '',
        targetId: null,
        payload: { key: 'obl-x', instrument: 'celex-32099r0001', titles: { en: 'A duty' }, summaries: { en: 'A summary.' }, originalLanguage: 'en', refLabel: 'Art. 1', dutyType: 'conduct' },
      }),
    );
    const panel = (await screen.findByRole('heading', { name: 'What it adds' })).closest('section') as HTMLElement;
    expect(panel.querySelector('[data-proposal-fact="instrument"]')).toHaveTextContent('celex-32099r0001The library does not hold this instrument.');
    expect(panel.querySelector('[data-proposal-fact="effectiveFrom"]')).toHaveTextContent('Since the duty began');
    expect(panel.querySelector('[data-proposal-fact="terms"]')).toHaveTextContent('No scope terms');
    // A key no read labels stays the key, rather than a guess.
    await waitFor(() => expect(panel.querySelector('[data-proposal-fact="dutyType"]')).toHaveTextContent('conduct'));
  });

  it('shows no warning for a proposal the screen found nothing in', async () => {
    renderWith(detail({ riskFlags: [] }));
    await screen.findByText('Add version 2 of the research payment obligation');
    expect(screen.queryByText(/reads like an instruction to an AI/)).toBeNull();
  });
});
