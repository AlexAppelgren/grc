import { describe, expect, it } from 'vitest';

import { formatMessage } from './format-message';
import { createT, isLocale, locales, t } from './index';

describe('formatMessage (ICU-lite)', () => {
  it('substitutes simple placeholders', () => {
    expect(formatMessage('Needs {permission}', { permission: 'cases signoff' }, 'en-GB')).toBe('Needs cases signoff');
  });

  it('leaves an unknown placeholder visible rather than blank', () => {
    expect(formatMessage('Needs {permission}', {}, 'en-GB')).toBe('Needs {permission}');
  });

  it('selects plural branches with # as the number', () => {
    const msg = '{count, plural, one {# open change} other {# open changes}}';
    expect(formatMessage(msg, { count: 1 }, 'en-GB')).toBe('1 open change');
    expect(formatMessage(msg, { count: 2 }, 'en-GB')).toBe('2 open changes');
    expect(formatMessage(msg, { count: 0 }, 'en-GB')).toBe('0 open changes');
  });

  it('prefers an exact =n branch', () => {
    const msg = '{count, plural, =0 {Not clicked yet} one {Clicked # time} other {Clicked # times}}';
    expect(formatMessage(msg, { count: 0 }, 'en-GB')).toBe('Not clicked yet');
    expect(formatMessage(msg, { count: 1 }, 'en-GB')).toBe('Clicked 1 time');
    expect(formatMessage(msg, { count: 5 }, 'en-GB')).toBe('Clicked 5 times');
  });

  it('formats the number per locale and nests placeholders inside branches', () => {
    const msg = '{count, plural, one {# item for {who}} other {# items for {who}}}';
    expect(formatMessage(msg, { count: 1234, who: 'Sara' }, 'sv-SE')).toBe('1 234 items for Sara');
  });

  it('falls back to other when a category is missing', () => {
    expect(formatMessage('{n, plural, other {# things}}', { n: 1 }, 'en-GB')).toBe('1 things');
  });

  it('treats a non-number plural argument as a plain substitution', () => {
    expect(formatMessage('{n, plural, one {x} other {y}}', { n: 'text' }, 'en-GB')).toBe('text');
    expect(formatMessage('{n, plural, one {x} other {y}}', {}, 'en-GB')).toBe('{n}');
  });

  it('tolerates an unbalanced brace', () => {
    expect(formatMessage('open {brace', {}, 'en-GB')).toBe('open {brace');
  });
});

describe('t', () => {
  it('reads the catalog for the default and a named locale', () => {
    expect(t('nav.today')).toBe('Today');
    expect(t('nav.today', {}, 'sv')).toBe('Idag');
    expect(createT('sv')('pill.openChanges', { count: 2 })).toBe('2 öppna ändringar');
  });

  it('lists the shipped locales and validates a tag', () => {
    expect([...locales]).toEqual(['en', 'sv']);
    expect(isLocale('sv')).toBe(true);
    expect(isLocale('de')).toBe(false);
    expect(isLocale(undefined)).toBe(false);
  });
});
