import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import {
  CLAMP_CHARACTERS,
  CLAMP_LINES,
  chosenText,
  diffFlags,
  firstText,
  isLong,
  originalOf,
  provisionChipLabel,
  provisionPlace,
  provisionTextLabel,
  regulationName,
  summaryMachineLabel,
} from './rule-words-presentation';
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

describe('chosenText', () => {
  it('shows the language chosen when this text holds it, else the one it opens in', () => {
    expect(chosenText([svOriginal, enMachine], 'sv', 'en')).toBe(svOriginal);
    expect(chosenText([fiOriginal, daMachine], 'sv', 'en')).toBe(fiOriginal);
    expect(chosenText([svOriginal, enMachine], null, 'en')).toBe(enMachine);
    expect(chosenText([], 'sv', 'sv')).toBeNull();
  });
});

describe('diffFlags', () => {
  it('reads a comparison as the original only when it is in the original language and no machine made either side', () => {
    expect(diffFlags({ language: 'sv', isMachine: false }, [svOriginal, enMachine])).toEqual({ language: 'sv', isMachine: false, isOriginal: true });
    expect(diffFlags({ language: 'en', isMachine: true }, [svOriginal, enMachine])).toEqual({ language: 'en', isMachine: true, isOriginal: false });
    expect(provisionTextLabel(diffFlags({ language: 'sv', isMachine: false }, [fiOriginal, svOfficial]), [fiOriginal, svOfficial], 'en', t)).toBe('Swedish, official text');
  });
});

describe('regulationName', () => {
  const swedishName: LocalizedText = { text: 'Lag om värdepappersmarknaden', language: 'sv', isOriginal: true, isMachine: false };
  const englishName: LocalizedText = { text: 'Securities Market Act', language: 'en', isOriginal: false, isMachine: true };

  it("prefers the authority's own name in the reader's language to a machine's in the summary's", () => {
    expect(regulationName([swedishName, englishName], 'en', 'sv', englishName)).toBe(swedishName);
  });

  it("follows the summary's language, and takes the machine's name only where the reader has no own name", () => {
    expect(regulationName([swedishName, englishName], 'sv', 'en', englishName)).toBe(swedishName);
    expect(regulationName([swedishName, englishName], 'en', 'en', swedishName)).toBe(englishName);
    expect(regulationName([swedishName], 'en', 'en', swedishName)).toBe(swedishName);
    expect(regulationName([], 'en', 'en', null)).toBeNull();
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
