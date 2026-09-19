// Writes src/styles/tokens.generated.css from @sebgroup/green-tokens (2023
// theme). Playbook 6.3: the palette is imported, never copied. The package
// ships light and dark both scoped to `:root` (Verification_Log 2026-09-19);
// this script rescopes them so next-themes' class attribute can switch:
//   light -> `:root, .light`   dark -> `.dark`
// The `.light` alias exists so a light block can sit inside a dark page (the
// /dev/pills gallery renders both themes side by side).
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const tokensDir = dirname(require.resolve('@sebgroup/green-tokens/package.json'));
const version = require('@sebgroup/green-tokens/package.json').version;
const cssDir = join(tokensDir, '2023', 'css');

function block(file, selector) {
  const css = readFileSync(join(cssDir, file), 'utf8');
  const match = css.match(/:root\s*\{([\s\S]*?)\}/);
  if (!match) throw new Error(`build-tokens: no :root block in ${file}`);
  const body = match[1].trim().split('\n').map((l) => `  ${l.trim()}`).join('\n');
  return `/* ${file} */\n${selector} {\n${body}\n}\n`;
}

const out = [
  '/* generated, never edit. */',
  `/* Source: @sebgroup/green-tokens ${version}, 2023 theme (Apache-2.0). */`,
  '/* Regenerate with: npm run build:tokens (scripts/build-tokens.mjs). */',
  '/* Brand values are overridden in brand.css (DECISIONS D-05). */',
  '',
  block('colors.ref.css', ':root'),
  block('variables.base.css', ':root'),
  block('variables.shadows.css', ':root'),
  block('variables.light.css', ':root, .light'),
  block('variables.dark.css', '.dark'),
].join('\n');

const target = join(here, '..', 'src', 'styles', 'tokens.generated.css');
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, out);
process.stdout.write(`build-tokens: wrote ${target} from green-tokens ${version}\n`);
