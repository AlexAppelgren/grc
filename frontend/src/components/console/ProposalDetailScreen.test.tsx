import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import type { ProposalDetail } from '@/features/proposals/types';
import { renderWith } from '@/shared/testing/render';
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
  '/api/v1/vocab/provision_kind': { items: [{ key: 'section', kind: 'unit', label: 'Section', labels: {}, usageNote: '', sortOrder: 0, active: true, isSystem: true, isDefault: false, usageCount: 0, extra: {} }], total: 1 },
  '/api/v1/reference/jurisdictions': [{ key: 'eu', kind: 'supranational', label: 'European Union', parentKey: null }],
};

function showProposal(row: ProposalDetail): void {
  installAdapter((sent) => {
    if (sent.path === `/api/v1/proposals/${row.id}`) return { status: 200, data: row };
    if (sent.path in READS) return { status: 200, data: READS[sent.path] };
    if (sent.path === '/api/v1/taxonomy/terms') {
      const dimension = (sent.params as { dimension?: string }).dimension;
      const items = dimension === 'regime' ? [{ id: 't1', key: 'securities', label: 'Securities', dimension: 'regime' }] : [{ id: 't2', key: 'pre_trade', label: 'Before the trade', dimension: 'lifecycle_stage' }];
      return { status: 200, data: { items, total: items.length } };
    }
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  }, { me: editor });
  renderWith(<ProposalDetailScreen proposalId={row.id} />);
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
    showProposal(detail({ status: 'approved', appliedAt: DECIDED_AT, reviewedAt: DECIDED_AT, reviewedByAgent: AGENT, reviewNote: 'Matches the adopted text.' }));
    const panel = await decision('applied');
    expect(panel).toHaveTextContent(/^Applied .+ by the agent library-confirmer, machine-confirmed\./);
    expect(panel).toHaveTextContent("The agent's note: Matches the adopted text.");
    expect(panel).not.toHaveTextContent('Note to the proposer');
  });

  it('names the agent that corrected the payload as an agent, on a line of its own', async () => {
    showProposal(detail({ status: 'approved', appliedAt: DECIDED_AT, reviewedAt: DECIDED_AT, reviewedByAgent: AGENT, correctedByAgent: AGENT }));
    const panel = await decision('applied');
    expect(panel.querySelector('[data-proposal-corrected-by-agent]')).toHaveTextContent('The agent library-confirmer corrected the proposal before applying it.');
  });

  it('names the agent that rejected it, and labels its note as the agent\'s', async () => {
    showProposal(detail({ status: 'rejected', reviewedAt: DECIDED_AT, reviewedByAgent: AGENT, rejectionCode: 'bad_source', reviewNote: 'The source is the consultation draft.' }));
    const panel = await decision('rejected');
    expect(panel).toHaveTextContent(/^Rejected .+ by the agent library-confirmer\./);
    expect(panel).toHaveTextContent("The agent's note: The source is the consultation draft.");
  });

  it('names a person who decided it, with their note to the proposer, and no agent line', async () => {
    showProposal(detail({ status: 'approved', appliedAt: DECIDED_AT, reviewedAt: DECIDED_AT, reviewedBy: PERSON, correctedBy: PERSON, reviewNote: 'Checked against the board decision.' }));
    const panel = await decision('applied');
    expect(panel).toHaveTextContent(/^Applied .+ by Kari Nygaard\./);
    expect(panel).toHaveTextContent('Note to the proposer: Checked against the board decision.');
    expect(panel).not.toHaveTextContent('agent');
    expect(panel.querySelector('[data-proposal-corrected-by-agent]')).toBeNull();
  });

  it('never shows an empty name when a decided proposal names nobody', async () => {
    showProposal(detail({ status: 'approved', appliedAt: DECIDED_AT, reviewedAt: DECIDED_AT }));
    const panel = await decision('applied');
    expect(panel).toHaveTextContent(/^Applied [^.]+\.$/);
    expect(panel).not.toHaveTextContent(/ by \./);
    expect(panel).not.toHaveTextContent(/ by $/);
  });

  it('shows the four-eyes notice, and no Approve, when the server says the reader filed it', async () => {
    showProposal(detail({ isMine: true }));
    expect(await screen.findByText('Someone else has to approve it.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve and apply' })).toBeNull();
  });

  it('warns a person when the screen flagged a text, and still lets them decide', async () => {
    showProposal(detail({ riskFlags: ['embedded_instructions'] }));
    expect(await screen.findByText(/reads like an instruction to an AI/)).toBeInTheDocument();
    expect(screen.getByText('Flagged')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve and apply' })).toBeInTheDocument();
  });

  it('shows a new instrument\'s facts by their labels, the original title first, and plain Approve and Reject', async () => {
    showProposal(
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
    // Fields that share a page are listed under it once, with that page linked once.
    expect([...document.querySelectorAll('[data-source-group] p')].map((fields) => fields.textContent)).toEqual(['Title (English), Short name']);
    expect(sources.getAllByRole('link', { name: 'https://eur-lex.europa.eu/eli/reg_impl/2016/523/oj' })).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Approve and apply' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
    expect(document.querySelector('[data-proposal-correction]')).toBeNull();
  });

  it('shows a new obligation under its instrument\'s short name and key, with its texts, duty type and scope by label', async () => {
    showProposal(
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
    // A duty's title and summary are bleqq's wording: their language is named, never called the original.
    expect(fact('titles')).toHaveTextContent('EnglishHold a qualifying borrow agreement');
    expect(fact('titles')).not.toHaveTextContent('original');
    expect(fact('summaries')).toHaveTextContent('Before short selling a share');
    expect(fact('refLabel')).toHaveTextContent('Art. 5-7');
    expect(fact('effectiveFrom')).toHaveTextContent('1 Nov 2012');
    await waitFor(() => expect(fact('dutyType')).toHaveTextContent('Reporting'));
    await waitFor(() => expect(fact('terms')).toHaveTextContent('Before the trade'));
  });

  it('names an obligation\'s instrument by its key alone, and says so, when the library does not hold it', async () => {
    showProposal(
      detail({
        kind: 'new_obligation',
        targetType: '',
        targetId: null,
        payload: { key: 'obl-x', instrument: 'celex-32099r0001', titles: { en: 'A duty' }, summaries: { en: 'A summary.' }, originalLanguage: 'en', refLabel: 'Art. 1', dutyType: 'conduct' },
      }),
    );
    const panel = (await screen.findByRole('heading', { name: 'What it adds' })).closest('section') as HTMLElement;
    expect(panel.querySelector('[data-proposal-fact="instrument"]')).toHaveTextContent('celex-32099r0001The library does not hold this regulation.');
    expect(panel.querySelector('[data-proposal-fact="effectiveFrom"]')).toHaveTextContent('Since the duty began');
    expect(panel.querySelector('[data-proposal-fact="terms"]')).toHaveTextContent('No scope terms');
    // A key no read labels stays the key, rather than a guess.
    await waitFor(() => expect(panel.querySelector('[data-proposal-fact="dutyType"]')).toHaveTextContent('conduct'));
  });

  it("shows a record's machine translations beside the original each was made from", async () => {
    showProposal(
      detail({
        kind: 'new_translations',
        targetType: '',
        targetId: null,
        payload: { target: 'instrument', key: 'fffs-2017-2', titles: { da: 'FFFS 2017:2 om værdipapirhandel' }, titlesFrom: 'sv', summaries: {} },
        instrumentShortName: 'FFFS 2017:2',
        originalTitle: { text: 'FFFS 2017:2 om värdepappersrörelse', language: 'sv', isOriginal: true, isMachine: false },
        originalSummary: null,
      }),
    );
    const panel = (await screen.findByRole('heading', { name: 'What it adds' })).closest('section') as HTMLElement;
    expect(panel.querySelector('[data-proposal-fact="key"]')).toHaveTextContent('FFFS 2017:2fffs-2017-2');
    const titles = panel.querySelector('[data-proposal-fact="titles"]') as HTMLElement;
    expect([...titles.querySelectorAll('[data-language]')].map((block) => block.textContent)).toEqual([
      'Swedish (original)FFFS 2017:2 om värdepappersrörelse',
      'Danish (machine translation)FFFS 2017:2 om værdipapirhandel',
    ]);
    expect(panel.querySelector('[data-proposal-fact="summaries"]')).toBeNull();
    expect(screen.getByText('New translations')).toBeInTheDocument();
  });

  it("labels a duty's summary translations as machine-made, and its own language by name only", async () => {
    showProposal(
      detail({
        kind: 'new_translations',
        targetType: '',
        targetId: null,
        payload: { target: 'obligation', key: 'obl-research-payments', titles: { sv: 'Betala för analys' }, titlesFrom: 'en', summaries: {} },
        instrumentShortName: 'FFFS 2017:2',
        originalTitle: { text: 'Pay for research', language: 'en', isOriginal: true, isMachine: false },
        originalSummary: null,
      }),
    );
    const panel = (await screen.findByRole('heading', { name: 'What it adds' })).closest('section') as HTMLElement;
    const titles = panel.querySelector('[data-proposal-fact="titles"]') as HTMLElement;
    expect([...titles.querySelectorAll('[data-language]')].map((block) => block.textContent)).toEqual(['EnglishPay for research', 'Swedish (machine translation)Betala för analys']);
  });

  it('names the language of a new summary version without calling it the original', async () => {
    showProposal(detail({ payload: { summaries: { sv: 'Investeringsanalys.', en: 'Research.' }, originalLanguage: 'sv', isMachine: true } }));
    const changes = (await screen.findByRole('heading', { name: 'What changes' })).closest('section') as HTMLElement;
    const blocks = [...changes.querySelectorAll('[data-language]')];
    expect(blocks.map((block) => block.querySelector('p')?.textContent)).toEqual(['Swedish', 'English (machine translation)']);
    expect(blocks[0]?.querySelector('[lang]')).toHaveAttribute('lang', 'sv');
  });

  describe('a proposed provision', () => {
    const svText = 'Investeringsanalys från tredje part får tas emot endast om den betalas\n  1. med institutets egna medel, eller\n  2. från ett analyskonto.';
    const provision = (overrides: Partial<ProposalDetail>) =>
      detail({
        kind: 'new_provision',
        title: 'Add the text of 6 §, FFFS 2017:2, as read on 1 Nov 2026',
        targetType: '',
        targetId: null,
        payload: {
          key: 'fffs-2017-2/9-6',
          instrument: 'fffs-2017-2',
          parent: 'fffs-2017-2/9',
          provisionKind: 'section',
          refLabel: '6 §',
          heading: 'Betalning för analys',
          texts: { en: 'Investment research from a third party may be received only if it is paid for.', sv: svText },
          originalLanguage: 'sv',
          isMachine: true,
          obligations: ['obl-research-payments', 'obl-research-budget'],
        },
        ...overrides,
      });
    const panelOf = async () => (await screen.findByRole('heading', { name: 'What it adds' })).closest('section') as HTMLElement;
    const blocksOf = (panel: HTMLElement) => [...panel.querySelectorAll('[data-proposal-fact="texts"] [data-language]')] as HTMLElement[];

    it('shows where it sits, how it is cited, its kind and heading, each text labelled with the original first, and the obligations it ties to', async () => {
      showProposal(provision({}));
      const panel = await panelOf();
      expect(panel).toHaveAttribute('data-proposal-record', 'new_provision');
      const fact = (field: string) => panel.querySelector(`[data-proposal-fact="${field}"]`);
      expect(fact('instrument')).toHaveTextContent('fffs-2017-2');
      expect(fact('parent')).toHaveTextContent('fffs-2017-2/9');
      expect(fact('refLabel')).toHaveTextContent('6 §');
      await waitFor(() => expect(fact('provisionKind')).toHaveTextContent('Section'));
      expect(within(fact('heading') as HTMLElement).getByText('Betalning för analys')).toHaveAttribute('lang', 'sv');
      expect(within(fact('texts') as HTMLElement).getByText("The rule's own words")).toBeInTheDocument();
      const blocks = blocksOf(panel);
      expect(blocks.map((block) => block.querySelector('p')?.textContent)).toEqual(['Swedish (original)', 'English (machine translation)']);
      // The law's own words keep their line breaks, in their own language.
      const original = blocks[0]?.querySelector('[lang]') as HTMLElement;
      expect(original).toHaveAttribute('lang', 'sv');
      expect(original.textContent).toBe(svText);
      expect(original.className).toContain('whitespace-pre-wrap');
      expect([...(fact('obligations') as HTMLElement).querySelectorAll('li')].map((item) => item.textContent)).toEqual(['obl-research-payments', 'obl-research-budget']);
      expect(screen.getByRole('button', { name: 'Approve and apply' })).toBeInTheDocument();
    });

    it("labels a Finnish act's Swedish text as the authority's own", async () => {
      showProposal(
        provision({
          payload: {
            key: 'fi-laki-2014-610/1',
            instrument: 'fi-laki-2014-610',
            provisionKind: 'section',
            refLabel: '1 §',
            texts: { fi: 'Luottolaitoksen on…', sv: 'Kreditinstitutet ska…', en: 'The credit institution must…' },
            originalLanguage: 'fi',
            officialLanguages: ['sv'],
            isMachine: true,
          },
        }),
      );
      const panel = await panelOf();
      expect(blocksOf(panel).map((block) => block.querySelector('p')?.textContent)).toEqual(['Finnish (original)', 'Swedish (official text)', 'English (machine translation)']);
      expect(panel.querySelector('[data-proposal-fact="heading"]')).toBeNull();
      expect(panel.querySelector('[data-proposal-fact="parent"]')).toBeNull();
      expect(panel.querySelector('[data-proposal-fact="obligations"]')).toHaveTextContent('None yet');
    });

    it('labels every text that is neither the original nor official a machine translation, whatever the payload says', async () => {
      showProposal(
        provision({
          payload: {
            key: 'fffs-2017-2/9-6',
            instrument: 'fffs-2017-2',
            provisionKind: 'section',
            refLabel: '6 §',
            texts: { sv: 'Betalning…', en: 'Payment…' },
            originalLanguage: 'sv',
            isMachine: false,
          },
        }),
      );
      const panel = await panelOf();
      expect(blocksOf(panel).map((block) => block.querySelector('p')?.textContent)).toEqual(['Swedish (original)', 'English (machine translation)']);
    });

    it('shows a new version of a provision by its texts, its date and its obligations, without the structure it already has', async () => {
      showProposal(
        provision({
          kind: 'new_provision_version',
          targetType: 'provision',
          targetId: 'pr-6',
          payload: { texts: { sv: 'Ny lydelse.' }, originalLanguage: 'sv', effectiveFrom: '2026-10-01', obligations: ['obl-research-payments'] },
        }),
      );
      const panel = await panelOf();
      expect(panel).toHaveAttribute('data-proposal-record', 'new_provision_version');
      expect(panel.querySelector('[data-proposal-fact="instrument"]')).toBeNull();
      expect(panel.querySelector('[data-proposal-fact="refLabel"]')).toBeNull();
      expect(panel.querySelector('[data-proposal-fact="effectiveFrom"]')).toHaveTextContent('1 Oct 2026');
      expect(blocksOf(panel).map((block) => block.querySelector('p')?.textContent)).toEqual(['Swedish (original)']);
      expect(panel.querySelector('[data-proposal-fact="obligations"]')).toHaveTextContent('obl-research-payments');
    });

    it('clamps a long text, with "Show all"', async () => {
      const long = Array.from({ length: 40 }, (_, i) => `${i + 1} §. Stycke.`).join('\n');
      showProposal(provision({ payload: { texts: { sv: long }, originalLanguage: 'sv', refLabel: '6 §', instrument: 'fffs-2017-2', provisionKind: 'section' } }));
      const panel = await panelOf();
      const text = blocksOf(panel)[0]?.querySelector('[lang]') as HTMLElement;
      expect(text.className).toContain('overflow-hidden');
      fireEvent.click(within(panel).getByRole('button', { name: 'Show all' }));
      expect(text.className).not.toContain('overflow-hidden');
      expect(within(panel).getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true');
    });
  });

  it('shows no warning for a proposal the screen found nothing in', async () => {
    showProposal(detail({ riskFlags: [] }));
    await screen.findByText('Add version 2 of the research payment obligation');
    expect(screen.queryByText(/reads like an instruction to an AI/)).toBeNull();
  });
});
