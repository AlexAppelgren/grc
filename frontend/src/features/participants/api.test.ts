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

  it('reads, adds and removes on one route per verb, naming the record in the query or the body', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: { ok: s.path } }));
    const onObligation = { subjectType: 'obligation', subjectId: 'ob1' } as const;
    const onCase = { subjectType: 'change', subjectId: 'ch1' } as const;
    expect(await participants.listParticipants(onObligation)).toEqual({ ok: '/api/v1/participants' });
    await participants.addParticipant(onObligation, { teamKey: 'legal' });
    await participants.removeParticipant(onObligation, 'p 1');
    await participants.listParticipants(onCase);
    await participants.addParticipant(onCase, { userId: 'u1' });
    await participants.removeParticipant(onCase, 'p 1');
    expect(sent.map((s) => [s.method, s.path, s.params, s.body])).toEqual([
      ['get', '/api/v1/participants', { ...onObligation, limit: participants.PARTICIPANTS_PAGE }, null],
      ['post', '/api/v1/participants', null, { ...onObligation, teamKey: 'legal' }],
      ['delete', '/api/v1/participants/p%201', onObligation, null],
      ['get', '/api/v1/participants', { ...onCase, limit: participants.PARTICIPANTS_PAGE }, null],
      ['post', '/api/v1/participants', null, { ...onCase, userId: 'u1' }],
      ['delete', '/api/v1/participants/p%201', onCase, null],
    ]);
  });
});
