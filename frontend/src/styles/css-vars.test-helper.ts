import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// Test helper: reads the stylesheets as text and resolves custom properties
// per theme, so brand.test.ts and contrast.test.ts assert against the values
// the browser would compute. No CSS engine involved: the files are flat
// declaration blocks.

export type Theme = 'light' | 'dark';
export type VarMap = Map<string, string>;

const stylesDir = join(process.cwd(), 'src', 'styles');

export function readStyle(name: string): string {
  return readFileSync(join(stylesDir, name), 'utf8');
}

interface Block {
  selectors: string[];
  declarations: [string, string][];
}

export function parseBlocks(css: string): Block[] {
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const blocks: Block[] = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(withoutComments)) !== null) {
    const selectors = (m[1] ?? '').split(',').map((s) => s.trim()).filter(Boolean);
    const declarations: [string, string][] = [];
    for (const line of (m[2] ?? '').split(';')) {
      const idx = line.indexOf(':');
      if (idx === -1) continue;
      const name = line.slice(0, idx).trim();
      const value = line.slice(idx + 1).trim();
      if (name.startsWith('--')) declarations.push([name, value]);
    }
    blocks.push({ selectors, declarations });
  }
  return blocks;
}

function appliesTo(block: Block, theme: Theme): boolean {
  const s = block.selectors;
  if (theme === 'light') return s.includes(':root') || s.includes('.light');
  // Dark inherits :root for the non-themed reference values, then .dark wins.
  return s.includes(':root') || s.includes('.dark');
}

/** Files apply in order; later declarations win, as in a stylesheet. */
export function computeVars(files: string[], theme: Theme): VarMap {
  const vars: VarMap = new Map();
  for (const file of files) {
    const blocks = parseBlocks(file);
    // Within one file the theme block must beat :root for dark.
    const ordered = theme === 'dark' ? [...blocks.filter((b) => !b.selectors.includes('.dark')), ...blocks.filter((b) => b.selectors.includes('.dark'))] : blocks;
    for (const block of ordered) {
      if (!appliesTo(block, theme)) continue;
      for (const [name, value] of block.declarations) vars.set(name, value);
    }
  }
  return vars;
}

export function resolveVar(vars: VarMap, value: string, depth = 0): string {
  if (depth > 20) throw new Error(`css-vars: var() chain too deep at ${value}`);
  const m = /^var\((--[A-Za-z0-9-]+)(?:\s*,\s*(.+))?\)$/.exec(value.trim());
  if (!m) return value.trim();
  const name = m[1] ?? '';
  const found = vars.get(name);
  if (found === undefined) {
    if (m[2] !== undefined) return resolveVar(vars, m[2], depth + 1);
    throw new Error(`css-vars: ${name} is not defined`);
  }
  return resolveVar(vars, found, depth + 1);
}

export function resolveName(vars: VarMap, name: string): string {
  return resolveVar(vars, `var(${name})`);
}

export function brandVariableNames(vars: VarMap): string[] {
  return [...vars.keys()].filter((k) => k.startsWith('--gds-sys-color-') && k.includes('brand'));
}

export function normaliseColour(value: string): string {
  return value.toLowerCase().replace(/\s+/g, '');
}
