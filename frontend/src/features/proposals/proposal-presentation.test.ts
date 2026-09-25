import { describe, expect, it } from 'vitest';

import { createT, type Locale } from '@/shared/i18n';

import {
  agentCorrectionLine,
  decisionLine,
  decisionNoteLine,
  fieldSourceLabel,
  fieldSourceRows,
  isObligationVersion,
  isVocabularyKind,
  kindLabel,
  obligationPayloadOf,
  presentProposal,
  proposerLine,
  scopeTermPills,
  sourceLine,
  statusLabel,
  statusTone,
  targetLine,
  vocabularyPayloadOf,
} from './proposal-presentation';
import type { ProposalQueueRow } from './types';

const t = createT('en');
const langName = (code: string) => new Intl.DisplayNames(['en' satisfies Locale], { type: 'language' }).of(code) ?? code;

function row(overrides: Partial<ProposalQueueRow> = {}): ProposalQueueRow {
  return {
    id: 'p-1',
    kind: 'new_obligation_version',
    status: 'open',
    title: 'Add version 2',
    targetType: 'obligation',
    targetId: 'obl-1',
    changeId: null,
    payload: { summaries: { sv: 'Text' }, originalLanguage: 'sv' },
    fieldSources: { 'summaries.sv': 'https://example.test/' },
    scopeSuggestion: [],
    sourceLabel: 'Finansinspektionen, board decision',
    sourceUrl: 'https://example.test/',
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
    target: null,
    isMine: false,
    reviewedAt: null,
    rejectionCode: '',
    reviewNote: '',
    appliedAt: null,
    createdAt: '2026-09-16T07:12:00Z',
    ...overrides,
  } as ProposalQueueRow;
}

describe('kind and status', () => {
  it('reads every vocabulary and term kind as "Vocabulary", and the obligation kind as "New version"', () => {
    expect(kindLabel('new_obligation_version', t)).toBe('New version');
    for (const kind of ['vocabulary_create', 'vocabulary_relabel', 'vocabulary_retire', 'vocabulary_restore', 'vocabulary_merge', 'term_create', 'term_update']) {
      expect(kindLabel(kind, t)).toBe('Vocabulary');
    }
  });

  it('names each kind of new record by its own label', () => {
    expect(kindLabel('new_instrument', t)).toBe('New instrument');
    expect(kindLabel('new_obligation', t)).toBe('New obligation');
    expect(kindLabel('new_provision', t)).toBe('New provision');
    expect(kindLabel('new_provision_version', t)).toBe('New provision version');
  });

  it('falls back for a kind the catalog does not know, rather than throwing', () => {
    expect(kindLabel('something_new', t)).not.toBe('');
  });

  it('gives each status its own tone: open warning, approved positive, rejected and superseded information', () => {
    expect(statusTone('open')).toBe('warning');
    expect(statusTone('approved')).toBe('positive');
    expect(statusTone('rejected')).toBe('information');
    expect(statusTone('superseded')).toBe('information');
    expect(statusLabel('open', t)).toBe('Waiting');
    expect(statusLabel('approved', t)).toBe('Approved');
  });
});

describe('presentProposal', () => {
  it('always carries a kind and a status pill, in that order', () => {
    const pills = presentProposal(row(), t);
    expect(pills.map((p) => p.key)).toEqual(['kind', 'status']);
    expect(pills[0]?.tone).toBe('notice');
  });

  it('adds a warning "Flagged" pill after the status when the screen flagged a text, and none otherwise', () => {
    const flagged = presentProposal(row({ riskFlags: ['embedded_instructions'], isMine: true }), t);
    expect(flagged.map((p) => p.key)).toEqual(['kind', 'status', 'flagged', 'yours']);
    expect(flagged[2]).toMatchObject({ label: 'Flagged', tone: 'warning' });
    expect(presentProposal(row({ riskFlags: [] }), t).some((p) => p.key === 'flagged')).toBe(false);
  });

  it('adds a positive "Yours" pill last, only when the server says the reader filed it', () => {
    const mine = presentProposal(row({ isMine: true }), t);
    expect(mine.at(-1)).toMatchObject({ key: 'yours', label: 'Yours', tone: 'positive' });
    expect(presentProposal(row({ isMine: false, proposedBy: { id: 'u-1', name: 'Kari Nygaard' } }), t).some((p) => p.key === 'yours')).toBe(false);
  });
});

describe('proposerLine', () => {
  it('names the platform person when one proposed it', () => {
    expect(proposerLine(row({ proposedBy: { id: 'u-1', name: 'Kari Nygaard' } }), t)).toBe('Kari Nygaard');
  });

  it('names an agent by the model that drafted it', () => {
    expect(proposerLine(row({ model: 'agent pipeline 0.4' }), t)).toBe('agent pipeline 0.4');
  });

  it('uses the organisation phrase whenever the server says a bank made it, agent run or not', () => {
    expect(proposerLine(row({ fromOrganisation: true, agentRunId: 'run-1', model: 'agent pipeline 0.4' }), t)).toBe('A member of an organisation');
    expect(proposerLine(row({ fromOrganisation: true, agentRunId: null, model: '' }), t)).toBe('A member of an organisation');
  });

  it('names the agent run generically when it named no model', () => {
    expect(proposerLine(row({ model: '' }), t)).toBe('An agent run');
  });
});

describe('targetLine', () => {
  it('names the record by its own title and instrument, and nothing for a vocabulary change', () => {
    const target = { id: 'obl-1', title: 'Pay for research only under the permitted models', referenceLabel: 'Third-party payments', instrumentShortName: 'FFFS 2017:2' };
    expect(targetLine(row({ target }), t)).toBe('Pay for research only under the permitted models · FFFS 2017:2');
    expect(targetLine(row({ target: { ...target, title: '', instrumentShortName: '' } }), t)).toBe('Third-party payments');
    expect(targetLine(row({ target: null }), t)).toBeNull();
  });
});

describe('the decision', () => {
  const date = (iso: string) => iso.slice(0, 10);
  const agent = { key: 'library-confirmer', version: 1 };
  const person = { id: 'u-2', name: 'Kari Nygaard' };

  it('reads an agent\'s approval as machine-confirmed, naming the agent, and its note as the agent\'s', () => {
    const decided = row({ status: 'approved', appliedAt: '2026-09-17T10:14:00Z', reviewedAt: '2026-09-17T10:14:00Z', reviewedByAgent: agent, reviewNote: 'Matches the source.' });
    expect(decisionLine(decided, date, t)).toBe('Applied 2026-09-17 by the agent library-confirmer, machine-confirmed.');
    expect(decisionNoteLine(decided, t)).toBe("The agent's note: Matches the source.");
  });

  it('names the agent that corrected the payload as an agent, and nobody when none did', () => {
    expect(agentCorrectionLine(row({ status: 'approved', correctedByAgent: agent }), t)).toBe('The agent library-confirmer corrected the proposal before applying it.');
    expect(agentCorrectionLine(row({ status: 'approved', correctedBy: person }), t)).toBeNull();
  });

  it('names the agent that rejected it', () => {
    const decided = row({ status: 'rejected', reviewedAt: '2026-09-17T10:14:00Z', reviewedByAgent: agent, reviewNote: 'The source is a draft.' });
    expect(decisionLine(decided, date, t)).toBe('Rejected 2026-09-17 by the agent library-confirmer.');
    expect(decisionNoteLine(decided, t)).toBe("The agent's note: The source is a draft.");
  });

  it('names a person who decided it, and labels their note to the proposer', () => {
    const approved = row({ status: 'approved', appliedAt: '2026-09-17T10:14:00Z', reviewedBy: person, reviewNote: 'Checked.' });
    expect(decisionLine(approved, date, t)).toBe('Applied 2026-09-17 by Kari Nygaard.');
    expect(decisionNoteLine(approved, t)).toBe('Note to the proposer: Checked.');
    expect(decisionLine(row({ status: 'rejected', reviewedAt: '2026-09-17T10:14:00Z', reviewedBy: person }), date, t)).toBe('Rejected 2026-09-17 by Kari Nygaard.');
  });

  it('never interpolates an empty name when a decided row names nobody', () => {
    expect(decisionLine(row({ status: 'approved', appliedAt: '2026-09-17T10:14:00Z' }), date, t)).toBe('Applied 2026-09-17.');
    expect(decisionLine(row({ status: 'approved', appliedAt: '2026-09-17T10:14:00Z', reviewedBy: { id: 'u-2', name: '' } }), date, t)).toBe('Applied 2026-09-17.');
    expect(decisionLine(row({ status: 'rejected', reviewedAt: '2026-09-17T10:14:00Z' }), date, t)).toBe('Rejected 2026-09-17.');
  });

  it('says nothing while the proposal is open, and no note when there is none', () => {
    expect(decisionLine(row({ status: 'open' }), date, t)).toBeNull();
    expect(decisionNoteLine(row({ status: 'approved', reviewNote: '' }), t)).toBeNull();
  });
});

describe('sourceLine', () => {
  it('is null when the proposal names no source, and the sentence otherwise', () => {
    expect(sourceLine(row({ sourceLabel: '' }), t)).toBeNull();
    expect(sourceLine(row({ sourceLabel: 'FI board decision' }), t)).toBe('Source: FI board decision');
  });
});

describe('payload readers', () => {
  it('tells an obligation-version proposal from a vocabulary one by kind, not by payload shape', () => {
    expect(isObligationVersion('new_obligation_version')).toBe(true);
    expect(isObligationVersion('vocabulary_create')).toBe(false);
    expect(isVocabularyKind('vocabulary_relabel')).toBe(true);
    expect(isVocabularyKind('new_obligation_version')).toBe(false);
    expect(isVocabularyKind('new_obligation')).toBe(false);
    expect(isVocabularyKind('term_update')).toBe(true);
  });

  it('reads the obligation-version payload only when it carries summaries', () => {
    expect(obligationPayloadOf(row())?.originalLanguage).toBe('sv');
    expect(obligationPayloadOf(row({ payload: { list: 'flag', key: 'ai' } }))).toBeNull();
    expect(obligationPayloadOf(row({ payload: { summaries: null } }))).toBeNull();
    expect(obligationPayloadOf(row({ payload: undefined }))).toBeNull();
  });

  it('reads a vocabulary payload as-is, and as empty when the row names none', () => {
    expect(vocabularyPayloadOf(row({ payload: undefined }))).toEqual({});
  });

  it('reads a vocabulary payload as-is', () => {
    expect(vocabularyPayloadOf(row({ payload: { list: 'flag', key: 'ai', labels: { en: 'AI' } } })).key).toBe('ai');
  });
});

describe('field sources', () => {
  it('labels each field a reviewer can trace: text per language, the effective date, the scope', () => {
    expect(fieldSourceLabel('summaries.en', langName, t)).toBe('Text (English)');
    expect(fieldSourceLabel('effectiveFrom', langName, t)).toBe('Effective date');
    expect(fieldSourceLabel('terms', langName, t)).toBe('Scope');
  });

  it('orders rows text first, then the effective date, then scope, whatever order the API answered them in', () => {
    const rows = fieldSourceRows({ terms: 'u3', effectiveFrom: 'u2', 'summaries.sv': 'u1a', 'summaries.en': 'u1b' });
    expect(rows.map((r) => r.field)).toEqual(['summaries.en', 'summaries.sv', 'effectiveFrom', 'terms']);
  });

  it('reads a field name the three known shapes do not match as itself, rather than guessing', () => {
    expect(fieldSourceLabel('title', langName, t)).toBe('title');
  });
});

describe('scopeTermPills', () => {
  it('is one brand pill per ref, in order, labelled through the resolver given to it', () => {
    const pills = scopeTermPills(['service_type:advice', 'client_category:retail'], (ref) => ref.split(':')[1] ?? ref);
    expect(pills).toEqual([
      { key: 'term:service_type:advice', label: 'advice', tone: 'brand', order: 0 },
      { key: 'term:client_category:retail', label: 'retail', tone: 'brand', order: 1 },
    ]);
  });
});
