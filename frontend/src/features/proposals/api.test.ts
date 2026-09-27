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

  it('sends the queue\'s origin, notMine and page size for the route to filter, and leaves them out when unset', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    await proposals.listProposals({ status: 'open', origin: 'agent', notMine: true, limit: 100 });
    await proposals.listProposals({ origin: '', notMine: false });
    expect([sent[0]?.params, sent[1]?.params]).toEqual([{ status: 'open', origin: 'agent', notMine: 'true', limit: '100' }, {}]);
  });

  it('sends the order and the page a tab asks for, and leaves out the first page\'s offset', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [], total: 0 } }));
    await proposals.listProposals({ status: 'approved', order: 'newest', limit: 100, offset: 100 });
    await proposals.listProposals({ status: 'open', order: 'oldest', offset: 0 });
    expect([sent[0]?.params, sent[1]?.params]).toEqual([
      { status: 'approved', order: 'newest', limit: '100', offset: '100' },
      { status: 'open', order: 'oldest' },
    ]);
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

  it('reads a batch and decides its rows and the rest in one call', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { id: 'b-1', rows: [] } }));
    await proposals.getProposalBatch('b-1');
    await proposals.decideProposalBatch('b-1', { rows: [{ rowId: 'r-1', decision: 'rejected', rejectionCode: 'wrong_scope' }], rest: 'approved', restRejectionCode: '', note: '' });
    expect(sent.map((call) => [call.method, call.path])).toEqual([
      ['get', '/api/v1/proposal-batches/b-1'],
      ['post', '/api/v1/proposal-batches/b-1/decide'],
    ]);
    expect(sent[1]?.body).toEqual({ rows: [{ rowId: 'r-1', decision: 'rejected', rejectionCode: 'wrong_scope' }], rest: 'approved', restRejectionCode: '', note: '' });
  });

  it('asks for a re-tag in the console and reads the request back', async () => {
    const sent = installAdapter(() => ({ status: 202, data: { id: 'q-1', status: 'queued' } }));
    await proposals.createRetagRequest({ topic: 'Add the term Client money' });
    await proposals.getRetagRequest('q-1');
    expect(sent.map((call) => [call.method, call.path, call.body])).toEqual([
      ['post', '/api/v1/console/research-requests', { topic: 'Add the term Client money' }],
      ['get', '/api/v1/console/research-requests/q-1', null],
    ]);
  });

  it('reads every taxonomy term, across dimensions', async () => {
    const sent = installAdapter(() => ({ status: 200, data: { items: [{ id: 't-1', key: 'custody', label: 'Custody', dimension: 'service_type' }], total: 1 } }));
    const terms = await proposals.listTaxonomyTerms();
    expect([sent[0]?.path, terms.map((term) => term.key)]).toEqual(['/api/v1/taxonomy/terms', ['custody']]);
  });
});
