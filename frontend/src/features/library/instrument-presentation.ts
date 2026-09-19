import type { PresentedPill, VocabularyRef } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import type { Translate } from '@/shared/i18n';

import { presentBindingLevel } from './obligation-presentation';

// Instrument header and row (design/screens/tenant-instrument.html,
// tenant-inventory.html): the short name as brand, the level as information,
// "Binding" as information or "Guidance, comply or explain" as warning, the
// jurisdiction as a brand facet, the regime as information. The API sends the
// binding fact, never a phrase.

export interface InstrumentFacts {
  /** The instrument's stable key and short name, e.g. "FFFS 2017:2". */
  instrument: VocabularyRef;
  level: VocabularyRef;
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
    presentBindingLevel(instrument.binding, INSTRUMENT_SLOT_ORDER.binding, t),
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
