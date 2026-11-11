// Message catalogs: every key in en exists in sv and vice versa, no empty
// strings, every plural message has an `other` branch (playbook 9, "a UI
// string missing in a shipped language"). Exits 1 on any finding.
//
// The catalogs are one directory per feature namespace, each holding one file
// per language: src/messages/<namespace>/<language>.json. The app merges them
// into one flat catalog, so a key belongs to exactly one namespace and a key
// claimed twice is a finding too.
//
// Given the source directory as well, a key that no production file names is a
// finding: a literal 'ns.key', or a template such as `workflow.weekday.${day}`
// or 'ns.prefix.' + part that can build it. Dead copy otherwise piles up
// unseen (129 keys by the review of 2026-11-11).
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

const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Every non-test .ts/.tsx/.mjs file under dir, the catalogs excluded.
function sourceFiles(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== 'messages' && entry.name !== 'testing') sourceFiles(path, out);
    } else if (/\.(ts|tsx|mjs)$/.test(entry.name) && !/\.test\.|\.generated\./.test(entry.name)) out.push(path);
  }
  return out;
}

// The keys of the catalog that no source file names or can build.
export function unusedKeys(keys, sourceDir) {
  const literals = new Set();
  const patterns = [];
  for (const file of sourceFiles(sourceDir)) {
    const text = readFileSync(file, 'utf8');
    for (const m of text.matchAll(/(['"`])([A-Za-z][\w-]*(?:\.[\w:-]+)+)\1/g)) literals.add(m[2]);
    for (const m of text.matchAll(/`([^`]*\$\{[^`]*)`/g)) {
      const parts = m[1].split(/\$\{[^}]*\}/);
      if (parts[0].includes('.')) patterns.push(new RegExp(`^${parts.map(escape).join('[\\w:.-]+')}$`));
    }
    for (const m of text.matchAll(/(['"])([A-Za-z][\w.-]*\.)\1\s*\+/g)) patterns.push(new RegExp(`^${escape(m[2])}[\\w:.-]+$`));
  }
  return keys.filter((key) => !literals.has(key) && !patterns.some((re) => re.test(key)));
}

export function checkMessages(dir, sourceDir) {
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

  if (sourceDir !== undefined) {
    for (const key of unusedKeys(allKeys, sourceDir)) problems.push(`"${key}" is used by no source file; delete it from every language`);
  }

  return { problems, keyCount: allKeys.length, languages };
}

// The merged en catalog, for copy-drift-check.mjs.
export function englishCatalog(dir) {
  return readCatalogs(dir).catalogs.en ?? {};
}

export const sourceDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');
export const messagesDir = join(sourceDir, 'messages');

if (process.argv[1] !== undefined && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const { problems, keyCount, languages } = checkMessages(messagesDir, sourceDir);
  if (problems.length > 0) {
    console.error(`messages-check: ${problems.length} problem(s)\n  ${problems.join('\n  ')}`);
    process.exit(1);
  }
  console.log(`messages-check: ${keyCount} keys in ${languages.join(', ')}: ok`);
}
