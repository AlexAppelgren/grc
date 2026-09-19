import { describe, expect, it } from 'vitest';

import { formatDate, formatDateTime, formatLongDate, formatPartialDate, type FormatContext } from './format';

const stockholm: FormatContext = { locale: 'en', timeZone: 'Europe/Stockholm' };
const swedish: FormatContext = { locale: 'sv', timeZone: 'Europe/Stockholm' };
const helsinki: FormatContext = { locale: 'en', timeZone: 'Europe/Helsinki' };

describe('formatDate', () => {
  it('formats a plain date as a calendar day in day-month order, whatever the timezone', () => {
    expect(formatDate('2026-10-01', stockholm)).toBe('1 Oct 2026');
    expect(formatDate('2026-10-01', helsinki)).toBe('1 Oct 2026');
    expect(formatDate('2026-10-01', { locale: 'en', timeZone: 'Pacific/Kiritimati' })).toBe('1 Oct 2026');
  });

  it('shows an instant in the tenant timezone', () => {
    // 23:30 UTC on 30 Sep is already 1 Oct in Stockholm.
    expect(formatDate('2026-09-30T23:30:00Z', stockholm)).toBe('1 Oct 2026');
    expect(formatDate(new Date('2026-09-30T23:30:00Z'), { locale: 'en', timeZone: 'UTC' })).toBe('30 Sept 2026');
  });

  it('uses the user language', () => {
    expect(formatDate('2026-10-01', swedish)).toBe('1 okt. 2026');
  });
});

describe('formatDateTime', () => {
  it('shows the time in the tenant timezone with a 24-hour clock', () => {
    expect(formatDateTime('2026-09-30T23:30:00Z', stockholm)).toBe('1 Oct 2026, 01:30');
    expect(formatDateTime('2026-09-30T23:30:00Z', helsinki)).toBe('1 Oct 2026, 02:30');
    expect(formatDateTime(new Date('2026-01-05T08:05:00Z'), swedish)).toBe('5 jan. 2026 09:05');
  });
});

describe('formatLongDate', () => {
  it('spells out the weekday for the Today kicker', () => {
    // ICU versions differ on the comma after the weekday in en-GB; the
    // words and their order are what the kicker promises.
    expect(formatLongDate('2026-09-19', stockholm)).toMatch(/^Saturday,? 19 September 2026$/);
    expect(formatLongDate(new Date('2026-09-18T23:30:00Z'), stockholm)).toMatch(/^Saturday,? 19 September 2026$/);
    expect(formatLongDate('2026-09-19', swedish)).toMatch(/^lördag,? 19 september 2026$/);
  });
});

describe('formatPartialDate', () => {
  it('formats by precision', () => {
    expect(formatPartialDate('2026-09-12', 'day', stockholm)).toBe('12 Sept 2026');
    expect(formatPartialDate('2026-09', 'month', stockholm)).toBe('September 2026');
    expect(formatPartialDate('2026-09-12', 'month', stockholm)).toBe('September 2026');
    expect(formatPartialDate('2026-09', 'quarter', stockholm)).toBe('Q3 2026');
    expect(formatPartialDate('2026-11', 'quarter', swedish)).toBe('Kv4 2026');
    expect(formatPartialDate('2026', 'year', stockholm)).toBe('2026');
  });

  it('never claims more precision than the value carries', () => {
    expect(formatPartialDate('2026', 'day', stockholm)).toBe('2026');
    expect(formatPartialDate('2026-09', 'day', stockholm)).toBe('September 2026');
    expect(formatPartialDate('2026', 'quarter', stockholm)).toBe('2026');
  });

  it('returns an unparseable value unchanged', () => {
    expect(formatPartialDate('soon', 'day', stockholm)).toBe('soon');
  });
});
