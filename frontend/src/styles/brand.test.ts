import { describe, expect, it } from 'vitest';

import { brandVariableNames, computeVars, normaliseColour, readStyle, resolveName, type Theme } from './css-vars.test-helper';

// D-05: no SEB brand value survives in the computed brand set once brand.css
// is applied. The SEB set is the prototype's three known values plus every
// value the generated file assigns to a brand variable, in either theme.

const tokens = readStyle('tokens.generated.css');
const brand = readStyle('brand.css');

const KNOWN_SEB_VALUES = ['#003824', '#efe9dc', '#685631'].map(normaliseColour);

function generatedBrandValues(): Set<string> {
  const values = new Set<string>(KNOWN_SEB_VALUES);
  for (const theme of ['light', 'dark'] as const) {
    const vars = computeVars([tokens], theme);
    for (const name of brandVariableNames(vars)) values.add(normaliseColour(resolveName(vars, name)));
  }
  return values;
}

describe('brand.css overrides every Green brand variable (D-05)', () => {
  const sebValues = generatedBrandValues();

  it.each<Theme>(['light', 'dark'])('%s: every brand variable is overridden and carries none of the SEB values', (theme) => {
    const generated = computeVars([tokens], theme);
    const applied = computeVars([tokens, brand], theme);
    const names = brandVariableNames(generated);
    expect(names.length).toBeGreaterThanOrEqual(16);

    const surviving: string[] = [];
    for (const name of names) {
      const before = normaliseColour(resolveName(generated, name));
      const after = normaliseColour(resolveName(applied, name));
      if (after === before || sebValues.has(after)) surviving.push(`${name}: ${after}`);
    }
    expect(surviving).toEqual([]);
  });

  it('the prototype’s SEB values are in the forbidden set', () => {
    for (const v of KNOWN_SEB_VALUES) expect(sebValues.has(v)).toBe(true);
  });

  it('the generated file is marked generated and never edited', () => {
    expect(tokens.startsWith('/* generated, never edit. */')).toBe(true);
  });

  it('light tokens sit under :root and .light, dark under .dark', () => {
    expect(tokens).toContain(':root, .light {');
    expect(tokens).toContain('.dark {');
  });
});
