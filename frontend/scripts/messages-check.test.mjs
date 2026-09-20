import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { checkMessages } from './messages-check.mjs';

// Writes { namespace: { language: catalog } } as the real layout on disk:
// src/messages/<namespace>/<language>.json.
function messagesDir(namespaces) {
  const dir = mkdtempSync(join(tmpdir(), 'messages-check-'));
  for (const [namespace, languages] of Object.entries(namespaces)) {
    mkdirSync(join(dir, namespace));
    for (const [language, catalog] of Object.entries(languages)) {
      writeFileSync(join(dir, namespace, `${language}.json`), JSON.stringify(catalog, null, 2));
    }
  }
  return dir;
}

describe('checkMessages', () => {
  it('reads every namespace directory and counts the keys of all of them', () => {
    const dir = messagesDir({
      nav: { en: { 'nav.today': 'Today' }, sv: { 'nav.today': 'Idag' } },
      watch: { en: { 'watch.title': 'Watch' }, sv: { 'watch.title': 'Bevakning' } },
    });
    const result = checkMessages(dir);
    expect(result.problems).toEqual([]);
    expect(result.keyCount).toBe(2);
    expect(result.languages).toEqual(['en', 'sv']);
  });

  it('fails on a key missing from one language of one namespace', () => {
    const dir = messagesDir({
      nav: { en: { 'nav.today': 'Today' }, sv: { 'nav.today': 'Idag' } },
      watch: { en: { 'watch.title': 'Watch', 'watch.empty': 'Nothing yet' }, sv: { 'watch.title': 'Bevakning' } },
    });
    expect(checkMessages(dir).problems).toEqual(['sv: missing key "watch.empty"']);
  });

  it('fails on an empty string and on a value that is not a string', () => {
    const dir = messagesDir({
      nav: { en: { 'nav.today': '  ', 'nav.watch': 'Watch' }, sv: { 'nav.today': 'Idag', 'nav.watch': 2 } },
    });
    expect(checkMessages(dir).problems).toEqual(['en: "nav.today" is empty', 'sv: "nav.watch" is not a string']);
  });

  it('fails on a plural without an other branch', () => {
    const dir = messagesDir({
      pill: {
        en: { 'pill.openChanges': '{count, plural, one {# open change} other {# open changes}}' },
        sv: { 'pill.openChanges': '{count, plural, one {# öppen ändring}}' },
      },
    });
    expect(checkMessages(dir).problems).toEqual(['sv: "pill.openChanges" plural has no "other" branch']);
  });

  it('fails when a translation drops or renames a placeholder', () => {
    const dir = messagesDir({
      shell: { en: { 'shell.signedInAs': 'Signed in as {name}' }, sv: { 'shell.signedInAs': 'Inloggad som {namn}' } },
    });
    expect(checkMessages(dir).problems).toEqual(['sv: "shell.signedInAs" placeholders {namn} differ from en {name}']);
  });

  it('fails when two namespaces claim the same key, because the merged catalog would drop one', () => {
    const dir = messagesDir({
      nav: { en: { 'nav.today': 'Today' }, sv: { 'nav.today': 'Idag' } },
      today: { en: { 'nav.today': 'Today' }, sv: { 'nav.today': 'Idag' } },
    });
    expect(checkMessages(dir).problems).toEqual([
      'today/en.json: "nav.today" is already in nav',
      'today/sv.json: "nav.today" is already in nav',
    ]);
  });

  it('fails when en is missing altogether', () => {
    const dir = messagesDir({ nav: { sv: { 'nav.today': 'Idag' } } });
    expect(checkMessages(dir).problems).toContain('no namespace has an en.json');
  });

  // A catalog left directly under src/messages is in no namespace, so
  // messages.ts never imports it and every string in it is missing from the
  // running app. The check used to read directories only and pass in silence.
  it('fails on a catalog left outside a namespace directory', () => {
    const dir = messagesDir({
      nav: { en: { 'nav.today': 'Today' }, sv: { 'nav.today': 'Idag' } },
    });
    writeFileSync(join(dir, 'en.json'), JSON.stringify({ 'stray.key': 'Stray' }, null, 2));
    const { problems, keyCount } = checkMessages(dir);
    expect(problems).toEqual([
      'en.json: a catalog outside a namespace directory is never loaded; move it into src/messages/<namespace>/',
    ]);
    expect(keyCount).toBe(1);
  });
});
