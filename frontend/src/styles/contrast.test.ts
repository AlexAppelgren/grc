import { describe, expect, it } from 'vitest';

import { pillTones } from '@/components/ui/pill-tones';

import { computeVars, readStyle, resolveName, type Theme, type VarMap } from './css-vars.test-helper';

// Playbook 6.3: contrast is pinned by a unit test against WCAG AA for every
// text-on-surface pair the design uses, in both themes, including all six
// pill tones. Values are resolved from tokens.generated.css + brand.css, then
// theme.css for the rail's --sidebar-* aliases (ADR 0020 amendment 2026-09-19).
// The pairs are the table in design/system/foundations.md "Contrast".

const AA_NORMAL_TEXT = 4.5;
// WCAG 1.4.11: a field boundary and the focus ring against their surface.
const AA_NON_TEXT = 3;

const tokens = readStyle('tokens.generated.css');
const brand = readStyle('brand.css');
const themeCss = readStyle('theme.css');

type Rgba = { r: number; g: number; b: number; a: number };

function parseColour(value: string): Rgba {
  const v = value.trim().toLowerCase();
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/.exec(v);
  if (hex) {
    let h = hex[1] ?? '';
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16), a: 1 };
  }
  const rgb = /^rgba?\(([^)]+)\)$/.exec(v);
  if (rgb) {
    const parts = (rgb[1] ?? '').split(',').map((p) => Number(p.trim()));
    return { r: parts[0] ?? 0, g: parts[1] ?? 0, b: parts[2] ?? 0, a: parts[3] ?? 1 };
  }
  throw new Error(`contrast: cannot parse colour "${value}"`);
}

function composite(fg: Rgba, bg: Rgba): Rgba {
  const a = fg.a;
  return { r: fg.r * a + bg.r * (1 - a), g: fg.g * a + bg.g * (1 - a), b: fg.b * a + bg.b * (1 - a), a: 1 };
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance(c: Rgba): number {
  return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
}

export function contrastRatio(fg: string, bg: string): number {
  const back = parseColour(bg);
  const front = composite(parseColour(fg), back);
  const l1 = luminance(front);
  const l2 = luminance(back);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

interface Pair {
  name: string;
  fg: string;
  bg: string;
}

// Every text-on-surface pair the shell and the primitives use. Names are
// theme.css semantic names; values are the token variables behind them.
const PAIRS: Pair[] = [
  { name: 'text on page', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l1-neutral-01' },
  { name: 'text on subtle (banner, code block)', fg: '--gds-sys-color-content-neutral-01', bg: '--subtle' },
  { name: 'text on a warning banner', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l3-warning-02' },
  { name: 'text on a refusal banner', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l3-negative-02' },
  { name: 'text on an added sentence (DiffText ins)', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l3-positive-02' },
  { name: 'text on a removed sentence (DiffText del)', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l3-negative-02' },
  { name: 'warning pill on a warning banner (waiting for approval)', fg: '--gds-sys-color-content-warning-01', bg: '--gds-sys-color-l3-warning-02' },
  { name: 'text on accent (current row, pressed toggle)', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l3-neutral-02' },
  { name: 'text on search highlight', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l3-brand-02-2' },
  { name: 'text on surface', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'text on surface-2', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l2-neutral-02-2' },
  { name: 'text on sand', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l2-brand-02' },
  { name: 'muted on page', fg: '--gds-sys-color-content-neutral-02', bg: '--gds-sys-color-l1-neutral-01' },
  { name: 'muted on subtle (banner)', fg: '--gds-sys-color-content-neutral-02', bg: '--subtle' },
  { name: 'muted on accent (count or role on the current row)', fg: '--gds-sys-color-content-neutral-02', bg: '--gds-sys-color-l3-neutral-02' },
  { name: 'muted on surface', fg: '--gds-sys-color-content-neutral-02', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'muted on sand', fg: '--gds-sys-color-content-neutral-02', bg: '--gds-sys-color-l2-brand-02' },
  { name: 'brass on sand (legal margin)', fg: '--gds-sys-color-content-brand-02', bg: '--gds-sys-color-l2-brand-02' },
  { name: 'brass on surface (AI note)', fg: '--gds-sys-color-content-brand-02', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'accent on surface', fg: '--bleqq-accent', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'on-brand on the brand surface', fg: '--bleqq-on-brand', bg: '--gds-sys-color-l2-brand-01' },
  { name: 'on-brand-muted on the brand surface', fg: '--bleqq-on-brand-muted', bg: '--gds-sys-color-l2-brand-01' },
  { name: 'button text on button', fg: '--gds-sys-color-content-neutral-03', bg: '--gds-sys-color-l3-neutral-03' },
  { name: 'negative on surface (danger button)', fg: '--gds-sys-color-content-negative-01', bg: '--gds-sys-color-l2-neutral-02' },
  // The danger button's hover fill, which differs by theme (theme.css
  // --negative-hover): l3-negative-02 in light, one step deeper in dark.
  { name: 'negative on danger hover', fg: '--gds-sys-color-content-negative-01', bg: '--negative-hover' },
  { name: 'warning on surface (date emphasis)', fg: '--gds-sys-color-content-warning-01', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'positive on surface (date emphasis)', fg: '--gds-sys-color-content-positive-03', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'notice on surface (date emphasis)', fg: '--gds-sys-color-content-notice-01', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'notice on sand (focus ring reference)', fg: '--gds-sys-color-content-notice-01', bg: '--gds-sys-color-l2-brand-02' },
  { name: 'outlined information pill on surface', fg: pillTones.information.text, bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'outlined information pill on sand', fg: pillTones.information.text, bg: '--gds-sys-color-l2-brand-02' },
  // The rail: a neutral surface with a hairline, shadcn's structure in
  // seb.io's restraint. Every text the rail sets, on every surface it sets it.
  { name: 'rail: destination label on the rail', fg: '--sidebar-foreground', bg: '--sidebar' },
  { name: 'rail: role line, count and minimise on the rail', fg: '--sidebar-muted-foreground', bg: '--sidebar' },
  { name: 'rail: current and hovered row', fg: '--sidebar-accent-foreground', bg: '--sidebar-accent' },
  { name: 'rail: role line and count on a current or hovered row', fg: '--sidebar-muted-foreground', bg: '--sidebar-accent' },
  // The tab bar and the More sheet below 1024 px (design/system/navigation.md
  // 16). Named for the bar or the sheet even where a generic pair covers the
  // same tokens, so a later token change fails by name.
  { name: 'tab bar: tab label on the bar', fg: '--gds-sys-color-content-neutral-02', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'tab bar: current tab label', fg: '--sidebar-accent-foreground', bg: '--sidebar-accent' },
  { name: 'more sheet: row label', fg: '--gds-sys-color-content-neutral-01', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'more sheet: organisation and role line', fg: '--gds-sys-color-content-neutral-02', bg: '--gds-sys-color-l2-neutral-02' },
];

// Each tone on the background it takes in that theme (light-dark() in Pill.tsx).
function pillPairs(theme: Theme): Pair[] {
  return Object.entries(pillTones).map(([tone, { background, darkBackground, text }]) => ({ name: `pill ${tone}`, fg: text, bg: theme === 'dark' ? darkBackground : background }));
}

const NON_TEXT: Pair[] = [
  { name: 'input boundary on surface', fg: '--gds-sys-color-border-neutral-01', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'focus ring on surface', fg: '--gds-sys-color-content-notice-01', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'focus ring on page', fg: '--gds-sys-color-content-notice-01', bg: '--gds-sys-color-l1-neutral-01' },
  { name: 'focus ring on the rail', fg: '--sidebar-ring', bg: '--sidebar' },
  { name: 'tab bar: tab icon on the bar', fg: '--gds-sys-color-content-neutral-02', bg: '--gds-sys-color-l2-neutral-02' },
  // The fill alone is 1.19:1 against the bar (WCAG 1.4.11 fails); the inset
  // line-strong outline is the current tab's 3:1 indicator, against both.
  { name: 'tab bar: current-tab outline on the bar', fg: '--gds-sys-color-border-neutral-01', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'tab bar: current-tab outline on its fill', fg: '--gds-sys-color-border-neutral-01', bg: '--gds-sys-color-l3-neutral-02' },
  { name: 'more sheet: current-row outline on the sheet', fg: '--gds-sys-color-border-neutral-01', bg: '--gds-sys-color-l2-neutral-02' },
  { name: 'tab bar: focus ring on the bar', fg: '--gds-sys-color-content-notice-01', bg: '--gds-sys-color-l2-neutral-02' },
];

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
});
