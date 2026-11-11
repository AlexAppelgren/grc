import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { presentCalendarFeed } from './calendar-feeds-presentation';

const t = createT('en');

describe('presentCalendarFeed', () => {
  it('marks a feed that still works active, positive', () => {
    expect(presentCalendarFeed({ revokedAt: null }, t)).toEqual([{ key: 'status:active', label: 'Active', tone: 'positive', order: 5 }]);
  });

  it('marks a revoked feed revoked, a neutral fact, as an API key reads', () => {
    expect(presentCalendarFeed({ revokedAt: '2026-09-12T09:00:00Z' }, t)).toEqual([{ key: 'status:revoked', label: 'Revoked', tone: 'information', order: 5 }]);
  });

  it('labels in Swedish from the catalog, never from the API', () => {
    expect(presentCalendarFeed({ revokedAt: null }, createT('sv'))[0]?.label).toBe('Aktivt');
  });
});
