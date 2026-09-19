// Message catalogs: every key in en exists in sv and vice versa, no empty
// strings, every plural message has an `other` branch (playbook 9, "a UI
// string missing in a shipped language"). Exits 1 on any finding.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dir = join(here, '..', 'src', 'messages');
const files = readdirSync(dir).filter((f) => f.endsWith('.json'));
const catalogs = Object.fromEntries(files.map((f) => [f.replace(/\.json$/, ''), JSON.parse(readFileSync(join(dir, f), 'utf8'))]));
const languages = Object.keys(catalogs);
const problems = [];

if (!languages.includes('en')) problems.push('en.json is missing');

const allKeys = new Set(languages.flatMap((l) => Object.keys(catalogs[l])));
for (const key of allKeys) {
  for (const lang of languages) {
    const value = catalogs[lang][key];
    if (value === undefined) problems.push(`${lang}.json: missing key "${key}"`);
    else if (typeof value !== 'string') problems.push(`${lang}.json: "${key}" is not a string`);
    else if (value.trim() === '') problems.push(`${lang}.json: "${key}" is empty`);
    else if (value.includes(', plural,') && !/\bother\s*\{/.test(value)) problems.push(`${lang}.json: "${key}" plural has no "other" branch`);
  }
}

// Placeholders must agree across languages.
const names = (v) => [...String(v).matchAll(/\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,}]/g)].map((m) => m[1]).sort().join(',');
for (const key of allKeys) {
  const en = catalogs.en?.[key];
  if (typeof en !== 'string') continue;
  for (const lang of languages) {
    const v = catalogs[lang][key];
    if (typeof v === 'string' && names(v) !== names(en)) problems.push(`${lang}.json: "${key}" placeholders {${names(v)}} differ from en {${names(en)}}`);
  }
}

if (problems.length > 0) {
  console.error(`messages-check: ${problems.length} problem(s)\n  ${problems.join('\n  ')}`);
  process.exit(1);
}
console.log(`messages-check: ${allKeys.size} keys in ${languages.join(', ')}: ok`);
