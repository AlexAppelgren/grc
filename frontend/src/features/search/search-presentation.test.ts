import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

import type { SearchHit } from './types';
import {
  factsOfHit,
  highlightSnippet,
  matchKindLabel,
  presentSearchHit,
  presentSearchHitRow,
  validityMeta,
  versionMeta,
  type SearchHitFacts,
} from './search-presentation';

// Pins label, tone and order for the result row (design/system/pills-and-labels.md).

const t = createT('en');
const ctx = defaultFormatContext;

function hit(overrides: Partial<SearchHit> = {}): SearchHit {
  return {
    type: 'obligation',
    id: 'ob-1',
    title: 'Disclose all costs and charges',
    snippet: 'Institutet ska lamna information om kostnader innan tjansten utfors.',
    matchKind: 'keyword',
    score: 0.8,
    instrumentShortName: 'FFFS 2017:2',
    binding: true,
    validFrom: null,
    validTo: null,
    versionNo: null,
    urgency: null,
    ...overrides,
  };
}

describe('search-presentation', () => {
  it('labels each match kind', () => {
    expect(matchKindLabel('keyword', t)).toBe('Keyword match');
    expect(matchKindLabel('concept', t)).toBe('Concept match');
    expect(matchKindLabel('both', t)).toBe('Keyword and concept');
  });

  it('orders instrument, match kind, then guidance', () => {
    const facts: SearchHitFacts = { instrument: { key: 'FFFS 2017:2', label: 'FFFS 2017:2' }, matchKind: 'both', guidance: true };
    const pills = presentSearchHit(facts, t);
    expect(pills.map((pill) => pill.label)).toEqual(['FFFS 2017:2', 'Keyword and concept', 'Guidance']);
    expect(pills.map((pill) => pill.tone)).toEqual(['brand', 'information', 'information']);
  });

  it('carries no instrument or guidance pill when the hit has neither', () => {
    const facts: SearchHitFacts = { instrument: null, matchKind: 'keyword', guidance: false };
    expect(presentSearchHit(facts, t).map((pill) => pill.label)).toEqual(['Keyword match']);
  });

  it('adds the urgency pill last, toned by its severity kind', () => {
    const facts: SearchHitFacts = {
      instrument: null,
      matchKind: 'concept',
      guidance: false,
      urgency: { key: 'act_now', kind: 'act_now', label: 'Act now' },
    };
    const pills = presentSearchHit(facts, t);
    expect(pills.map((pill) => pill.label)).toEqual(['Concept match', 'Act now']);
    expect(pills[1]?.tone).toBe('negative');
  });

  it('reads the facts off the wire hit: brand instrument, guidance only when binding is false', () => {
    expect(factsOfHit(hit({ binding: false }))).toEqual({
      instrument: { key: 'FFFS 2017:2', label: 'FFFS 2017:2' },
      matchKind: 'keyword',
      guidance: true,
    });
    expect(factsOfHit(hit({ instrumentShortName: null, binding: true }))).toEqual({
      instrument: null,
      matchKind: 'keyword',
      guidance: false,
    });
  });

  it('drops an urgency key outside the fixed severity scale, exactly as the watch feed does', () => {
    const facts = factsOfHit(hit({ urgency: { key: 'invented', kind: null, label: 'Invented' } }));
    expect(facts.urgency).toBeUndefined();
  });

  it('carries a known urgency through to the row', () => {
    const withUrgency = hit({ urgency: { key: 'monitor', kind: null, label: 'Monitor' } });
    const pills = presentSearchHitRow(withUrgency, t);
    expect(pills.map((pill) => pill.label)).toContain('Monitor');
  });

  it('shows the version only when the hit carries one', () => {
    expect(versionMeta(hit({ versionNo: 3 }), t)).toBe('Version 3');
    expect(versionMeta(hit({ versionNo: null }), t)).toBeNull();
  });

  it('describes validity every way a chunk can carry it', () => {
    expect(validityMeta(hit(), t, ctx)).toBeNull();
    expect(validityMeta(hit({ validFrom: '2026-01-01', validTo: '2026-08-31' }), t, ctx)).toBe('1 Jan 2026 to 31 Aug 2026');
    expect(validityMeta(hit({ validFrom: '2026-01-01', validTo: null }), t, ctx)).toBe('From 1 Jan 2026');
    expect(validityMeta(hit({ validFrom: null, validTo: '2026-08-31' }), t, ctx)).toBe('Until 31 Aug 2026');
  });

  it('marks the query terms in the snippet, case-insensitively, ignoring short fragments', () => {
    const segments = highlightSnippet('The firm does not downplay a warning about costs.', 'Warning Costs a');
    expect(segments.filter((segment) => segment.matched).map((segment) => segment.text)).toEqual(['warning', 'costs']);
    expect(segments.map((segment) => segment.text).join('')).toBe('The firm does not downplay a warning about costs.');
  });

  it('marks nothing when the query has no word of at least two characters', () => {
    expect(highlightSnippet('Some text', 'a')).toEqual([{ text: 'Some text', matched: false }]);
  });

  it('extracts a query term from punctuation before matching it in the snippet', () => {
    expect(highlightSnippet('Cost (and charges)', '(and')).toEqual([
      { text: 'Cost (', matched: false },
      { text: 'and', matched: true },
      { text: ' charges)', matched: false },
    ]);
  });
});
