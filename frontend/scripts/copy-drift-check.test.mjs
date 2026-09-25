import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { checkCopyDrift } from './copy-drift-check.mjs';

function fixture(namespaces, specs) {
  const root = mkdtempSync(join(tmpdir(), 'copy-drift-'));
  const messages = join(root, 'messages');
  mkdirSync(messages);
  for (const [namespace, catalog] of Object.entries(namespaces)) {
    mkdirSync(join(messages, namespace));
    writeFileSync(join(messages, namespace, 'en.json'), JSON.stringify(catalog, null, 2));
  }
  const e2e = join(root, 'e2e');
  mkdirSync(e2e);
  for (const [name, source] of Object.entries(specs)) writeFileSync(join(e2e, name), source);
  return { messages, e2e };
}

describe('checkCopyDrift', () => {
  it('accepts a literal that lives in any namespace, not just the first one', () => {
    const { messages, e2e } = fixture(
      { nav: { 'nav.today': 'Today' }, watch: { 'watch.title': 'What changed' } },
      { 'watch.journey.spec.ts': "await page.getByText('What changed').click();\nawait page.getByRole('link', { name: 'Today' }).click();\n" },
    );
    const result = checkCopyDrift(messages, e2e);
    expect(result.findings).toEqual([]);
    expect(result.checked).toBe(2);
    expect(result.specCount).toBe(1);
  });

  it('still catches a literal that drifted away from the catalogs', () => {
    const { messages, e2e } = fixture(
      { watch: { 'watch.title': 'What changed' } },
      { 'watch.journey.spec.ts': "await page.getByText('What has changed').click();\n" },
    );
    expect(checkCopyDrift(messages, e2e).findings).toEqual([
      'watch.journey.spec.ts: "What has changed" is not in the message catalogs',
    ]);
  });

  it('expands plural branches and placeholders across namespaces', () => {
    const { messages, e2e } = fixture(
      {
        pill: { 'pill.openChanges': '{count, plural, one {# open change} other {# open changes}}' },
        shell: { 'shell.signedInAs': 'Signed in as {name}' },
      },
      { 'shell.journey.spec.ts': "getByText('3 open changes');\ngetByText('Signed in as Sara Lind');\n" },
    );
    expect(checkCopyDrift(messages, e2e).findings).toEqual([]);
  });

  it('skips the e2e support directory', () => {
    const { messages, e2e } = fixture({ nav: { 'nav.today': 'Today' } }, {});
    mkdirSync(join(e2e, 'support'));
    writeFileSync(join(e2e, 'support', 'helpers.spec.ts'), "getByText('Not copy at all');\n");
    expect(checkCopyDrift(messages, e2e)).toEqual({ findings: [], checked: 0, specCount: 0 });
  });
});
