import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { presentCalendarFeed } from './calendar-feeds-presentation';

const t = createT('en');

describe('presentCalendarFeed', () => {
  it('marks a live subscription active, positive', () => {
    expect(presentCalendarFeed({ revokedAt: null }, t)).toEqual([{ key: 'status:active', label: 'Active', tone: 'positive', order: 10 }]);
  });

  it('marks a revoked subscription revoked, neutral', () => {
    expect(presentCalendarFeed({ revokedAt: '2026-09-22T09:00:00Z' }, t)).toEqual([{ key: 'status:revoked', label: 'Revoked', tone: 'information', order: 10 }]);
  });
});
