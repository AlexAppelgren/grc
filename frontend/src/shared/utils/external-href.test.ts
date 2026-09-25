import { describe, expect, it } from 'vitest';

import { externalHref } from './external-href';

// H26: a source or bank-typed link renders as a link only for http and https;
// anything else comes back null and the caller renders it as plain text.

describe('externalHref', () => {
  it('passes an https or http address through unchanged', () => {
    expect(externalHref('https://www.fi.se/en/published/regulations/')).toBe('https://www.fi.se/en/published/regulations/');
    expect(externalHref('http://www.finanstilsynet.dk/')).toBe('http://www.finanstilsynet.dk/');
    expect(externalHref('HTTPS://EUR-LEX.EUROPA.EU/')).toBe('HTTPS://EUR-LEX.EUROPA.EU/');
  });

  it('refuses a javascript: address, however it is spelled', () => {
    expect(externalHref('javascript:alert(1)')).toBeNull();
    expect(externalHref('  JavaScript:alert(1)')).toBeNull();
    expect(externalHref('java\tscript:alert(1)')).toBeNull();
  });

  it('refuses a data: address', () => {
    expect(externalHref('data:text/html,<script>alert(1)</script>')).toBeNull();
  });

  it('refuses every other scheme, a relative path and text that is no address', () => {
    for (const url of ['vbscript:msgbox(1)', 'file:///etc/passwd', 'mailto:a@b.se', 'ftp://ftp.fi.se/', '/inventory', '//evil.example/', 'fi.se', '', 'not a url']) {
      expect(externalHref(url)).toBeNull();
    }
  });
});
