import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

// T-AGT-07-3 (playbook 11.2): fetched content is untrusted and is never rendered as HTML.
// ESLint's react/no-danger refuses the JSX prop; nothing in ESLint sees `innerHTML` on a
// DOM node, so the source tree is read here instead. A screen shows fetched text as text.
// Proven to fail 2026-09-19 by assigning `node.innerHTML` in src/shared/utils/cn.ts (the
// scan named the file), and react/no-danger by a probe component using the JSX prop on a
// div and on a component of ours (two errors); both restored.
// Vitest runs from the frontend package root (vitest.config.ts).
const FRONTEND = process.cwd();
const SOURCE = join(FRONTEND, 'src');
const SOURCE_SUFFIXES = ['.ts', '.tsx', '.js', '.mjs'];
const GUARD = join(SOURCE, 'shared', 'no-dangerous-html.test.ts');

const DANGEROUS = [
  { name: 'dangerouslySetInnerHTML', pattern: /dangerouslySetInnerHTML/ },
  { name: 'innerHTML', pattern: /\.innerHTML\b/ },
  { name: 'outerHTML', pattern: /\.outerHTML\b/ },
  { name: 'insertAdjacentHTML', pattern: /insertAdjacentHTML/ },
  { name: 'document.write', pattern: /document\s*\.\s*write\b/ },
];

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    if (!SOURCE_SUFFIXES.some((suffix) => entry.name.endsWith(suffix))) return [];
    // This guard names the patterns it forbids, and the generated client is not ours.
    if (entry.name === 'api.generated.ts' || path === GUARD) return [];
    return [path];
  });
}

describe('no component renders fetched text as HTML (AGT-07, playbook 11.2)', () => {
  const files = sourceFiles(SOURCE);

  it('reads the whole source tree, so an empty scan cannot pass', () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it.each(DANGEROUS)('never writes $name', ({ pattern }) => {
    const offenders = files.filter((path) => pattern.test(readFileSync(path, 'utf8'))).map((path) => path.slice(FRONTEND.length));
    expect(offenders).toEqual([]);
  });

  it('keeps react/no-danger switched on for our own components as well', () => {
    const config = readFileSync(join(FRONTEND, 'eslint.config.js'), 'utf8');
    expect(config).toContain("'react/no-danger': ['error', { customComponentNames: ['*'] }]");
  });
});
