import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as privateRecords from './api';

// The bank's own queue's three routes: the path each call takes and what it sends. There is
// no read of one proposal, so the detail walks the queue a full page at a time.

describe('private records api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads a page of the queue, leaving out the first page\'s offset', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    await privateRecords.listPrivateProposals({ limit: 20 });
    await privateRecords.listPrivateProposals({ limit: 20, offset: 40 });
    expect(sent.map((s) => [s.path, s.params])).toEqual([
      ['/api/v1/private-proposals', { limit: '20' }],
      ['/api/v1/private-proposals', { limit: '20', offset: '40' }],
    ]);
  });

  it('finds a proposal on a later page, and answers null once the queue runs out', async () => {
    const sent = installAdapter((s) => {
      const offset = Number((s.params as { offset?: string }).offset ?? 0);
      return { status: 200, data: { items: offset === 0 ? [{ id: 'a' }] : [{ id: 'b' }], total: 101 } };
    });
    expect(await privateRecords.findPrivateProposal('b')).toEqual({ id: 'b' });
    expect(await privateRecords.findPrivateProposal('c')).toBeNull();
    expect(sent.map((s) => s.params)).toEqual([{ limit: '100' }, { limit: '100', offset: '100' }, { limit: '100' }, { limit: '100', offset: '100' }]);
  });

  it('approves with the note and rejects with the reason\'s key and the note', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'p-1' } }));
    await privateRecords.approvePrivateProposal('p-1', { note: '' });
    await privateRecords.rejectPrivateProposal('p-1', { rejectionCode: 'duplicate', note: 'Held already.' });
    expect(sent.map((s) => [s.method, s.path, s.body])).toEqual([
      ['post', '/api/v1/private-proposals/p-1/approve', { note: '' }],
      ['post', '/api/v1/private-proposals/p-1/reject', { rejectionCode: 'duplicate', note: 'Held already.' }],
    ]);
  });
});
