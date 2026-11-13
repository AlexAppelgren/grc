import type { PresentedPill, VocabularyRef } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { MessageKey, Translate } from '@/shared/i18n';

import type { components } from '@/types/api.generated';

import { presentBindingLevel } from './obligation-presentation';
import type { InstrumentLinkRef, Obligation } from './types';

// Instrument header and row (design/screens/tenant-instrument.html,
// tenant-inventory.html): the short name as brand, the level as information,
// "Binding" as information or "Guidance, comply or explain" as warning
// ("Standard" as information when the level's kind is standard, D-37), the
// jurisdiction as a brand facet, the regime as information. The API sends the
// binding fact, never a phrase.

export interface InstrumentFacts {
  /** The instrument's stable key and short name, e.g. "FFFS 2017:2". */
  instrument: VocabularyRef;
  level: VocabularyRef;
  /** The level's kind: `standard` or null (D-37). */
  levelKind?: string | null;
  binding: boolean;
  jurisdiction?: VocabularyRef;
  regime?: VocabularyRef;
}

export const INSTRUMENT_SLOT_ORDER = {
  instrument: 10,
  level: 20,
  binding: 30,
  jurisdiction: 40,
  regime: 50,
} as const;

export function presentInstrument(instrument: InstrumentFacts, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: `instrument:${instrument.instrument.key}`, label: instrument.instrument.label, tone: slotTone.instrument, order: INSTRUMENT_SLOT_ORDER.instrument },
    { key: `level:${instrument.level.key}`, label: instrument.level.label, tone: slotTone.instrumentLevel, order: INSTRUMENT_SLOT_ORDER.level },
    presentBindingLevel(instrument.binding, instrument.levelKind ?? null, INSTRUMENT_SLOT_ORDER.binding, t),
  ];
  if (instrument.jurisdiction !== undefined) {
    pills.push({
      key: `jurisdiction:${instrument.jurisdiction.key}`,
      label: instrument.jurisdiction.label,
      tone: slotTone.jurisdiction,
      order: INSTRUMENT_SLOT_ORDER.jurisdiction,
    });
  }
  if (instrument.regime !== undefined) {
    pills.push({ key: `regime:${instrument.regime.key}`, label: instrument.regime.label, tone: slotTone.regime, order: INSTRUMENT_SLOT_ORDER.regime });
  }
  return pills;
}

// The words the instrument card uses for the record, by its level (INV-09): a directive
// is "this directive", an act "this act". Levels are rows an admin may add to, so a level
// this map does not know reads as the general term. Keys are compared, never labels.
const OBLIGATIONS_TITLE: Record<string, MessageKey> = {
  eu_regulation: 'inventory.instrument.obligationsTitle.euRegulation',
  eu_directive: 'inventory.instrument.obligationsTitle.euDirective',
  eu_guidance: 'inventory.instrument.obligationsTitle.euGuidance',
  act: 'inventory.instrument.obligationsTitle.act',
  government_regulation: 'inventory.instrument.obligationsTitle.governmentRegulation',
  authority_regulation: 'inventory.instrument.obligationsTitle.authorityRegulation',
  standard: 'inventory.instrument.obligationsTitle.standard',
};

/** "Obligations from this directive", "from this act": the obligations panel's title for the level. */
export function obligationsTitleOf(levelKey: string, t: Translate): string {
  return t(OBLIGATIONS_TITLE[levelKey] ?? 'inventory.instrument.obligationsTitle.other');
}

/** The level whose duties sit in each country's implementing law, not under the record itself (ADR 0065). */
export const DIRECTIVE_LEVEL = 'eu_directive';

/**
 * A directive's national laws as its page opens them: the laws with duties in the bank's scope
 * first, and the totals over every law listed. An act of the directive's own jurisdiction that
 * names it (a delegated regulation supplementing it) is not a national law and is left out.
 */
export function nationalLawsOf(implementedBy: readonly InstrumentLinkRef[], jurisdiction: string): { laws: InstrumentLinkRef[]; obligations: number; inScope: number } {
  const national = implementedBy.filter((law) => law.jurisdiction.key !== jurisdiction);
  return {
    // A stable sort: within each half the laws keep the order the read answers them in.
    laws: [...national].sort((a, b) => Number(b.obligationCounts.inScope > 0) - Number(a.obligationCounts.inScope > 0)),
    obligations: national.reduce((sum, law) => sum + law.obligationCounts.inLibrary, 0),
    inScope: national.reduce((sum, law) => sum + law.obligationCounts.inScope, 0),
  };
}

/** One chip of a regulation's answer filter: the list's `applicability` value (none for every obligation in scope) and its label with its count. */
export interface AnswerFilter {
  value: Obligation['applicability'] | null;
  label: string;
}

/** The answer filter over a regulation's obligations in scope, from its roll-up: all, still to decide, applies, does not apply. */
export function answerFiltersOf(rollup: Pick<components['schemas']['RegisterInstrumentApplicability'], 'inScope' | 'underAssessment' | 'applies' | 'notApplicable'>, t: Translate): AnswerFilter[] {
  return [
    { value: null, label: t('inventory.instrument.answer.all', { count: rollup.inScope }) },
    { value: 'under_assessment', label: t('inventory.instrument.answer.underAssessment', { count: rollup.underAssessment }) },
    { value: 'applies', label: t('inventory.instrument.answer.applies', { count: rollup.applies }) },
    { value: 'not_applicable', label: t('inventory.instrument.answer.notApplicable', { count: rollup.notApplicable }) },
  ];
}
