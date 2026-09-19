// Copy drift (playbook 8.3, failure class 3): every literal a spec asserts
// through getByText('…') or getByRole(…, { name: '…' }) must exist in
// messages/en.json (journeys run in one pinned language). Plural messages
// are expanded per branch with `#` as a number, `{var}` placeholders match
// any text. Exits 1 on drift.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const en = JSON.parse(readFileSync(join(root, 'src', 'messages', 'en.json'), 'utf8'));

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return name === 'support' ? [] : walk(full);
    return /\.spec\.ts$/.test(name) ? [full] : [];
  });
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// One regex per catalog value, expanding plural branches.
function patternsFor(value) {
  const plural = /\{\s*(\w+)\s*,\s*plural\s*,([^]*)\}\s*$/.exec(value);
  const variants = [];
  if (plural && value.trimStart().startsWith('{')) {
    const branches = [...plural[2].matchAll(/(?:=\d+|\w+)\s*\{([^{}]*)\}/g)].map((m) => m[1]);
    for (const b of branches) variants.push(b);
  } else {
    variants.push(value);
  }
  return variants.map((v) => {
    const parts = v.split(/(\{[^{}]*\}|#)/).map((p) => (p === '#' ? '\\d+' : p.startsWith('{') ? '.+' : escapeRegex(p)));
    return new RegExp(`^${parts.join('')}$`);
  });
}

const patterns = Object.values(en).flatMap(patternsFor);
const known = (text) => patterns.some((p) => p.test(text));

const specs = walk(join(root, 'tests', 'e2e'));
const findings = [];
const literal = /getBy(?:Text|Role|Label|Placeholder|Title)\(\s*(?:'[^']*'|"[^"]*")?\s*,?\s*(?:\{[^}]*?name:\s*)?(?:'([^']*)'|"([^"]*)")/g;
let checked = 0;

for (const file of specs) {
  const src = readFileSync(file, 'utf8');
  for (const m of src.matchAll(literal)) {
    const text = m[1] ?? m[2];
    if (text === undefined || text === '') continue;
    // getByRole('button') with no name: the first quoted string is the role,
    // not copy. The match stops at that string when there is no `name:`.
    if (m[0].startsWith('getByRole(') && !/name:/.test(m[0])) continue;
    checked += 1;
    if (!known(text)) findings.push(`${relative(root, file)}: "${text}" is not in messages/en.json`);
  }
}

if (findings.length > 0) {
  console.error(`copy-drift-check: ${findings.length} drift(s)\n  ${findings.join('\n  ')}`);
  process.exit(1);
}
console.log(`copy-drift-check: ${checked} literal(s) in ${specs.length} spec(s) match en.json: ok`);
