import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import type { EvalQuestion } from './api';
import { gateKind, languageLabel, presentQuestion, presentRun } from './evaluation-presentation';

const t = createT('en');

const question = (extra: Partial<EvalQuestion> = {}): EvalQuestion => ({
  id: 'q1',
  key: 'r-sv-01',
  lang: 'sv',
  question: 'kostnader och avgifter',
  expected: ['obl-costs-charges'],
  matchKind: 'concept',
  asOf: null,
  via: 'search',
  notes: '',
  active: true,
  inGate: true,
  ...extra,
});

describe('evaluation presentation', () => {
  it('reads a question as in the gate, not yet in it, or retired, retired first', () => {
    expect(gateKind(question())).toBe('in_gate');
    expect(gateKind(question({ inGate: false }))).toBe('not_in_gate');
    expect(gateKind(question({ active: false, inGate: true }))).toBe('retired');
  });

  it('names a language by its row, and by its key while the rows have not answered or lack it', () => {
    expect(languageLabel('sv', [{ key: 'sv', label: 'Swedish' }])).toBe('Swedish');
    expect(languageLabel('sv', undefined)).toBe('sv');
    expect(languageLabel('fi', [{ key: 'sv', label: 'Swedish' }])).toBe('fi');
  });

  it('gives a question its gate, language and match pills in slot order, the gate first', () => {
    const pills = presentQuestion(question({ inGate: false }), t, undefined);
    expect(pills.map((pill) => pill.key)).toEqual(['gate:not_in_gate', 'lang:sv', 'match:concept']);
    expect(pills[0]?.tone).toBe('warning');
  });

  it('marks a run scored with a stand-in, and nothing else', () => {
    expect(presentRun(true, t).map((pill) => pill.tone)).toEqual(['warning']);
    expect(presentRun(false, t)).toEqual([]);
  });
});
