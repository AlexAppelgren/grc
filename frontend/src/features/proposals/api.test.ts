import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as proposals from './api';

// The queue's four routes: the path each call takes and the query it sends.
// Nothing here reshapes the server's answer, because the generated types are
// the screens' types.

describe('proposals api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the queue with only the filters that are set', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    await proposals.listProposals({ status: 'open', kind: 'new_obligation_version' });
    expect([sent[0]?.path, sent[0]?.params]).toEqual(['/api/v1/proposals', { status: 'open', kind: 'new_obligation_version' }]);
  });

  it('leaves out an unset filter rather than sending it empty', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    await proposals.listProposals({});
    expect(sent[0]?.params).toEqual({});
  });

  it('reads one proposal by id', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'p-1' } }));
    await proposals.getProposal('p-1');
    expect(sent[0]?.path).toBe('/api/v1/proposals/p-1');
  });

  it('approves with the reviewer\'s note and corrections', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'p-1', status: 'approved' } }));
    await proposals.approveProposal('p-1', { note: 'Looks right', payloadOverrides: { effectiveFrom: '2026-10-01' } });
    expect([sent[0]?.method, sent[0]?.path, sent[0]?.body]).toEqual(['post', '/api/v1/proposals/p-1/approve', { note: 'Looks right', payloadOverrides: { effectiveFrom: '2026-10-01' } }]);
  });

  it('rejects with a reason and a note', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'p-1', status: 'rejected' } }));
    await proposals.rejectProposal('p-1', { rejectionCode: 'wrong_fact', note: 'Not what the source says' });
    expect([sent[0]?.method, sent[0]?.path, sent[0]?.body]).toEqual(['post', '/api/v1/proposals/p-1/reject', { rejectionCode: 'wrong_fact', note: 'Not what the source says' }]);
  });

  it('reads this tenant\'s own pending proposals, scoped by targetList', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    await proposals.listTenantProposals({ status: 'open', targetList: 'flag' });
    expect([sent[0]?.path, sent[0]?.params]).toEqual(['/api/v1/tenant/proposals', { status: 'open', targetList: 'flag' }]);
  });

  it('filters the queue by targetList alone', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    await proposals.listProposals({ targetList: 'flag' });
    expect(sent[0]?.params).toEqual({ targetList: 'flag' });
  });

  it('leaves out an unset filter on the tenant read too', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    await proposals.listTenantProposals({ kind: 'vocabulary_create' });
    expect(sent[0]?.params).toEqual({ kind: 'vocabulary_create' });
  });
});
