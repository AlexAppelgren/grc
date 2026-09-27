import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as participants from './api';

// Each wrapper hits its route with its method, body and query, and returns `.data`.

describe('participants api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads, adds and removes on the obligation’s own routes, and reads the picker’s lists', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: { ok: s.path } }));
    expect(await participants.listObligationParticipants('ob 1')).toEqual({ ok: '/api/v1/obligations/ob%201/participants' });
    await participants.addObligationParticipant('ob1', { teamKey: 'legal' });
    await participants.removeObligationParticipant('ob1', 'p 1');
    await participants.listPeople('register.read');
    await participants.listTeams();
    expect(sent.map((s) => [s.method, s.path, s.params, s.body])).toEqual([
      ['get', '/api/v1/obligations/ob%201/participants', { limit: participants.PARTICIPANTS_PAGE }, null],
      ['post', '/api/v1/obligations/ob1/participants', null, { teamKey: 'legal' }],
      ['delete', '/api/v1/obligations/ob1/participants/p%201', null, null],
      ['get', '/api/v1/reference/people', { permission: 'register.read' }, null],
      ['get', '/api/v1/tenant/teams', { limit: participants.PARTICIPANTS_PAGE }, null],
    ]);
  });
});
