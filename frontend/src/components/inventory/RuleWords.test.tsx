import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CLAMP_CHARACTERS } from '@/features/library/rule-words-presentation';
import type { LocalizedText, ObligationDetail } from '@/features/library/types';
import { renderWith } from '@/shared/testing/render';

import { RuleWords } from './RuleWords';

// "The rule's own words" (design/screens/tenant-obligation.html; INV-02, INV-05):
// each cited provision's verbatim text, opened in the reader's language, else
// English, else the original, with a line above it that is always true of it.

type Provision = ObligationDetail['provisions'][number];

const svOriginal: LocalizedText = {
  text: 'Investeringsanalys från tredje part får tas emot endast om den betalas\n  1. med institutets egna medel, eller\n  2. från ett analyskonto.',
  language: 'sv',
  isOriginal: true,
  isMachine: false,
};
const enMachine: LocalizedText = { text: 'Investment research from a third party may be received only if it is paid for by the institution.', language: 'en', isOriginal: false, isMachine: true };
const fiOriginal: LocalizedText = { text: 'Luottolaitoksen on arvioitava…', language: 'fi', isOriginal: true, isMachine: false };
const svOfficial: LocalizedText = { text: 'Kreditinstitutet ska bedöma…', language: 'sv', isOriginal: false, isMachine: false };
const daMachine: LocalizedText = { text: 'Kreditinstituttet skal vurdere…', language: 'da', isOriginal: false, isMachine: true };

function provision(id: string, texts: LocalizedText[], patch: Partial<Provision> = {}): Provision {
  // The shape the library returns: the refLabel is the section's own number, and the chapter is in the path.
  return { id, refLabel: `${id} §`, path: `FFFS 2017:2 > 9 kap. > ${id} §`, heading: 'Betalning för analys', texts, ...patch };
}

function obligation(provisions: Provision[]): ObligationDetail {
  return {
    instrument: { id: 'in-1', key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
    provenance: { sourceUrl: 'https://www.fi.se/', sourceLabel: 'fi.se, consolidated text' },
    provisions,
  } as unknown as ObligationDetail;
}

function show(provisions: Provision[], locale: 'en' | 'sv' = 'en') {
  return renderWith(<RuleWords obligation={obligation(provisions)} />, { locale });
}

const block = (id: string) => document.querySelector(`[data-provision-words="${id}"]`) as HTMLElement;
const label = (id: string) => block(id).querySelector('[data-provision-label]')?.textContent;
const text = (id: string) => block(id).querySelector('[data-provision-text]') as HTMLElement;

describe('RuleWords', () => {
  it('draws nothing for an obligation that cites no provision', () => {
    const { container } = show([]);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows an original alone with its label, its reference back to the regulation and its heading, kept exactly as stored', () => {
    show([provision('6', [svOriginal])]);
    expect(screen.getByRole('heading', { level: 2, name: "The rule's own words" })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'FFFS 2017:2' })).toHaveAttribute('href', '/inventory/instruments/in-1');
    // The full citation: the chapter from the path, not the bare "6 §" of the refLabel.
    expect(block('6').querySelector('[data-provision-ref]')).toHaveTextContent('FFFS 2017:2 9 kap. 6 §');
    // The heading is the source's words, read in the source's language.
    expect(screen.getByRole('heading', { level: 3, name: 'Betalning för analys' })).toHaveAttribute('lang', 'sv');
    expect(label('6')).toBe('Swedish, original');
    // Verbatim: the line breaks and indents of the list survive, and nothing is trimmed.
    expect(text('6').textContent).toBe(svOriginal.text);
    expect(text('6')).toHaveAttribute('lang', 'sv');
    expect(text('6').className).toContain('whitespace-pre-wrap');
    // One text needs no chips.
    expect(block('6').querySelector('[data-provision-languages]')).toBeNull();
  });

  it('opens the English machine translation first for an English reader, labelled, and switches to the original', () => {
    show([provision('6', [svOriginal, enMachine], { heading: null })]);
    expect(screen.queryByRole('heading', { level: 3 })).toBeNull();
    expect(label('6')).toBe('Machine translation from Swedish. The original is authoritative.');
    expect(text('6')).toHaveAttribute('lang', 'en');
    const chips = within(block('6').querySelector('[data-provision-languages]') as HTMLElement);
    expect(chips.getAllByRole('button').map((chip) => chip.textContent)).toEqual(['Swedish, original', 'English']);
    expect(chips.getByRole('button', { name: 'English' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(chips.getByRole('button', { name: 'Swedish, original' }));
    expect(label('6')).toBe('Swedish, original');
    expect(text('6')).toHaveAttribute('lang', 'sv');
    expect(chips.getByRole('button', { name: 'Swedish, original' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('opens the original first for a Swedish reader of a Swedish rule, in Swedish words', () => {
    show([provision('6', [svOriginal, enMachine])], 'sv');
    expect(label('6')).toBe('svenska, original');
    expect(text('6')).toHaveAttribute('lang', 'sv');
  });

  it('labels the authority\'s own second-language text as official, never as a translation', () => {
    show([provision('6', [fiOriginal, svOfficial, enMachine])], 'sv');
    expect(label('6')).toBe('svenska, officiell språkversion');
    fireEvent.click(screen.getByRole('button', { name: 'engelska' }));
    expect(label('6')).toBe('Maskinöversättning från finska. Originalet gäller.');
  });

  it('opens the original when the provision holds neither the reader\'s language nor English', () => {
    show([provision('6', [fiOriginal, daMachine])]);
    expect(label('6')).toBe('Finnish, original');
    expect(text('6')).toHaveAttribute('lang', 'fi');
  });

  it('says in one line when the library does not hold the wording yet, and links the source', () => {
    show([provision('6', [])]);
    const line = block('6').querySelector('[data-provision-not-held]') as HTMLElement;
    expect(line).toHaveTextContent("The library does not hold this rule's wording yet.");
    expect(within(line).getByRole('link', { name: 'fi.se, consolidated text' })).toHaveAttribute('href', 'https://www.fi.se/');
    expect(within(block('6')).getByRole('link', { name: 'FFFS 2017:2' })).toBeInTheDocument();
    expect(block('6').querySelector('[data-provision-label]')).toBeNull();
    // With no text held the heading's language is not known, so it claims none.
    expect(screen.getByRole('heading', { level: 3, name: 'Betalning för analys' })).not.toHaveAttribute('lang');
  });

  it('opens two provisions and folds the rest behind "Show <n> more"', () => {
    show([provision('6', [svOriginal]), provision('7', []), provision('8', [enMachine]), provision('9', [])]);
    expect([...document.querySelectorAll('[data-provision-words]')].map((row) => row.getAttribute('data-provision-words'))).toEqual(['6', '7']);
    fireEvent.click(screen.getByRole('button', { name: 'Show 2 more' }));
    expect([...document.querySelectorAll('[data-provision-words]')].map((row) => row.getAttribute('data-provision-words'))).toEqual(['6', '7', '8', '9']);
  });

  // jsdom lays nothing out: the clamped box's heights are set by hand, as a browser would measure them.
  function measured(scrollHeight: number, clientHeight: number) {
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(scrollHeight);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(clientHeight);
  }
  afterEach(() => vi.restoreAllMocks());
  const long: LocalizedText = { ...svOriginal, text: 'Lång paragraf. '.repeat(Math.ceil(CLAMP_CHARACTERS / 10)) };

  it('clamps a text longer than about a screen, with "Show all" and a fade at the cut', () => {
    measured(900, 540);
    show([provision('6', [long])]);
    expect(text('6').className).toContain('overflow-hidden');
    expect(text('6').className).toContain('mask-image');
    const more = screen.getByRole('button', { name: 'Show all' });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(more);
    expect(text('6').className).not.toContain('overflow-hidden');
    expect(screen.getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true');
    // The full text is in the page either way: clamping hides, it never cuts.
    expect(text('6').textContent).toBe(long.text);
  });

  it('offers no "Show all" when the long text fits under the clamp, since it would change nothing', () => {
    measured(420, 420);
    show([provision('6', [long])]);
    expect(screen.queryByRole('button', { name: 'Show all' })).toBeNull();
    expect(text('6').className).not.toContain('mask-image');
  });
});
