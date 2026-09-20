// Copy drift (playbook 8.3, failure class 3): every literal a spec asserts
// through getByText('…') or getByRole(…, { name: '…' }) must exist in the
// English message catalogs (journeys run in one pinned language). Plural
// messages are expanded per branch with `#` as a number, `{var}` placeholders
// match any text. Exits 1 on drift.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { englishCatalog, messagesDir } from './messages-check.mjs';

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

const literal = /getBy(?:Text|Role|Label|Placeholder|Title)\(\s*(?:'[^']*'|"[^"]*")?\s*,?\s*(?:\{[^}]*?name:\s*)?(?:'([^']*)'|"([^"]*)")/g;

export function checkCopyDrift(messages, specsDir) {
  const patterns = Object.values(englishCatalog(messages)).flatMap(patternsFor);
  const known = (text) => patterns.some((p) => p.test(text));
  const specs = walk(specsDir);
  const findings = [];
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
      if (!known(text)) findings.push(`${relative(specsDir, file)}: "${text}" is not in the message catalogs`);
    }
  }

  return { findings, checked, specCount: specs.length };
}

if (process.argv[1] !== undefined && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const specsDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'tests', 'e2e');
  const { findings, checked, specCount } = checkCopyDrift(messagesDir, specsDir);
  if (findings.length > 0) {
    console.error(`copy-drift-check: ${findings.length} drift(s)\n  ${findings.join('\n  ')}`);
    process.exit(1);
  }
  console.log(`copy-drift-check: ${checked} literal(s) in ${specCount} spec(s) match the catalogs: ok`);
}
