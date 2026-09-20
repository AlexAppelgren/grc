// Message catalogs: every key in en exists in sv and vice versa, no empty
// strings, every plural message has an `other` branch (playbook 9, "a UI
// string missing in a shipped language"). Exits 1 on any finding.
//
// The catalogs are one directory per feature namespace, each holding one file
// per language: src/messages/<namespace>/<language>.json. The app merges them
// into one flat catalog, so a key belongs to exactly one namespace and a key
// claimed twice is a finding too.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// { languages, catalogs: { <language>: { <key>: value } }, problems }
function readCatalogs(dir) {
  const problems = [];
  const catalogs = {};
  const owners = {};
  const names = readdirSync(dir).sort();
  const namespaces = names.filter((name) => statSync(join(dir, name)).isDirectory());
  // Only a namespace directory is read. A catalog left directly under
  // src/messages belongs to no namespace, so the app never imports it and its
  // copy would go missing without a word: say so instead of skipping it.
  for (const name of names.filter((name) => name.endsWith('.json') && !namespaces.includes(name))) {
    problems.push(`${name}: a catalog outside a namespace directory is never loaded; move it into src/messages/<namespace>/`);
  }
  for (const namespace of namespaces) {
    const files = readdirSync(join(dir, namespace))
      .filter((file) => file.endsWith('.json'))
      .sort();
    for (const file of files) {
      const language = file.replace(/\.json$/, '');
      catalogs[language] ??= {};
      owners[language] ??= {};
      const entries = JSON.parse(readFileSync(join(dir, namespace, file), 'utf8'));
      for (const [key, value] of Object.entries(entries)) {
        const owner = owners[language][key];
        if (owner !== undefined) problems.push(`${namespace}/${file}: "${key}" is already in ${owner}`);
        else owners[language][key] = namespace;
        catalogs[language][key] = value;
      }
    }
  }
  return { languages: Object.keys(catalogs).sort(), catalogs, problems };
}

const placeholders = (v) =>
  [...String(v).matchAll(/\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,}]/g)].map((m) => m[1]).sort().join(',');

export function checkMessages(dir) {
  const { languages, catalogs, problems } = readCatalogs(dir);
  if (!languages.includes('en')) problems.push('no namespace has an en.json');

  const allKeys = [...new Set(languages.flatMap((l) => Object.keys(catalogs[l])))];
  for (const key of allKeys) {
    for (const lang of languages) {
      const value = catalogs[lang][key];
      if (value === undefined) problems.push(`${lang}: missing key "${key}"`);
      else if (typeof value !== 'string') problems.push(`${lang}: "${key}" is not a string`);
      else if (value.trim() === '') problems.push(`${lang}: "${key}" is empty`);
      else if (value.includes(', plural,') && !/\bother\s*\{/.test(value)) problems.push(`${lang}: "${key}" plural has no "other" branch`);
    }
  }

  // Placeholders must agree across languages.
  for (const key of allKeys) {
    const en = catalogs.en?.[key];
    if (typeof en !== 'string') continue;
    for (const lang of languages) {
      const v = catalogs[lang][key];
      if (typeof v === 'string' && placeholders(v) !== placeholders(en)) {
        problems.push(`${lang}: "${key}" placeholders {${placeholders(v)}} differ from en {${placeholders(en)}}`);
      }
    }
  }

  return { problems, keyCount: allKeys.length, languages };
}

// The merged en catalog, for copy-drift-check.mjs.
export function englishCatalog(dir) {
  return readCatalogs(dir).catalogs.en ?? {};
}

export const messagesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'messages');

if (process.argv[1] !== undefined && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const { problems, keyCount, languages } = checkMessages(messagesDir);
  if (problems.length > 0) {
    console.error(`messages-check: ${problems.length} problem(s)\n  ${problems.join('\n  ')}`);
    process.exit(1);
  }
  console.log(`messages-check: ${keyCount} keys in ${languages.join(', ')}: ok`);
}
