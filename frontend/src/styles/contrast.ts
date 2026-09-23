// WCAG AA contrast (playbook 6.3, NFR-03): the ratio formula and the named
// pairs the design uses, shared by the unit test (contrast.test.ts, which
// resolves the pairs from the stylesheets) and the NFR-S9 journey
// (tests/e2e/shared.journey.spec.ts, which resolves them from the colours
// the browser computes). The pairs are the table in
// design/system/foundations.md "Contrast". The pill tones are not listed
// here: ESLint keeps pill-tones out of src/ outside the places that map
// tones, so the unit test adds them and the journey measures every rendered
// pill instead.

export const AA_NORMAL_TEXT = 4.5;
// WCAG 1.4.11: a field boundary and the focus ring against their surface.
export const AA_NON_TEXT = 3;

interface Rgba {
  r: number;
  g: number;
  b: number;
  a: number;
}

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

/**
 * The colour behind an element as the eye sees it: `layers` are the
 * background colours of the element and its ancestors, innermost first. The
 * first opaque one is the base, and every translucent layer inside it is
 * painted over it in turn.
 */
export function flatten(layers: readonly string[]): string {
  const parsed = layers.map(parseColour);
  const base = parsed.findIndex((c) => c.a === 1);
  if (base === -1) throw new Error('contrast: no opaque background behind the element');
  const colour = parsed.slice(0, base).reduceRight((under, over) => composite(over, under), parsed[base] as Rgba);
  return `rgb(${colour.r}, ${colour.g}, ${colour.b})`;
}

/** A foreground and a background, each a custom property name. */
export interface Pair {
  name: string;
  fg: string;
  bg: string;
}

// Every text-on-surface pair the shell and the primitives use. Names are
// theme.css semantic names; values are the token variables behind them.
export const PAIRS: readonly Pair[] = [
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

export const NON_TEXT: readonly Pair[] = [
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
