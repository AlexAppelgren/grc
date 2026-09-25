import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as governance from './api';

// The one wrapper hits GET /audit-events with the filters as query
// parameters and returns `.data`.

const event = {
  id: 'e1',
  createdAt: '2026-09-19T08:00:00Z',
  actor: { type: 'user', id: 'u1', label: 'Maria Lindqvist' },
  action: 'api_key.created',
  subjectType: 'api_key',
  subjectId: 'k1',
  subjectTitle: 'GRC export sync',
  summary: 'API key cw_ab12 created.',
  before: {},
  after: { scopes: ['tenant:read'] },
  steppedUp: true,
};

describe('governance api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the audit log with its filters and paging', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [event], total: 1 } }));
    expect(await governance.listAuditEvents({ limit: 20, offset: 0 })).toEqual({ items: [event], total: 1 });
    await governance.listAuditEvents({ subjectType: 'api_key', subjectId: 'k1', actorId: 'u1', from: '2026-09-01T00:00:00.000Z', to: '2026-09-20T00:00:00.000Z', limit: 20, offset: 20 });
    expect(sent.map((s) => [s.method, s.path, s.params, s.authorization])).toEqual([
      ['get', '/api/v1/audit-events', { limit: 20, offset: 0 }, 'Bearer tok'],
      [
        'get',
        '/api/v1/audit-events',
        { subjectType: 'api_key', subjectId: 'k1', actorId: 'u1', from: '2026-09-01T00:00:00.000Z', to: '2026-09-20T00:00:00.000Z', limit: 20, offset: 20 },
        'Bearer tok',
      ],
    ]);
  });
});
