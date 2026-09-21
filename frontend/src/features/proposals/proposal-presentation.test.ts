import { describe, expect, it } from 'vitest';

import { createT, type Locale } from '@/shared/i18n';

import {
  fieldSourceLabel,
  fieldSourceRows,
  isMineOf,
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
  vocabularyPayloadOf,
} from './proposal-presentation';
import type { ProposalRow } from './types';

const t = createT('en');
const langName = (code: string) => new Intl.DisplayNames(['en' satisfies Locale], { type: 'language' }).of(code) ?? code;

function row(overrides: Partial<ProposalRow> = {}): ProposalRow {
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
    effectiveFrom: '2026-10-01',
    origin: 'agent',
    agentRunId: 'run-1',
    model: 'agent pipeline 0.4',
    proposedBy: null,
    reviewedBy: null,
    reviewedAt: null,
    rejectionCode: '',
    reviewNote: '',
    appliedAt: null,
    createdAt: '2026-09-16T07:12:00Z',
    ...overrides,
  } as ProposalRow;
}

describe('kind and status', () => {
  it('reads every vocabulary and term kind as "Vocabulary", and the obligation kind as "New version"', () => {
    expect(kindLabel('new_obligation_version', t)).toBe('New version');
    for (const kind of ['vocabulary_create', 'vocabulary_relabel', 'vocabulary_retire', 'vocabulary_restore', 'vocabulary_merge', 'term_create', 'term_update']) {
      expect(kindLabel(kind, t)).toBe('Vocabulary');
    }
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
    const pills = presentProposal(row(), false, t);
    expect(pills.map((p) => p.key)).toEqual(['kind', 'status']);
    expect(pills[0]?.tone).toBe('notice');
  });

  it('adds a positive "Yours" pill last, only when the reader made the proposal', () => {
    const mine = presentProposal(row(), true, t);
    expect(mine.at(-1)).toMatchObject({ key: 'yours', label: 'Yours', tone: 'positive' });
    expect(presentProposal(row(), false, t).some((p) => p.key === 'yours')).toBe(false);
  });
});

describe('isMineOf', () => {
  it('is true only when the signed-in reader is the named proposer', () => {
    expect(isMineOf(row({ proposedBy: { id: 'u-1', name: 'Kari Nygaard' } }), 'u-1')).toBe(true);
    expect(isMineOf(row({ proposedBy: { id: 'u-1', name: 'Kari Nygaard' } }), 'u-2')).toBe(false);
    expect(isMineOf(row({ proposedBy: null }), 'u-1')).toBe(false);
    expect(isMineOf(row({ proposedBy: { id: 'u-1', name: 'Kari Nygaard' } }), null)).toBe(false);
  });
});

describe('proposerLine', () => {
  it('names the platform person when one proposed it', () => {
    expect(proposerLine(row({ proposedBy: { id: 'u-1', name: 'Kari Nygaard' } }), t)).toBe('Kari Nygaard');
  });

  it('names the agent run by its model when nobody is named but an agent run is', () => {
    expect(proposerLine(row({ proposedBy: null, agentRunId: 'run-1', model: 'agent pipeline 0.4' }), t)).toBe('agent pipeline 0.4');
  });

  it('falls back to the organisation phrase when neither a person nor an agent run is named', () => {
    expect(proposerLine(row({ proposedBy: null, agentRunId: null, model: '' }), t)).toBe('A member of an organisation');
  });

  it('names the agent run generically when it named no model', () => {
    expect(proposerLine(row({ proposedBy: null, agentRunId: 'run-1', model: '' }), t)).toBe('An agent run');
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
