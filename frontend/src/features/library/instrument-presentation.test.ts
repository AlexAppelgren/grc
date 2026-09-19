import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { presentInstrument, type InstrumentFacts } from './instrument-presentation';

const t = createT('en');
const sv = createT('sv');

const fffs: InstrumentFacts = {
  instrument: { key: 'fffs-2017-2', label: 'FFFS 2017:2' },
  level: { key: 'authority_regulation', label: 'FI regulation' },
  binding: true,
  jurisdiction: { key: 'SE', label: 'Sweden' },
  regime: { key: 'securities', label: 'Securities' },
};

const esma: InstrumentFacts = {
  instrument: { key: 'esma-gl-appropriateness', label: 'ESMA guidelines' },
  level: { key: 'eu_guidance', label: 'EU guidance, level 3' },
  binding: false,
  jurisdiction: { key: 'EU', label: 'EU' },
};

describe('presentInstrument', () => {
  it('matches the card: short name, level, binding, jurisdiction, regime', () => {
    expect(presentInstrument(fffs, t).map((p) => [p.key, p.label, p.tone])).toEqual([
      ['instrument:fffs-2017-2', 'FFFS 2017:2', 'brand'],
      ['level:authority_regulation', 'FI regulation', 'information'],
      ['binding', 'Binding', 'information'],
      ['jurisdiction:SE', 'Sweden', 'brand'],
      ['regime:securities', 'Securities', 'information'],
    ]);
  });

  it('guidance reads "Guidance, comply or explain" as a warning, and a missing regime is left out', () => {
    expect(presentInstrument(esma, t).map((p) => [p.key, p.label, p.tone])).toEqual([
      ['instrument:esma-gl-appropriateness', 'ESMA guidelines', 'brand'],
      ['level:eu_guidance', 'EU guidance, level 3', 'information'],
      ['guidance', 'Guidance, comply or explain', 'warning'],
      ['jurisdiction:EU', 'EU', 'brand'],
    ]);
  });

  it('a missing jurisdiction is left out and the order holds', () => {
    const pills = presentInstrument({ ...fffs, jurisdiction: undefined }, t);
    expect(pills.map((p) => p.key)).toEqual(['instrument:fffs-2017-2', 'level:authority_regulation', 'binding', 'regime:securities']);
    expect(pills.map((p) => p.order)).toEqual([...pills.map((p) => p.order)].sort((a, b) => a - b));
  });

  it('computed labels come from the catalog in the user language', () => {
    expect(presentInstrument(fffs, sv).find((p) => p.key === 'binding')?.label).toBe('Bindande');
    expect(presentInstrument(esma, sv).find((p) => p.key === 'guidance')?.label).toBe('Vägledning, följ eller förklara');
  });
});
