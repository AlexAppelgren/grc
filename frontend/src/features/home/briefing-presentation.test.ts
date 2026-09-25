import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

import { isoWeekNumber, weekKicker } from './briefing-presentation';

const t = createT('en');
const ctx = defaultFormatContext;

describe('isoWeekNumber', () => {
  it('the design card\'s own week: Monday 14 September 2026 is week 38', () => {
    expect(isoWeekNumber(new Date(Date.UTC(2026, 8, 14)))).toBe(38);
  });

  it('the first Monday of an ISO year is week 1', () => {
    // 2026-01-01 is a Thursday, so week 1 runs Monday 29 Dec 2025 to Sunday 4 Jan 2026.
    expect(isoWeekNumber(new Date(Date.UTC(2025, 11, 29)))).toBe(1);
  });
});

describe('weekKicker', () => {
  it('names the ISO week and both bounds, never a number the API did not send', () => {
    expect(weekKicker('2026-09-14', '2026-09-20', t, ctx)).toBe('Week 38, 14 Sept 2026 to 20 Sept 2026');
  });
});
