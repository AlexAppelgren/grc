import type { Locale, Translate } from '@/shared/i18n';

import type { LocalizedText } from './types';
import { languageName } from './version-presentation';

// The language labels of the obligation page (design/screens/tenant-obligation.html;
// INV-02, INV-05). Two kinds of text sit on it and their flags mean different
// things. A cited provision's text is the law's own words: its original is the
// language the authority published the rule in and governs; a text that is
// neither original nor machine made is the authority's own version in a second
// official language (Finland enacts in Finnish and Swedish). The summary is
// bleqq's plain words about the rule: its "original" is only the language bleqq
// wrote it in, so nothing on the summary is ever called the original.

/**
 * Where a cited provision sits in its regulation, after the regulation's short
 * name: `9 kap. 6 §` from the path `FFFS 2017:2 > 9 kap. > 6 §`. The refLabel
 * alone can be only the provision's own number (`6 §`), which leaves out the
 * chapter a Swedish citation needs. A path that does not start at the
 * regulation falls back to the refLabel.
 */
export function provisionPlace(provision: { path: string; refLabel: string }, shortName: string): string {
  const [top, ...rest] = provision.path.split(' > ');
  return top === shortName && rest.length > 0 ? rest.join(' ') : provision.refLabel;
}

/** The language a reader opens a provision in: their own when it is held, else English, else the original. */
export function firstText(texts: readonly LocalizedText[], reader: Locale): LocalizedText | null {
  return texts.find((text) => text.language === reader) ?? texts.find((text) => text.language === 'en') ?? originalOf(texts);
}

/** The text that governs: the one flagged original, else the first, which the read puts first. */
export function originalOf(texts: readonly LocalizedText[]): LocalizedText | null {
  return texts.find((text) => text.isOriginal) ?? texts[0] ?? null;
}

/** A provision's language chip: the language's name, and the original's says so. */
export function provisionChipLabel(text: LocalizedText, reader: Locale, t: Translate): string {
  const name = languageName(text.language, reader);
  return text.isOriginal ? t('library.languageOriginal', { language: name }) : name;
}

/** The line above a provision's text, always true of it: the original, a machine translation of it, or an official text. */
export function provisionTextLabel(text: LocalizedText, texts: readonly LocalizedText[], reader: Locale, t: Translate): string {
  if (text.isOriginal) return t('library.languageOriginal', { language: languageName(text.language, reader) });
  if (text.isMachine) return t('legal.machineTranslation', { language: languageName(originalOf(texts)?.language ?? text.language, reader) });
  return t('inventory.obligation.officialText', { language: languageName(text.language, reader) });
}

/** The line above the summary when a machine translated it: it names the language bleqq wrote in, never "the original". */
export function summaryMachineLabel(writtenIn: string, reader: Locale, t: Translate): string {
  return t('inventory.obligation.summaryMachine', { language: languageName(writtenIn, reader) });
}

/** About a screen of law: a text longer than this opens clamped, with "Show all". */
export const CLAMP_CHARACTERS = 1200;
export const CLAMP_LINES = 16;

export function isLong(text: string): boolean {
  return text.length > CLAMP_CHARACTERS || text.split('\n').length > CLAMP_LINES;
}
