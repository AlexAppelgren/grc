import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { CLAMP_CHARACTERS, CLAMP_LINES, firstText, isLong, originalOf, provisionChipLabel, provisionPlace, provisionTextLabel, summaryMachineLabel } from './rule-words-presentation';
import type { LocalizedText } from './types';

const t = createT('en');
const sv = createT('sv');

const svOriginal: LocalizedText = { text: 'Investeringsanalys får tas emot endast…', language: 'sv', isOriginal: true, isMachine: false };
const enMachine: LocalizedText = { text: 'Investment research may be received only…', language: 'en', isOriginal: false, isMachine: true };
const fiOriginal: LocalizedText = { text: 'Luottolaitoksen on…', language: 'fi', isOriginal: true, isMachine: false };
// Finland enacts in Finnish and Swedish: the Swedish is the authority's own, not a translation.
const svOfficial: LocalizedText = { text: 'Kreditinstitutet ska…', language: 'sv', isOriginal: false, isMachine: false };
const daMachine: LocalizedText = { text: 'Kreditinstituttet skal…', language: 'da', isOriginal: false, isMachine: true };

describe('firstText', () => {
  it('opens in the reader\'s own language when the provision holds it', () => {
    expect(firstText([svOriginal, enMachine], 'sv')).toBe(svOriginal);
    expect(firstText([fiOriginal, svOfficial, enMachine], 'sv')).toBe(svOfficial);
  });

  it('falls back to English, then to the original', () => {
    expect(firstText([svOriginal, enMachine], 'en')).toBe(enMachine);
    expect(firstText([fiOriginal, svOfficial, enMachine], 'en')).toBe(enMachine);
    expect(firstText([fiOriginal, daMachine], 'en')).toBe(fiOriginal);
    expect(firstText([fiOriginal, daMachine], 'sv')).toBe(fiOriginal);
  });

  it('has nothing to open when the library holds no wording', () => {
    expect(firstText([], 'en')).toBeNull();
  });
});

describe('originalOf', () => {
  it('is the text flagged original, else the first one the read gave', () => {
    expect(originalOf([enMachine, svOriginal])).toBe(svOriginal);
    expect(originalOf([daMachine])).toBe(daMachine);
    expect(originalOf([])).toBeNull();
  });
});

describe('the labels of the rule\'s own words', () => {
  it('marks the original\'s chip and names the others by language only, in the reader\'s language', () => {
    expect(provisionChipLabel(svOriginal, 'en', t)).toBe('Swedish, original');
    expect(provisionChipLabel(enMachine, 'en', t)).toBe('English');
    expect(provisionChipLabel(svOriginal, 'sv', sv)).toBe('svenska, original');
    expect(provisionChipLabel(enMachine, 'sv', sv)).toBe('engelska');
  });

  it('says above each text what it is: the original, a machine translation of it, or an official text', () => {
    const swedishLaw = [svOriginal, enMachine];
    expect(provisionTextLabel(svOriginal, swedishLaw, 'en', t)).toBe('Swedish, original');
    expect(provisionTextLabel(enMachine, swedishLaw, 'en', t)).toBe('Machine translation from Swedish. The original is authoritative.');
    expect(provisionTextLabel(enMachine, swedishLaw, 'sv', sv)).toBe('Maskinöversättning från svenska. Originalet gäller.');
    const finnishLaw = [fiOriginal, svOfficial, enMachine];
    expect(provisionTextLabel(svOfficial, finnishLaw, 'en', t)).toBe('Swedish, official text');
    expect(provisionTextLabel(svOfficial, finnishLaw, 'sv', sv)).toBe('svenska, officiell språkversion');
    expect(provisionTextLabel(enMachine, finnishLaw, 'en', t)).toBe('Machine translation from Finnish. The original is authoritative.');
    // A machine text with nothing beside it names its own language rather than guess another.
    expect(provisionTextLabel(daMachine, [daMachine], 'en', t)).toBe('Machine translation from Danish. The original is authoritative.');
  });

  it('never calls the summary\'s language the original', () => {
    expect(summaryMachineLabel('sv', 'en', t)).toBe('Machine-translated from Swedish');
    expect(summaryMachineLabel('en', 'sv', sv)).toBe('Maskinöversatt från engelska');
    expect(summaryMachineLabel('sv', 'en', t)).not.toMatch(/original/i);
  });
});

describe('isLong', () => {
  it('clamps a text longer than about a screen, by its characters or its lines', () => {
    expect(isLong('a'.repeat(CLAMP_CHARACTERS))).toBe(false);
    expect(isLong('a'.repeat(CLAMP_CHARACTERS + 1))).toBe(true);
    expect(isLong(Array.from({ length: CLAMP_LINES }, () => 'line').join('\n'))).toBe(false);
    expect(isLong(Array.from({ length: CLAMP_LINES + 1 }, () => 'line').join('\n'))).toBe(true);
  });
});

describe('provisionPlace', () => {
  it('cites the provision by its place in the regulation, after the short name', () => {
    expect(provisionPlace({ refLabel: '6 §', path: 'FFFS 2017:2 > 9 kap. > 6 §' }, 'FFFS 2017:2')).toBe('9 kap. 6 §');
    expect(provisionPlace({ refLabel: 'Article 22', path: 'GDPR > Article 22' }, 'GDPR')).toBe('Article 22');
  });

  it('keeps the refLabel when the path does not start at the regulation', () => {
    expect(provisionPlace({ refLabel: '9 kap. 6 §', path: '9 kap. > 6 §' }, 'FFFS 2017:2')).toBe('9 kap. 6 §');
    expect(provisionPlace({ refLabel: '6 §', path: 'FFFS 2017:2' }, 'FFFS 2017:2')).toBe('6 §');
  });
});
