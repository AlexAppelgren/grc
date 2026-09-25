import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import type { FormatContext } from '@/shared/utils/format';

import { inForceLabel, languageName, verifiedLabel, versionLabel } from './version-presentation';

const t = createT('en');
const sv = createT('sv');
const en: FormatContext = { locale: 'en', timeZone: 'Europe/Stockholm' };
const swedish: FormatContext = { locale: 'sv', timeZone: 'Europe/Stockholm' };

// Dates are pinned; nothing here reads today (CHUNK3_TASKS rule 8).
const oct1 = { date: '2026-10-01', precision: 'day' } as const;
const sep30 = { date: '2026-09-30', precision: 'day' } as const;
const jan3 = { date: '2018-01-03', precision: 'day' } as const;

describe('versionLabel', () => {
  it('names the version and, when it has one, the date it takes effect', () => {
    expect(versionLabel(1, null, t, en)).toBe('Version 1');
    expect(versionLabel(2, oct1, t, en)).toBe('Version 2, from 1 Oct 2026');
    expect(versionLabel(2, oct1, sv, swedish)).toBe('Version 2, från 1 okt. 2026');
  });

  it('renders the date with its precision', () => {
    expect(versionLabel(3, { date: '2026-10-01', precision: 'quarter' }, t, en)).toBe('Version 3, from Q4 2026');
    expect(versionLabel(3, { date: '2026-10-01', precision: 'quarter' }, sv, swedish)).toBe('Version 3, från kv. 4 2026');
    expect(versionLabel(4, { date: '2028-01-01', precision: 'month' }, t, en)).toBe('Version 4, from January 2028');
    expect(versionLabel(5, { date: '2028-01-01', precision: 'year' }, t, en)).toBe('Version 5, from 2028');
  });
});

describe('inForceLabel', () => {
  it('a closed range', () => {
    // en-GB abbreviates September as "Sept" (CLDR), as formatDate does everywhere.
    expect(inForceLabel(jan3, sep30, t, en)).toBe('In force 3 Jan 2018 to 30 Sept 2026');
    expect(inForceLabel(jan3, sep30, sv, swedish)).toBe('I kraft 3 jan. 2018 till 30 sep. 2026');
  });

  it('open at either end, or since always', () => {
    expect(inForceLabel(oct1, null, t, en)).toBe('In force from 1 Oct 2026');
    expect(inForceLabel(null, sep30, t, en)).toBe('In force until 30 Sept 2026');
    expect(inForceLabel(null, null, t, en)).toBe('In force');
    expect(inForceLabel(oct1, null, sv, swedish)).toBe('I kraft från 1 okt. 2026');
    expect(inForceLabel(null, sep30, sv, swedish)).toBe('I kraft till och med 30 sep. 2026');
    expect(inForceLabel(null, null, sv, swedish)).toBe('I kraft');
  });

  it('keeps each end at its own precision', () => {
    expect(inForceLabel({ date: '2028-10-01', precision: 'quarter' }, null, t, en)).toBe('In force from Q4 2028');
    expect(inForceLabel(jan3, { date: '2030-06-01', precision: 'year' }, t, en)).toBe('In force 3 Jan 2018 to 2030');
  });
});

describe('verifiedLabel', () => {
  it('shows the day of the last verification in the tenant timezone', () => {
    expect(verifiedLabel('2026-06-30T10:00:00Z', t, en)).toBe('Verified 30 Jun 2026');
    // 22:30 UTC on 29 June is already 30 June in Stockholm.
    expect(verifiedLabel('2026-06-29T22:30:00Z', t, en)).toBe('Verified 30 Jun 2026');
    expect(verifiedLabel('2026-06-30T10:00:00Z', sv, swedish)).toBe('Verifierad 30 juni 2026');
  });
});

describe('languageName', () => {
  it('names a content language in the user language', () => {
    expect(['sv', 'en', 'da', 'no', 'fi'].map((code) => languageName(code, 'en'))).toEqual(['Swedish', 'English', 'Danish', 'Norwegian', 'Finnish']);
    expect(languageName('sv', 'sv')).toBe('svenska');
  });

  it('shows the code of a language it has no name for', () => {
    expect(languageName('zz', 'en')).toBe('zz');
  });
});
