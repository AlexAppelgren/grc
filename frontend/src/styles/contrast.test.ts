import { describe, expect, it } from 'vitest';

import { pillTones } from '@/components/ui/pill-tones';

import { AA_NON_TEXT, AA_NORMAL_TEXT, contrastRatio, flatten, NON_TEXT, PAIRS, type Pair } from './contrast';
import { computeVars, readStyle, resolveName, type Theme, type VarMap } from './css-vars.test-helper';

// Playbook 6.3: contrast is pinned by a unit test against WCAG AA for every
// text-on-surface pair the design uses, in both themes, including all six
// pill tones. Values are resolved from tokens.generated.css + brand.css, then
// theme.css for the rail's --sidebar-* aliases (ADR 0020 amendment 2026-09-19).
// The pairs live in contrast.ts, which the NFR-S9 journey measures in a
// browser too; the pill pairs are added here.

const tokens = readStyle('tokens.generated.css');
const brand = readStyle('brand.css');
const themeCss = readStyle('theme.css');

// Each tone on the background it takes in that theme (light-dark() in
// Pill.tsx), and the tenant tag's outlined pill on the two surfaces it sits on.
function pillPairs(theme: Theme): Pair[] {
  return [
    ...Object.entries(pillTones).map(([tone, { background, darkBackground, text }]) => ({ name: `pill ${tone}`, fg: text, bg: theme === 'dark' ? darkBackground : background })),
    { name: 'outlined information pill on surface', fg: pillTones.information.text, bg: '--gds-sys-color-l2-neutral-02' },
    { name: 'outlined information pill on sand', fg: pillTones.information.text, bg: '--gds-sys-color-l2-brand-02' },
  ];
}

function varsFor(theme: Theme): VarMap {
  return computeVars([tokens, brand, themeCss], theme);
}

describe('WCAG AA contrast for every text-on-surface pair (playbook 6.3)', () => {
  for (const theme of ['light', 'dark'] as const) {
    const vars = varsFor(theme);
    describe(theme, () => {
      it.each([...PAIRS, ...pillPairs(theme)])('$name is at least 4.5:1', ({ fg, bg }) => {
        const ratio = contrastRatio(resolveName(vars, fg), resolveName(vars, bg));
        expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });
      it.each(NON_TEXT)('$name is at least 3:1', ({ fg, bg }) => {
        const ratio = contrastRatio(resolveName(vars, fg), resolveName(vars, bg));
        expect(ratio).toBeGreaterThanOrEqual(AA_NON_TEXT);
      });
    });
  }

  it('the six pill tones and only those are checked', () => {
    expect(Object.keys(pillTones).sort()).toEqual(['brand', 'information', 'negative', 'notice', 'positive', 'warning']);
  });

  it('the ratio formula matches the WCAG reference values', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
    expect(contrastRatio('rgba(255, 255, 255, 0.5)', '#000000')).toBeGreaterThan(1);
  });

  it('reads the colours a browser computes', () => {
    expect(contrastRatio('rgb(0, 0, 0)', 'rgb(255, 255, 255)')).toBeCloseTo(21, 5);
  });

  it('flattens translucent backgrounds onto the first opaque one behind them', () => {
    // Innermost first: a clear pill, a half-white wash, then a black card.
    expect(flatten(['rgba(0, 0, 0, 0)', 'rgba(255, 255, 255, 0.5)', 'rgb(0, 0, 0)', 'rgb(255, 0, 0)'])).toBe('rgb(127.5, 127.5, 127.5)');
    expect(flatten(['#ffffff'])).toBe('rgb(255, 255, 255)');
  });

  it('refuses to measure against a background it cannot see', () => {
    expect(() => flatten(['rgba(0, 0, 0, 0)'])).toThrow('no opaque background');
    expect(() => contrastRatio('oklch(0.5 0.1 120)', '#ffffff')).toThrow('cannot parse colour');
  });
});
